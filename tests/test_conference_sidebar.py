import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class ConferenceSidebarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.mod = _load_module("conference_sidebar_mod", root / "src" / "conference_sidebar.py")

    def write_result(self, path: pathlib.Path, title: str = "A Conference Paper") -> None:
        payload = {
            "papers": [
                {
                    "id": "openreview-icml-2025-abc123",
                    "title": title,
                    "link": "https://openreview.net/forum?id=abc123",
                    "source": "ICML-2025-Accepted",
                }
            ],
            "queries": [],
            "llm_ranked": [
                {
                    "paper_id": "openreview-icml-2025-abc123",
                    "score": 9,
                    "canonical_evidence": "命中 ICML 会议检索需求。",
                    "matched_query_tag": "query:rl:composite",
                }
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_update_sidebar_adds_conference_three_level_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            sidebar = tmp_path / "_sidebar.md"
            result = tmp_path / "conference-icml-2025.supabase.llm.json"
            sidebar.write_text("* <a class=\"dpr-sidebar-root-link\" href=\"#/\">首页</a>\n* Daily Papers\n", encoding="utf-8")
            self.write_result(result)

            self.mod.update_sidebar_with_conference(sidebar, result)
            text = sidebar.read_text(encoding="utf-8")

            self.assertIn("* Conference Papers", text)
            self.assertIn("  * ICML 2025 <!--dpr-conference:icml-2025-->", text)
            self.assertIn("    * 推荐论文", text)
            self.assertIn("      * <a class=\"dpr-sidebar-item-link dpr-sidebar-item-structured\"", text)
            self.assertIn("A Conference Paper", text)
            self.assertIn("https://openreview.net/forum?id=abc123", text)
            self.assertIn("&quot;selection_source&quot;: &quot;conference_retrieval&quot;", text)
            self.assertIn("&quot;label&quot;: &quot;rl&quot;", text)
            self.assertNotIn("rl:composite", text)
            self.assertIn("* Daily Papers", text)

    def test_update_sidebar_replaces_existing_conference_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            sidebar = tmp_path / "_sidebar.md"
            result = tmp_path / "conference-icml-2025.supabase.llm.json"
            sidebar.write_text("* Daily Papers\n", encoding="utf-8")

            self.write_result(result, title="First Title")
            self.mod.update_sidebar_with_conference(sidebar, result)
            self.write_result(result, title="Second Title")
            self.mod.update_sidebar_with_conference(sidebar, result)
            text = sidebar.read_text(encoding="utf-8")

            self.assertEqual(text.count("<!--dpr-conference:icml-2025-->"), 1)
            self.assertNotIn("First Title", text)
            self.assertIn("Second Title", text)


if __name__ == "__main__":
    unittest.main()
