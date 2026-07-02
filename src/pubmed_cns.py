#!/usr/bin/env python
"""CNS 级已发表期刊源（PubMed / NCBI E-utilities）。

与预印本源不同，本源是"查询驱动"的：按每个订阅方向（intent_profile）的
关键词 / intent_queries 去 PubMed 检索，并按 CNS 级期刊白名单过滤，只保留
Nature / Cell / Science 及其子刊等顶刊的已发表论文。

产出的论文会被注入到 Step 4 的输入（rerank JSON）中，走与预印本一致的
LLM 打分与 Step 5 选文流程；每个方向保底 1-2 篇由 Step 5 的按 tag 配额实现。

设计要点：
- 不依赖 Supabase：PubMed 本身即检索接口；
- 失败降级：任何网络/解析错误只记日志并跳过，绝不影响预印本主链路；
- 付费墙论文没有免费 PDF，标记 open_access=False，Step 6 对其降级为摘要级。
"""

import os
import re
import time
import json
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import requests

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TOOL = "daily-paper-reader"

# CNS 级期刊白名单（NLM Title / 常见刊名）。用户可在 config.yaml 的
# cns_source.journal_whitelist 覆盖。匹配时大小写与标点不敏感。
DEFAULT_CNS_JOURNALS: List[str] = [
    "Nature",
    "Science",
    "Cell",
    "Nature Neuroscience",
    "Nature Methods",
    "Nature Biotechnology",
    "Nature Medicine",
    "Nature Genetics",
    "Nature Cell Biology",
    "Nature Communications",
    "Cell Stem Cell",
    "Neuron",
    "Cell Systems",
    "Molecular Cell",
    "Developmental Cell",
    "Science Translational Medicine",
    "Science Advances",
]


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [pubmed-cns] {message}", flush=True)


