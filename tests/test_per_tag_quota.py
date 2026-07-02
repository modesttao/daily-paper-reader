import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class PerTagQuotaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("select_mod_quota", src_dir / "5.select_papers.py")

    def _paper(self, pid, score, tag, source="arxiv"):
        return {
            "id": pid,
            "llm_score": score,
            "source": source,
            "tags": [f"keyword:{tag}", f"query:{tag}"],
            "llm_tags": [f"query:{tag}"],
            "matched_query_tag": f"query:{tag}",
        }

    def _run(self, candidates, **cfg):
        base = {"per_tag_quota": True, "per_tag_min": 1, "per_tag_max": 2,
                "per_tag_high_score": 8.0, "per_tag_min_score": 6.0,
                "per_tag_prioritize_source": "pubmed"}
        base.update(cfg)
        return self.mod.process_mode_per_tag_quota(candidates, "extend", base)

    def _ids(self, result):
        return {p["id"] for p in result["deep_dive"]} | {p["id"] for p in result["quick_skim"]}

    def test_each_direction_gets_at_least_one(self):
        cands = [
            self._paper("a1", 9.0, "neural-organoid"),
            self._paper("a2", 8.5, "neural-organoid"),
            self._paper("b1", 6.5, "als-organoid"),
            self._paper("c1", 7.0, "scz-model"),
        ]
        res = self._run(cands)
        ids = self._ids(res)
        # 每个方向至少 1 篇
        self.assertIn("b1", ids)   # als 唯一候选
        self.assertIn("c1", ids)   # scz 唯一候选
        self.assertIn("a1", ids)   # neural 最高分

    def test_second_paper_only_if_high_score(self):
        # neural 有两篇高分(>=8) -> 出 2；als 第二篇低分 -> 只出 1
        cands = [
            self._paper("a1", 9.0, "neural-organoid"),
            self._paper("a2", 8.2, "neural-organoid"),
            self._paper("b1", 7.5, "als-organoid"),
            self._paper("b2", 6.5, "als-organoid"),
        ]
        ids = self._ids(self._run(cands))
        self.assertIn("a1", ids)
        self.assertIn("a2", ids)      # 第二篇高分，入选
        self.assertIn("b1", ids)
        self.assertNotIn("b2", ids)   # 第二篇非高分，不入选

    def test_below_floor_excluded(self):
        cands = [self._paper("a1", 5.0, "neural-organoid")]
        ids = self._ids(self._run(cands))
        self.assertEqual(ids, set())  # 低于 per_tag_min_score

    def test_pubmed_prioritized_within_direction(self):
        # 同方向：预印本分更高，但 pubmed 优先占坑（CNS 为主）
        cands = [
            self._paper("pre", 9.5, "neural-organoid", source="arxiv"),
            self._paper("cns", 8.0, "neural-organoid", source="pubmed"),
        ]
        res = self._run(cands, per_tag_min=1, per_tag_max=1)
        ids = self._ids(res)
        self.assertIn("cns", ids)      # pubmed 先占唯一名额
        self.assertNotIn("pre", ids)

    def test_deep_vs_quick_split(self):
        cands = [
            self._paper("hi", 8.5, "neural-organoid"),
            self._paper("lo", 6.5, "als-organoid"),
        ]
        res = self._run(cands)
        self.assertIn("hi", {p["id"] for p in res["deep_dive"]})
        self.assertIn("lo", {p["id"] for p in res["quick_skim"]})

    def test_multi_tag_paper_covers_both_directions(self):
        # 一篇同时命中两个方向，应同时代表两者，不重复计入总数
        p = self._paper("shared", 9.0, "neural-organoid")
        p["tags"] += ["keyword:als-organoid", "query:als-organoid"]
        p["llm_tags"] += ["query:als-organoid"]
        res = self._run([p])
        ids = self._ids(res)
        self.assertEqual(ids, {"shared"})  # 只出现一次


if __name__ == "__main__":
    unittest.main()
