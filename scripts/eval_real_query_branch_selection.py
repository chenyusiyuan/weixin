#!/usr/bin/env python3
"""Evaluate branch selection on real golden queries.

The golden set has `query + gold_skill`, but it does not have gold branch
labels. This script therefore fixes the skill to `gold_skill` and evaluates
whether the query is close enough to one branch in that skill's
`branch_conditions`.

It is a branch separability smoke test, not a final branch accuracy metric.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.mock_branch_progression_eval import overlap_score  # noqa: E402


GOLDEN_PATH = ROOT / "raw_test.jsonl"
SKILL_DIR = ROOT / "skills" / "definitions"
REPORT_FILE = ROOT / "docs" / "real_query_branch_eval.md"
JSON_FILE = ROOT / "docs" / "real_query_branch_eval.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_skill(path: Path) -> dict[str, Any]:
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    raw: dict[str, Any] = {}
    for doc in docs:
        if isinstance(doc, dict):
            raw.update(doc)
    return raw


def rank_branch(query: str, branches: list[dict[str, Any]]) -> tuple[str | None, float, str | None, float]:
    scored = sorted(
        [(overlap_score(query, branch), branch.get("variant")) for branch in branches],
        reverse=True,
        key=lambda item: item[0],
    )
    best_score, best_variant = scored[0] if scored else (0.0, None)
    runner_score, runner_variant = scored[1] if len(scored) > 1 else (0.0, None)
    return best_variant, best_score, runner_variant, runner_score


def classify_selection(selected: str | None, score: float, runner_score: float) -> str:
    if not selected or score < 0.10:
        return "no_select"
    margin = score - runner_score
    if score >= 0.26 and margin >= 0.03:
        return "confident"
    return "low_confidence"


def evaluate(min_gold_confidence: float) -> dict[str, Any]:
    skills: dict[str, dict[str, Any]] = {}
    for path in sorted(SKILL_DIR.glob("*.yaml")):
        skill = load_skill(path)
        skills[path.stem] = skill

    rows = [
        row for row in load_jsonl(GOLDEN_PATH)
        if row.get("gold_skill") in skills
        and float(row.get("confidence", 1.0)) >= min_gold_confidence
    ]
    records: list[dict[str, Any]] = []
    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        skill_id = row["gold_skill"]
        skill = skills[skill_id]
        branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
        query = str(row.get("query") or "").strip()
        if not branches:
            record = {
                "call_id": row.get("call_id"),
                "query": query,
                "gold_skill": skill_id,
                "skill_name": skill.get("name") or skill_id,
                "gold_confidence": row.get("confidence"),
                "status": "skill_has_no_branch",
                "selected_variant": None,
                "score": 0.0,
                "runner_up_variant": None,
                "runner_up_score": 0.0,
                "branch_count": 0,
            }
        else:
            selected, score, runner, runner_score = rank_branch(query, branches)
            record = {
                "call_id": row.get("call_id"),
                "query": query,
                "gold_skill": skill_id,
                "skill_name": skill.get("name") or skill_id,
                "gold_confidence": row.get("confidence"),
                "status": classify_selection(selected, score, runner_score),
                "selected_variant": selected,
                "score": score,
                "runner_up_variant": runner,
                "runner_up_score": runner_score,
                "branch_count": len(branches),
            }
        records.append(record)
        by_skill[skill_id].append(record)

    skill_summaries: list[dict[str, Any]] = []
    for skill_id, skill in sorted(skills.items()):
        skill_records = by_skill.get(skill_id, [])
        branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
        status_counter = Counter(r["status"] for r in skill_records)
        selected_counter = Counter(
            r["selected_variant"] for r in skill_records
            if r.get("selected_variant")
        )
        skill_summaries.append(
            {
                "skill_id": skill_id,
                "name": skill.get("name") or skill_id,
                "branch_count": len(branches),
                "real_query_count": len(skill_records),
                "status_counts": dict(status_counter),
                "selected_branch_counts": dict(selected_counter),
            }
        )

    branch_skills = [s for s in skill_summaries if s["branch_count"] > 0]
    branch_records = [r for r in records if r["branch_count"] > 0]
    status_counter = Counter(r["status"] for r in branch_records)
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(GOLDEN_PATH.relative_to(ROOT)),
        "min_gold_confidence": min_gold_confidence,
        "summary": {
            "golden_rows_used": len(rows),
            "skill_count": len(skills),
            "branch_skill_count": len(branch_skills),
            "branch_skills_with_real_queries": sum(1 for s in branch_skills if s["real_query_count"] > 0),
            "branch_skills_without_real_queries": [
                s["skill_id"] for s in branch_skills if s["real_query_count"] == 0
            ],
            "branch_query_count": len(branch_records),
            "confident": status_counter.get("confident", 0),
            "low_confidence": status_counter.get("low_confidence", 0),
            "no_select": status_counter.get("no_select", 0),
        },
        "skills": skill_summaries,
        "records": records,
    }
    return payload


def _short(text: str, limit: int = 70) -> str:
    text = str(text or "").replace("|", "｜").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def render_markdown(payload: dict[str, Any], examples_per_skill: int) -> str:
    summary = payload["summary"]
    lines: list[str] = [
        "# 真实 Query Branch 选择效果抽样",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 数据源：`{payload['source']}`；使用 gold_skill 固定 skill，只评估 branch 选择效果。",
        f"- gold 置信度过滤：`confidence >= {payload['min_gold_confidence']}`。",
        "- 说明：真实数据没有 gold branch 标签，因此这里看的是分支可分性/命中清晰度，不是最终准确率。",
        "",
        "## 总览",
        "",
        f"- 使用真实 query：{summary['golden_rows_used']} 条。",
        f"- 有分支 skill：{summary['branch_skill_count']} 个；其中 {summary['branch_skills_with_real_queries']} 个在 golden 中有真实 query。",
        f"- 参与 branch 评估 query：{summary['branch_query_count']} 条。",
        f"- confident：{summary['confident']}；low_confidence：{summary['low_confidence']}；no_select：{summary['no_select']}。",
    ]
    if summary["branch_skills_without_real_queries"]:
        lines.append("- 有分支但本次 golden 无真实样本：" + ", ".join(f"`{sid}`" for sid in summary["branch_skills_without_real_queries"]))

    records_by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in payload["records"]:
        records_by_skill[record["gold_skill"]].append(record)

    lines.extend(["", "## Skill 汇总", ""])
    lines.append("| skill_id | 名称 | branch | real query | confident | low | no_select | top branches |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|")
    for skill in payload["skills"]:
        if skill["branch_count"] <= 0:
            continue
        counts = skill["status_counts"]
        selected = Counter(skill["selected_branch_counts"]).most_common(4)
        top = "；".join(f"`{k}` {v}" for k, v in selected) or "-"
        lines.append(
            f"| `{skill['skill_id']}` | {skill['name']} | {skill['branch_count']} | "
            f"{skill['real_query_count']} | {counts.get('confident', 0)} | "
            f"{counts.get('low_confidence', 0)} | {counts.get('no_select', 0)} | {top} |"
        )

    lines.extend(["", "## 抽样明细", ""])
    for skill in payload["skills"]:
        if skill["branch_count"] <= 0:
            continue
        records = records_by_skill.get(skill["skill_id"], [])
        if not records:
            lines.append(f"### `{skill['skill_id']}` {skill['name']}")
            lines.append("- 本次真实数据中没有该 skill 的 query。")
            lines.append("")
            continue
        confident = sorted(
            [r for r in records if r["status"] == "confident"],
            key=lambda r: (-r["score"], r["query"]),
        )
        weak = sorted(
            [r for r in records if r["status"] != "confident"],
            key=lambda r: (r["score"], r["query"]),
        )
        sample = confident[:examples_per_skill]
        if weak:
            sample = sample[: max(0, examples_per_skill - min(2, len(weak)))] + weak[:2]
        lines.append(f"### `{skill['skill_id']}` {skill['name']}")
        counts = Counter(r["status"] for r in records)
        lines.append(
            f"- 真实 query：{len(records)}；confident：{counts.get('confident', 0)}；"
            f"low_confidence：{counts.get('low_confidence', 0)}；no_select：{counts.get('no_select', 0)}。"
        )
        lines.append("| query | selected branch | status | score | runner_up |")
        lines.append("|---|---|---|---:|---|")
        for r in sample:
            lines.append(
                f"| {_short(r['query'])} | `{r['selected_variant'] or '-'}` | "
                f"{r['status']} | {r['score']:.3f} | `{r['runner_up_variant'] or '-'}` {r['runner_up_score']:.3f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-gold-confidence", type=float, default=0.0)
    parser.add_argument("--examples-per-skill", type=int, default=6)
    parser.add_argument("--json-out", default=str(JSON_FILE))
    parser.add_argument("--md-out", default=str(REPORT_FILE))
    args = parser.parse_args()

    payload = evaluate(args.min_gold_confidence)
    Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.md_out).write_text(render_markdown(payload, args.examples_per_skill), encoding="utf-8")
    print(f"Wrote {args.md_out}")
    print(f"Wrote {args.json_out}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