def _norm_journal(name: str) -> str:
    """归一化刊名用于匹配：小写、去标点、压空白。"""
    text = re.sub(r"[^a-z0-9 ]+", " ", str(name or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _collect_direction_terms(profile: Dict[str, Any], max_terms: int = 12) -> List[str]:
    """从一个 intent_profile 收集用于 PubMed 检索的短语。"""
    terms: List[str] = []
    seen = set()
    for key in ("keywords", "intent_queries"):
        for item in profile.get(key) or []:
            if isinstance(item, dict):
                text = item.get("keyword") or item.get("query") or item.get("text") or ""
            else:
                text = item
            text = str(text or "").strip()
            if not text:
                continue
            low = text.lower()
            if low in seen:
                continue
            seen.add(low)
            terms.append(text)
            if len(terms) >= max_terms:
                return terms
    return terms


def build_pubmed_query(terms: List[str], journals: List[str]) -> str:
    """拼接 PubMed 检索式：(方向短语 OR) AND (期刊白名单 OR)。

    短语用引号包裹走短语检索；期刊用 [Journal] 字段限定。
    """
    term_clause = " OR ".join(f'"{t}"[Title/Abstract]' for t in terms if t.strip())
    journal_clause = " OR ".join(f'"{j}"[Journal]' for j in journals if j.strip())
    parts = []
    if term_clause:
        parts.append(f"({term_clause})")
    if journal_clause:
        parts.append(f"({journal_clause})")
    return " AND ".join(parts)


class PubMedClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        tool: str = DEFAULT_TOOL,
        timeout: int = 30,
    ):
        self.api_key = (api_key or os.getenv("NCBI_API_KEY") or "").strip() or None
        self.email = (email or os.getenv("NCBI_EMAIL") or "").strip() or None
        self.tool = tool
        self.timeout = timeout
        # 无 api_key 时 NCBI 限 3 req/s；留足间隔更稳。
        self._min_interval = 0.12 if self.api_key else 0.34
        self._last_call = 0.0

    def _common_params(self) -> Dict[str, str]:
        params: Dict[str, str] = {"tool": self.tool}
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _throttle(self) -> None:
        try:
            elapsed = time.time() - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        except Exception:
            pass
        self._last_call = time.time()

    def _get(self, endpoint: str, params: Dict[str, str]) -> requests.Response:
        self._throttle()
        url = f"{EUTILS_BASE}/{endpoint}"
        resp = requests.get(url, params={**self._common_params(), **params}, timeout=self.timeout)
        resp.raise_for_status()
        return resp

    def esearch(self, query: str, retmax: int = 30, reldays: int = 30) -> List[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": str(max(1, retmax)),
            "retmode": "json",
            "datetype": "pdat",
            "reldate": str(max(1, reldays)),
            "sort": "date",
        }
        data = self._get("esearch.fcgi", params).json()
        idlist = (((data or {}).get("esearchresult") or {}).get("idlist")) or []
        return [str(x) for x in idlist if str(x).strip()]

    def efetch(self, pmids: List[str]) -> str:
        if not pmids:
            return ""
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
        return self._get("efetch.fcgi", params).text


def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return html.unescape("".join(el.itertext())).strip()


def parse_pubmed_xml(xml_text: str) -> List[Dict[str, Any]]:
    """把 efetch 返回的 PubmedArticleSet XML 解析成规范化论文列表。"""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out: List[Dict[str, Any]] = []
    for art in root.findall(".//PubmedArticle"):
        medline = art.find(".//MedlineCitation")
        if medline is None:
            continue
        pmid = _text(medline.find("./PMID"))
        article = medline.find("./Article")
        if article is None or not pmid:
            continue

        title = _text(article.find("./ArticleTitle"))
        # 摘要可能有多段 AbstractText（含 Label）
        abstract_parts: List[str] = []
        for ab in article.findall("./Abstract/AbstractText"):
            label = ab.get("Label")
            seg = _text(ab)
            if not seg:
                continue
            abstract_parts.append(f"{label}: {seg}" if label else seg)
        abstract = "\n".join(abstract_parts).strip()

        journal_el = article.find("./Journal")
        journal = ""
        issn = ""
        if journal_el is not None:
            journal = _text(journal_el.find("./Title")) or _text(
                journal_el.find("./ISOAbbreviation")
            )
            issn = _text(journal_el.find("./ISSN"))

        # 作者
        authors: List[str] = []
        for a in article.findall("./AuthorList/Author"):
            last = _text(a.find("./LastName"))
            fore = _text(a.find("./ForeName")) or _text(a.find("./Initials"))
            name = (f"{fore} {last}").strip() or _text(a.find("./CollectiveName"))
            if name:
                authors.append(name)

        # 发表日期
        published = _parse_pub_date(article, medline)

        # DOI / PMCID（PMC 表示有免费全文）
        doi = ""
        pmcid = ""
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            idtype = (aid.get("IdType") or "").lower()
            val = _text(aid)
            if idtype == "doi" and not doi:
                doi = val
            elif idtype == "pmc" and not pmcid:
                pmcid = val

        out.append({
            "id": f"pmid:{pmid}",
            "pmid": pmid,
            "source": "pubmed",
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "issn": issn,
            "doi": doi,
            "pmcid": pmcid,
            "open_access": bool(pmcid),
            "published": published,
            "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "primary_category": None,
            "categories": [],
        })
    return out


def _parse_pub_date(article: ET.Element, medline: ET.Element) -> Optional[str]:
    # 优先 ArticleDate，其次 Journal/JournalIssue/PubDate
    for path in ("./ArticleDate", "./Journal/JournalIssue/PubDate"):
        el = article.find(path)
        if el is None:
            continue
        year = _text(el.find("./Year"))
        month = _text(el.find("./Month")) or "01"
        day = _text(el.find("./Day")) or "01"
        if not year:
            # PubDate 可能是 MedlineDate 自由文本，如 "2026 Jun"
            medline_date = _text(el.find("./MedlineDate"))
            m = re.search(r"(\d{4})", medline_date)
            if m:
                year = m.group(1)
        if year:
            month = _month_to_num(month)
            try:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T00:00:00+00:00"
            except Exception:
                return f"{year}-01-01T00:00:00+00:00"
    return None


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_to_num(month: str) -> int:
    m = str(month or "").strip().lower()
    if m.isdigit():
        return max(1, min(12, int(m)))
    return _MONTHS.get(m[:3], 1)


def filter_by_whitelist(papers: List[Dict[str, Any]], journals: List[str]) -> List[Dict[str, Any]]:
    """防御性二次过滤：按解析出的刊名匹配白名单（PubMed 字段检索偶有偏差）。"""
    allow = {_norm_journal(j) for j in journals if str(j).strip()}
    if not allow:
        return papers
    kept: List[Dict[str, Any]] = []
    for p in papers:
        jn = _norm_journal(p.get("journal"))
        if not jn:
            continue
        # 完整匹配或作为前缀（"nature" 命中 "nature", 但不误伤 "nature communications" 需在白名单内才留）
        if jn in allow or any(jn == a for a in allow):
            kept.append(p)
    return kept


def fetch_cns_candidates(
    profiles: List[Dict[str, Any]],
    journals: List[str],
    *,
    per_direction_fetch: int = 30,
    reldays: int = 30,
    client: Optional[PubMedClient] = None,
) -> List[Dict[str, Any]]:
    """按方向检索 CNS 论文，跨方向按 PMID 去重（保留全部命中 tag）。"""
    cli = client or PubMedClient()
    by_pmid: Dict[str, Dict[str, Any]] = {}

    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        if profile.get("enabled") is False:
            continue
        tag = str(profile.get("tag") or "").strip()
        if not tag:
            continue
        terms = _collect_direction_terms(profile)
        if not terms:
            continue
        query = build_pubmed_query(terms, journals)
        try:
            pmids = cli.esearch(query, retmax=per_direction_fetch, reldays=reldays)
            xml_text = cli.efetch(pmids)
            papers = filter_by_whitelist(parse_pubmed_xml(xml_text), journals)
        except Exception as exc:  # 单方向失败不影响其它方向
            log(f"[WARN] 方向 {tag} 检索失败：{exc}")
            continue
        log(f"方向 {tag}: 命中 {len(papers)} 篇 CNS 论文")

        tag_names = [f"keyword:{tag}", f"query:{tag}"]
        for p in papers:
            pmid = p.get("pmid")
            if not pmid:
                continue
            if pmid in by_pmid:
                existing = by_pmid[pmid]
                merged = list(dict.fromkeys((existing.get("tags") or []) + tag_names))
                existing["tags"] = merged
            else:
                q = dict(p)
                q["tags"] = list(tag_names)
                q["matched_query_tag"] = f"query:{tag}"
                by_pmid[pmid] = q
    return list(by_pmid.values())


def inject_into_rerank(rerank_path: str, cns_papers: List[Dict[str, Any]], star_rating: int = 5) -> int:
    """把 CNS 论文注入 Step 4 的输入（rerank JSON）。

    - 追加到 papers 列表；
    - 为每个方向 tag 在 queries 里补一条 ranked 引用，star_rating 给满分
      以确保进入 LLM 打分（真实相关度由 Step 4 的 LLM 评分决定）。
    若文件不存在（当天无预印本），创建最小结构。
    """
    if not cns_papers:
        return 0

    if os.path.exists(rerank_path):
        with open(rerank_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        os.makedirs(os.path.dirname(rerank_path) or ".", exist_ok=True)
        data = {"papers": [], "queries": []}

    papers = data.setdefault("papers", [])
    queries = data.setdefault("queries", [])
    existing_ids = {str(p.get("id")) for p in papers if isinstance(p, dict)}

    # tag -> query 对象索引（按 matched_query_tag / tag 匹配现有 query）
    query_by_tag: Dict[str, Dict[str, Any]] = {}
    for q in queries:
        if not isinstance(q, dict):
            continue
        qtag = str(q.get("tag") or "").strip()
        if qtag:
            query_by_tag.setdefault(qtag, q)

    added = 0
    for p in cns_papers:
        pid = str(p.get("id"))
        if pid not in existing_ids:
            papers.append(p)
            existing_ids.add(pid)
            added += 1
        for tag_name in p.get("tags") or []:
            if not tag_name.startswith("query:"):
                continue
            tag = tag_name.split(":", 1)[1]
            q = query_by_tag.get(tag)
            if q is None:
                q = {"tag": tag, "query": tag, "ranked": []}
                queries.append(q)
                query_by_tag[tag] = q
            ranked = q.setdefault("ranked", [])
            if not any(str(r.get("paper_id")) == pid for r in ranked if isinstance(r, dict)):
                ranked.append({"paper_id": pid, "star_rating": star_rating, "source": "pubmed"})

    with open(rerank_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return added


def load_cns_config(config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    cfg = (config or {}).get("cns_source") or {}
    enabled = bool(cfg.get("enabled", False))
    resolved = {
        "journal_whitelist": cfg.get("journal_whitelist") or DEFAULT_CNS_JOURNALS,
        "per_direction_fetch": int(cfg.get("per_direction_fetch") or 30),
        "reldays": int(cfg.get("reldays") or 30),
    }
    return enabled, resolved


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="检索 CNS 级 PubMed 论文并注入 rerank 候选池。")
    parser.add_argument("--config", default=os.getenv("DPR_CONFIG_FILE") or "config.yaml")
    parser.add_argument("--rerank", required=True, help="Step 4 输入（rerank JSON）路径。")
    parser.add_argument("--reldays", type=int, default=None)
    args = parser.parse_args()

    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] 未安装 PyYAML，跳过 CNS 源。")
        return

    if not os.path.exists(args.config):
        log(f"[WARN] 配置不存在：{args.config}，跳过。")
        return
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    enabled, cfg = load_cns_config(config)
    if not enabled:
        log("cns_source.enabled=false，跳过 CNS 源。")
        return

    profiles = ((config.get("subscriptions") or {}).get("intent_profiles")) or []
    if not profiles:
        log("[WARN] 无 intent_profiles，跳过。")
        return

    reldays = args.reldays if args.reldays is not None else cfg["reldays"]
    try:
        cns_papers = fetch_cns_candidates(
            profiles,
            cfg["journal_whitelist"],
            per_direction_fetch=cfg["per_direction_fetch"],
            reldays=reldays,
        )
    except Exception as exc:
        log(f"[WARN] CNS 检索整体失败，降级跳过：{exc}")
        return

    if not cns_papers:
        log("未检索到符合白名单的 CNS 论文。")
        return

    added = inject_into_rerank(args.rerank, cns_papers)
    log(f"注入完成：{added} 篇 CNS 论文进入候选池（去重后共 {len(cns_papers)} 篇）。")


if __name__ == "__main__":
    main()
