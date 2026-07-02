import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pubmed_cns as pc


SAMPLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>40000001</PMID>
      <Article>
        <Journal>
          <ISSN>1476-4687</ISSN>
          <Title>Nature Neuroscience</Title>
          <JournalIssue>
            <PubDate><Year>2026</Year><Month>Jun</Month><Day>15</Day></PubDate>
          </JournalIssue>
        </Journal>
        <ArticleTitle>Cortical organoid maturation atlas</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Brain organoids model development.</AbstractText>
          <AbstractText Label="RESULTS">We built a single-cell atlas.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author>
          <Author><LastName>Smith</LastName><Initials>A</Initials></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1038/s41593-026-00000-0</ArticleId>
        <ArticleId IdType="pmc">PMC12345678</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>40000002</PMID>
      <Article>
        <Journal>
          <Title>Some Predatory Journal</Title>
          <JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Off-whitelist paper</ArticleTitle>
        <Abstract><AbstractText>Not a CNS journal.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


class ParseTest(unittest.TestCase):
    def test_parse_pubmed_xml(self):
        papers = pc.parse_pubmed_xml(SAMPLE_XML)
        self.assertEqual(len(papers), 2)
        p = papers[0]
        self.assertEqual(p["id"], "pmid:40000001")
        self.assertEqual(p["source"], "pubmed")
        self.assertEqual(p["journal"], "Nature Neuroscience")
        self.assertIn("single-cell atlas", p["abstract"])
        self.assertIn("BACKGROUND:", p["abstract"])
        self.assertEqual(p["authors"], ["Jane Doe", "A Smith"])
        self.assertEqual(p["doi"], "10.1038/s41593-026-00000-0")
        self.assertTrue(p["open_access"])  # 有 PMC
        self.assertTrue(p["published"].startswith("2026-06-15"))
        self.assertEqual(p["link"], "https://pubmed.ncbi.nlm.nih.gov/40000001/")

    def test_parse_bad_xml_returns_empty(self):
        self.assertEqual(pc.parse_pubmed_xml("<not valid"), [])
        self.assertEqual(pc.parse_pubmed_xml(""), [])


class WhitelistTest(unittest.TestCase):
    def test_filter_by_whitelist(self):
        papers = pc.parse_pubmed_xml(SAMPLE_XML)
        kept = pc.filter_by_whitelist(papers, ["Nature Neuroscience", "Cell"])
        self.assertEqual([p["pmid"] for p in kept], ["40000001"])

    def test_whitelist_is_punctuation_insensitive(self):
        papers = [{"journal": "Nature  Neuroscience.", "pmid": "1"}]
        kept = pc.filter_by_whitelist(papers, ["nature neuroscience"])
        self.assertEqual(len(kept), 1)


class QueryBuildTest(unittest.TestCase):
    def test_build_pubmed_query(self):
        q = pc.build_pubmed_query(["brain organoid", "assembloid"], ["Nature", "Cell"])
        self.assertIn('"brain organoid"[Title/Abstract]', q)
        self.assertIn('"Nature"[Journal]', q)
        self.assertIn(" AND ", q)

    def test_collect_direction_terms_dedup_and_cap(self):
        profile = {
            "keywords": [{"keyword": "brain organoid"}, {"keyword": "Brain Organoid"}],
            "intent_queries": [{"query": "assembloid circuit"}],
        }
        terms = pc._collect_direction_terms(profile, max_terms=5)
        self.assertEqual(terms, ["brain organoid", "assembloid circuit"])


class FetchTest(unittest.TestCase):
    def _client(self):
        cli = pc.PubMedClient.__new__(pc.PubMedClient)
        cli.esearch = MagicMock(return_value=["40000001", "40000002"])
        cli.efetch = MagicMock(return_value=SAMPLE_XML)
        return cli

    def test_fetch_cns_candidates_filters_and_tags(self):
        profiles = [
            {"tag": "neural-organoid", "enabled": True,
             "keywords": [{"keyword": "brain organoid"}]},
            {"tag": "disabled", "enabled": False, "keywords": [{"keyword": "x"}]},
        ]
        out = pc.fetch_cns_candidates(
            profiles, ["Nature Neuroscience"], client=self._client()
        )
        self.assertEqual(len(out), 1)  # 只保留白名单内 + 跳过 disabled 方向
        self.assertEqual(out[0]["pmid"], "40000001")
        self.assertIn("keyword:neural-organoid", out[0]["tags"])
        self.assertIn("query:neural-organoid", out[0]["tags"])

    def test_direction_failure_does_not_abort(self):
        cli = pc.PubMedClient.__new__(pc.PubMedClient)
        cli.esearch = MagicMock(side_effect=RuntimeError("network"))
        cli.efetch = MagicMock(return_value="")
        out = pc.fetch_cns_candidates(
            [{"tag": "t", "enabled": True, "keywords": [{"keyword": "x"}]}],
            ["Nature"], client=cli,
        )
        self.assertEqual(out, [])


class InjectTest(unittest.TestCase):
    def test_inject_into_new_rerank_file(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rank", "arxiv.json")
            cns = [{
                "id": "pmid:40000001", "source": "pubmed", "title": "t",
                "tags": ["keyword:neural-organoid", "query:neural-organoid"],
            }]
            added = pc.inject_into_rerank(path, cns)
            self.assertEqual(added, 1)
            data = json.load(open(path))
            self.assertEqual(len(data["papers"]), 1)
            q = data["queries"][0]
            self.assertEqual(q["tag"], "neural-organoid")
            self.assertEqual(q["ranked"][0]["paper_id"], "pmid:40000001")
            self.assertEqual(q["ranked"][0]["star_rating"], 5)

    def test_inject_merges_into_existing_and_dedups(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "arxiv.json")
            json.dump({
                "papers": [{"id": "2606.1v1", "source": "arxiv"}],
                "queries": [{"tag": "neural-organoid", "query": "x", "ranked": []}],
            }, open(path, "w"))
            cns = [{"id": "pmid:1", "source": "pubmed",
                    "tags": ["query:neural-organoid"]}]
            pc.inject_into_rerank(path, cns)
            pc.inject_into_rerank(path, cns)  # 二次注入应幂等
            data = json.load(open(path))
            self.assertEqual(len(data["papers"]), 2)
            ranked = data["queries"][0]["ranked"]
            self.assertEqual(len(ranked), 1)  # 未重复追加


class ConfigTest(unittest.TestCase):
    def test_load_cns_config_defaults(self):
        enabled, cfg = pc.load_cns_config({"cns_source": {"enabled": True}})
        self.assertTrue(enabled)
        self.assertEqual(cfg["journal_whitelist"], pc.DEFAULT_CNS_JOURNALS)

    def test_disabled_by_default(self):
        enabled, _ = pc.load_cns_config({})
        self.assertFalse(enabled)


if __name__ == "__main__":
    unittest.main()
