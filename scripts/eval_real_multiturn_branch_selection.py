#!/usr/bin/env python3
"""Evaluate branch selection on real multi-turn customer query groups."""

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

from scripts.eval_real_query_branch_selection import classify_selection, rank_branch  # noqa: E402


CALLS_PATH = ROOT / "golden_test.jsonl"
MAPPING_PATH = ROOT / "scripts" / "references" / "merged_intent_skill_mapping.json"
SKILL_DIR = ROOT / "skills" / "definitions"
REPORT_FILE = ROOT / "docs" / "real_multiturn_branch_eval.md"
JSON_FILE = ROOT / "docs" / "real_multiturn_branch_eval.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_skill(path: Path) -> dict[str, Any]:
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    raw: dict[str, Any] = {}
    for doc in docs:
        if isinstance(doc, dict):
            raw.update(doc)
    return raw


def load_intent_mapping() -> dict[str, list[str]]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {item["intent"]: list(item.get("skill_ids") or []) for item in data.get("mappings", [])}


def evaluate(max_turns: int | None) -> dict[str, Any]:
    skills = {path.stem: load_skill(path) for path in sorted(SKILL_DIR.glob("*.yaml"))}
    mapping = load_intent_mapping()
    calls = load_jsonl(CALLS_PATH)
    records: list[dict[str, Any]] = []
    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for call in calls:
        queries = [q.get("query", "").strip() for q in call.get("queries") or [] if q.get("query")]
        if max_turns is not None:
            queries = queries[:max_turns]
        context = "；".join(queries)
        if not context:
            continue
        skill_ids: list[str] = []
        for intent in call.get("gold_intents") or []:
            for sid in mapping.get(intent, []):
                if sid in skills and sid not in skill_ids:
                    skill_ids.append(sid)
        for skill_id in skill_ids:
            skill = skills[skill_id]
            branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
            if not branches:
                continue
            selected, score, runner, runner_score = rank_branch(context, branches)
            record = {
                "call_id": call.get("call_id"),
                "gold_intents": call.get("gold_intents") or [],
                "gold_skill": skill_id,
                "skill_name": skill.get("name") or skill_id,
                "query_count": len(queries),
                "context": context,
                "status": classify_selection(selected, score, runner_score),
                "selected_variant": selected,
                "score": score,
                "runner_up_variant": runner,
                "runner_up_score": runner_score,
                "branch_count": len(branches),
            }
            records.append(record)
            by_skill[skill_id].append(record)

    skill_summaries = []
    for skill_id, skill in sorted(skills.items()):
        branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
        if not branches:
            continue
        skill_records = by_skill.get(skill_id, [])
        status = Counter(r["status"] for r in skill_records)
        selected = Counter(r["selected_variant"] for r in skill_records if r.get("selected_variant"))
        skill_summaries.append(
            {
                "skill_id": skill_id,
                "name": skill.get("name") or skill_id,
                "branch_count": len(branches),
                "real_context_count": len(skill_records),
                "status_counts": dict(status),
                "selected_branch_counts": dict(selected),
            }
        )
    status = Counter(r["status"] for r in records)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(CALLS_PATH.relative_to(ROOT)),
        "intent_mapping": str(MAPPING_PATH.relative_to(ROOT)),
        "max_turns": max_turns,
        "summary": {
            "call_count": len(calls),
            "evaluated_skill_contexts": len(records),
            "branch_skills_with_context": sum(1 for s in skill_summaries if s["real_context_count"] > 0),
            "confident": status.get("confident", 0),
            "low_confidence": status.get("low_confidence", 0),
            "no_select": status.get("no_select", 0),
        },
        "skills": skill_summaries,
        "records": records,
    }


def _short(text: str, limit: int = 100) -> str:
    text = str(text or "").replace("|", "｜").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def render_markdown(payload: dict[str, Any], examples_per_skill: int) -> str:
    summary = payload["summary"]
    lines = [
        "# 真实多轮 Query Branch 选择效果",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 数据源：`{payload['source']}`；intent→skill 映射：`{payload['intent_mapping']}`。",
        f"- 口径：同一通电话内客户 query 合并为上下文，再在 gold skill 的 branch 树中选择最接近分支。",
        "- 说明：仍然没有 gold branch 标签，因此这是分支可分性/命中清晰度检查。",
        "",
        "## 总览",
        "",
        f"- 通电话数：{summary['call_count']}；评估 skill-context：{summary['evaluated_skill_contexts']}。",
        f"- 有真实上下文的 branch skill：{summary['branch_skills_with_context']}。",
        f"- confident：{summary['confident']}；low_confidence：{summary['low_confidence']}；no_select：{summary['no_select']}。",
        "",
        "## Skill 汇总",
        "",
        "| skill_id | 名称 | branch | contexts | confident | low | no_select | top branches |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    records_by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in payload["records"]:
        records_by_skill[record["gold_skill"]].append(record)
    for skill in payload["skills"]:
        if skill["real_context_count"] == 0:
            continue
        counts = skill["status_counts"]
        top = "；".join(f"`{k}` {v}" for k, v in Counter(skill["selected_branch_counts"]).most_common(4)) or "-"
        lines.append(
            f"| `{skill['skill_id']}` | {skill['name']} | {skill['branch_count']} | {skill['real_context_count']} | "
            f"{counts.get('confident', 0)} | {counts.get('low_confidence', 0)} | {counts.get('no_select', 0)} | {top} |"
        )
    lines.extend(["", "## 抽样明细", ""])
    for skill in payload["skills"]:
        records = records_by_skill.get(skill["skill_id"], [])
        if not records:
            continue
        confident = sorted([r for r in records if r["status"] == "confident"], key=lambda r: (-r["score"], r["context"]))
        weak = sorted([r for r in records if r["status"] != "confident"], key=lambda r: (r["score"], r["context"]))
        sample = confident[:examples_per_skill]
        if weak:
            sample = sample[: max(0, examples_per_skill - min(2, len(weak)))] + weak[:2]
        counts = Counter(r["status"] for r in records)
        lines.append(f"### `{skill['skill_id']}` {skill['name']}")
        lines.append(f"- contexts：{len(records)}；confident：{counts.get('confident', 0)}；low_confidence：{counts.get('low_confidence', 0)}；no_select：{counts.get('no_select', 0)}。")
        lines.append("| customer context | selected branch | status | score | runner_up |")
        lines.append("|---|---|---|---:|---|")
        for r in sample:
            lines.append(
                f"| {_short(r['context'])} | `{r['selected_variant'] or '-'}` | {r['status']} | "
                f"{r['score']:.3f} | `{r['runner_up_variant'] or '-'}` {r['runner_up_score']:.3f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--examples-per-skill", type=int, default=6)
    parser.add_argument("--json-out", default=str(JSON_FILE))
    parser.add_argument("--md-out", default=str(REPORT_FILE))
    args = parser.parse_args()
    payload = evaluate(args.max_turns)
    Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.md_out).write_text(render_markdown(payload, args.examples_per_skill), encoding="utf-8")
    print(f"Wrote {args.md_out}")
    print(f"Wrote {args.json_out}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
