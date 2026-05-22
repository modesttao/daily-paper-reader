#!/usr/bin/env python
"""将会议检索结果写入 docs/_sidebar.md 的 Conference Papers 分组。"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SIDEBAR_PATH = ROOT_DIR / "docs" / "_sidebar.md"
CONFERENCE_HEADING = "* Conference Papers\n"


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def parse_conference_result_name(path: Path) -> Tuple[str, str]:
    name = path.name
    match = re.match(r"^conference-([a-z0-9-]+)-([0-9,-]+)\.supabase\.(?:llm|rerank|rrf)\.json$", name)
    if not match:
        raise ValueError(f"无法从会议结果文件名解析会议和年份：{path}")
    conference = match.group(1).upper()
    years = match.group(2).replace("-", ",")
    return conference, years


def build_conference_marker(conference: str, years: str) -> str:
    key = f"{norm_text(conference).lower()}-{norm_text(years).replace(',', '-')}"
    key = re.sub(r"[^a-z0-9-]+", "-", key).strip("-")
    return f"<!--dpr-conference:{key}-->"


def build_conference_label(conference: str, years: str) -> str:
    year_label = ", ".join(part.strip() for part in norm_text(years).split(",") if part.strip())
    return f"{norm_text(conference).upper()} {year_label}".strip()


def normalize_sidebar_tag(raw_tag: str) -> Tuple[str, str]:
    text = norm_text(raw_tag)
    if not text:
        return "", ""
    kind, sep, label = text.partition(":")
    if not sep:
        return "query", text
    kind = norm_text(kind).lower() or "query"
    if kind == "keyword":
        kind = "query"
    if kind not in {"keyword", "query", "paper", "other"}:
        kind = "other"
    label = norm_text(label)
    if kind == "query" and label.endswith(":composite"):
        label = label[: -len(":composite")].strip()
    return kind, label


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def score_from_ranked_item(item: Dict[str, Any]) -> float:
    for key in ("score", "star_rating"):
        try:
            return float(item.get(key))
        except Exception:
            continue
    return 0.0


def collect_ranked_ids(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    papers = data.get("papers") if isinstance(data.get("papers"), list) else []
    paper_ids = [norm_text(p.get("id")) for p in papers if isinstance(p, dict) and norm_text(p.get("id"))]
    llm_ranked = data.get("llm_ranked") if isinstance(data.get("llm_ranked"), list) else []
    ranked: List[Dict[str, Any]] = []
    seen = set()

    for item in llm_ranked:
        if not isinstance(item, dict):
            continue
        paper_id = norm_text(item.get("paper_id"))
        if not paper_id or paper_id in seen:
            continue
        seen.add(paper_id)
        ranked.append(item)

    if not ranked:
        queries = data.get("queries") if isinstance(data.get("queries"), list) else []
        merged: Dict[str, Dict[str, Any]] = {}
        for query in queries:
            if not isinstance(query, dict):
                continue
            for item in query.get("ranked") or []:
                if not isinstance(item, dict):
                    continue
                paper_id = norm_text(item.get("paper_id"))
                if not paper_id:
                    continue
                current = merged.get(paper_id)
                if current is None or score_from_ranked_item(item) > score_from_ranked_item(current):
                    merged[paper_id] = item
        ranked = sorted(merged.values(), key=score_from_ranked_item, reverse=True)

    if not ranked:
        ranked = [{"paper_id": paper_id} for paper_id in paper_ids]

    if limit > 0:
        ranked = ranked[:limit]
    return ranked


def build_sidebar_payload(
    paper: Dict[str, Any],
    ranked_item: Dict[str, Any],
    conference: str,
    years: str,
) -> str:
    title = norm_text(paper.get("title")) or norm_text(ranked_item.get("paper_id")) or "Untitled"
    link = norm_text(paper.get("link")) or "#"
    score = ranked_item.get("score", ranked_item.get("star_rating", "-"))
    try:
        score_text = f"{float(score):.1f}"
    except Exception:
        score_text = norm_text(score) or "-"
    tags = [
        {"kind": "paper", "label": conference.upper()},
        {"kind": "paper", "label": years.replace(",", "/")},
    ]
    matched_tag = norm_text(ranked_item.get("matched_query_tag"))
    if matched_tag:
        kind, label = normalize_sidebar_tag(matched_tag)
        if label:
            tags.append({"kind": kind or "query", "label": label})

    payload = {
        "title": title,
        "link": link,
        "score": score_text,
        "selection_source": "conference_retrieval",
        "tags": tags,
    }
    evidence = norm_text(
        ranked_item.get("canonical_evidence")
        or ranked_item.get("evidence_cn")
        or ranked_item.get("evidence_en")
        or ranked_item.get("tldr_cn")
        or ranked_item.get("tldr_en")
    )
    if evidence:
        payload["evidence"] = evidence
    return html.escape(json.dumps(payload, ensure_ascii=False), quote=True)


def build_conference_block(result_path: Path, limit: int = 80) -> List[str]:
    data = load_json(result_path)
    conference, years = parse_conference_result_name(result_path)
    marker = build_conference_marker(conference, years)
    label = build_conference_label(conference, years)
    papers = {
        norm_text(item.get("id")): item
        for item in (data.get("papers") if isinstance(data.get("papers"), list) else [])
        if isinstance(item, dict) and norm_text(item.get("id"))
    }
    ranked = collect_ranked_ids(data, limit)

    lines = [f"  * {label} {marker}\n", "    * 推荐论文\n"]
    for item in ranked:
        paper_id = norm_text(item.get("paper_id"))
        paper = papers.get(paper_id)
        if not paper:
            continue
        title = norm_text(paper.get("title")) or paper_id
        link = norm_text(paper.get("link")) or "#"
        payload = build_sidebar_payload(paper, item, conference, years)
        lines.append(
            "      * "
            f'<a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="{html.escape(link, quote=True)}" '
            f'data-sidebar-item="{payload}">{html.escape(title)}</a>\n'
        )
    return lines


def find_conference_heading(lines: List[str]) -> int:
    for idx, line in enumerate(lines):
        if line.strip() == "* Conference Papers":
            return idx
    return -1


def remove_existing_conference_block(lines: List[str], marker: str) -> None:
    heading_idx = find_conference_heading(lines)
    if heading_idx < 0:
        return
    block_idx = -1
    for idx in range(heading_idx + 1, len(lines)):
        if lines[idx].startswith("* "):
            break
        if marker in lines[idx]:
            block_idx = idx
            break
    if block_idx < 0:
        return
    end = block_idx + 1
    while end < len(lines):
        if lines[end].startswith("  * ") and not lines[end].startswith("    * "):
            break
        if lines[end].startswith("* "):
            break
        end += 1
    del lines[block_idx:end]


def ensure_conference_heading(lines: List[str]) -> int:
    heading_idx = find_conference_heading(lines)
    if heading_idx >= 0:
        return heading_idx

    daily_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == "* Daily Papers":
            daily_idx = idx
            break
    insert_idx = daily_idx if daily_idx >= 0 else len(lines)
    if insert_idx > 0 and lines[insert_idx - 1].strip():
        lines.insert(insert_idx, "\n")
        insert_idx += 1
    lines.insert(insert_idx, CONFERENCE_HEADING)
    return insert_idx


def update_sidebar_with_conference(sidebar_path: Path, result_path: Path, limit: int = 80) -> None:
    sidebar_path.parent.mkdir(parents=True, exist_ok=True)
    lines = sidebar_path.read_text(encoding="utf-8").splitlines(keepends=True) if sidebar_path.exists() else []
    conference, years = parse_conference_result_name(result_path)
    marker = build_conference_marker(conference, years)
    remove_existing_conference_block(lines, marker)
    heading_idx = ensure_conference_heading(lines)
    block = build_conference_block(result_path, limit)
    lines[heading_idx + 1:heading_idx + 1] = block
    sidebar_path.write_text("".join(lines), encoding="utf-8")


def choose_result_file(paths: Iterable[Path]) -> Path:
    existing = [p for p in paths if p and p.exists()]
    if not existing:
        raise FileNotFoundError("没有可用的会议结果文件。")
    priority = {".llm.json": 0, ".rerank.json": 1, ".rrf.json": 2}
    return sorted(
        existing,
        key=lambda p: next((rank for suffix, rank in priority.items() if p.name.endswith(suffix)), 9),
    )[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="更新 docs/_sidebar.md 的 Conference Papers 分组。")
    parser.add_argument("--result", action="append", default=[], help="会议结果 JSON，优先 llm，其次 rerank/rrf。可重复传入。")
    parser.add_argument("--sidebar", default=str(DEFAULT_SIDEBAR_PATH))
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    result_path = choose_result_file(Path(item) for item in args.result)
    update_sidebar_with_conference(Path(args.sidebar), result_path, limit=max(int(args.limit or 0), 0))
    print(f"[INFO] Conference sidebar updated: {args.sidebar} <- {result_path}", flush=True)


if __name__ == "__main__":
    main()
