#!/usr/bin/env python3
"""Generate progressive mock turns and smoke-test branch selection.

This is an offline guardrail for the YAML skill trees. The runtime only
deterministically selects branch_conditions with evaluable `expr`; hint-only
branches are passed to the LLM generator as soft context. This script builds
one progressive mock dialogue for every declared branch and checks whether a
lightweight text selector can recover the expected `variant` from the branch
hints/notes within the same skill.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fin_copilot.skills.branch_evaluator import select_branch_variant  # noqa: E402
SKILL_DIR = ROOT / "skills" / "definitions"
REPORT_FILE = ROOT / "docs" / "branch_progression_mock_eval.md"
JSON_FILE = ROOT / "docs" / "branch_progression_mock_eval.json"

PUNCT_RE = re.compile(r"[\s，。！？；：、/（）()【】\[\]\"“”‘’\-—~·,.;:!?\\]+")
ASCII_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
GENERIC_USER_RE = re.compile(r"^(你好|您好|好的|好|嗯|ok|OK|是的|对|谢谢)$")


@dataclass
class BranchCase:
    skill_id: str
    skill_name: str
    branch_index: int
    expected_variant: str
    selected_variant: str | None
    score: float
    runner_up_variant: str | None
    runner_up_score: float
    status: str
    runtime_mode: str
    expr_selected_variant: str | None
    expr_status: str
    expr_slots: dict[str, Any]
    turns: list[str]
    hint: str
    expr: str
    note: str


def load_yaml(path: Path) -> dict[str, Any]:
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    raw: dict[str, Any] = {}
    for doc in docs:
        if isinstance(doc, dict):
            raw.update(doc)
    return raw


def normalize(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("XX", "").replace("xxxx", "").replace("XXXX", "")
    text = text.lower()
    return PUNCT_RE.sub("", text)


def char_ngrams(value: Any, n: int) -> set[str]:
    text = normalize(value)
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def ascii_tokens(value: Any) -> set[str]:
    return {m.group(0).lower() for m in ASCII_WORD_RE.finditer(str(value or ""))}


def feature_set(value: Any) -> set[str]:
    text = str(value or "")
    features = set()
    features.update(char_ngrams(text, 2))
    features.update(char_ngrams(text, 3))
    features.update(ascii_tokens(text))
    return {f for f in features if f}


def branch_text(branch: dict[str, Any]) -> str:
    return "\n".join(
        str(branch.get(key) or "")
        for key in ("hint", "expr", "note")
    )


def overlap_score(query: str, branch: dict[str, Any]) -> float:
    qf = feature_set(query)
    bf = feature_set(branch_text(branch))
    if not qf or not bf:
        return 0.0
    overlap = len(qf & bf)
    recall = overlap / len(qf)
    precision = overlap / len(bf)
    return round((0.65 * recall) + (0.35 * precision), 4)


def select_branch(text: str, branches: list[dict[str, Any]]) -> tuple[str | None, float, str | None, float]:
    scored: list[tuple[float, str | None]] = []
    for branch in branches:
        scored.append((overlap_score(text, branch), branch.get("variant")))
    scored.sort(reverse=True, key=lambda item: item[0])
    best_score, best_variant = scored[0] if scored else (0.0, None)
    runner_score, runner_variant = scored[1] if len(scored) > 1 else (0.0, None)
    if best_score < 0.18:
        return None, best_score, runner_variant, runner_score
    return best_variant, best_score, runner_variant, runner_score


def first_business_example(skill: dict[str, Any]) -> str:
    triggers = skill.get("triggers") or {}
    for item in triggers.get("examples") or []:
        item = str(item).strip()
        if item and not GENERIC_USER_RE.match(item):
            return item
    for item in triggers.get("keywords") or []:
        item = str(item).strip()
        if item:
            return f"我想咨询{item}"
    return f"我想咨询{skill.get('name') or skill.get('skill_id')}"


def clean_for_utterance(text: str, *, max_len: int = 90) -> str:
    text = re.sub(r"\s+", "，", str(text or "").strip())
    text = text.strip("，。；; ")
    if len(text) > max_len:
        text = text[:max_len].rstrip("，。；; ") + "..."
    return text


def branch_progression_turns(skill: dict[str, Any], branch: dict[str, Any]) -> list[str]:
    name = str(skill.get("name") or skill.get("skill_id") or "这个问题")
    opening = first_business_example(skill)
    clarify = f"是的，我想继续处理{name}这个问题。"
    branch_line = clean_for_utterance(branch.get("hint") or branch.get("note") or branch.get("expr"))
    note_line = clean_for_utterance(branch.get("note") or branch.get("hint") or branch.get("expr"))
    if note_line and note_line != branch_line:
        final = f"我的情况是：{branch_line}。补充一下，{note_line}"
    else:
        final = f"我的情况是：{branch_line}"
    return [opening, clarify, final]


def expr_names(expr: str) -> set[str]:
    if not expr:
        return set()
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def expr_has_bare_compare_constant(expr: str) -> bool:
    if not expr:
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if any(isinstance(comp, ast.Name) for comp in node.comparators):
            return True
    return False


def likely_runtime_mode(branch: dict[str, Any]) -> str:
    expr = str(branch.get("expr") or "")
    hint = str(branch.get("hint") or "")
    if not expr:
        return "hint_soft"
    if expr_has_bare_compare_constant(expr):
        return "expr_needs_slots_or_quotes"
    if hint:
        return "expr_or_hint"
    return "expr_runtime"


def _merge_numeric_constraint(current: Any, op: ast.cmpop, value: int | float) -> int | float:
    if isinstance(op, ast.Eq):
        return value
    if isinstance(op, (ast.LtE, ast.Lt)):
        candidate = value if isinstance(op, ast.LtE) else value - 1
        return min(current, candidate) if isinstance(current, (int, float)) else candidate
    if isinstance(op, (ast.GtE, ast.Gt)):
        candidate = value if isinstance(op, ast.GtE) else value + 1
        return max(current, candidate) if isinstance(current, (int, float)) else candidate
    return current


def _fill_slots_for_node(node: ast.AST, slots: dict[str, Any]) -> None:
    if isinstance(node, ast.Expression):
        _fill_slots_for_node(node.body, slots)
        return
    if isinstance(node, ast.BoolOp):
        # For branch mock slots, satisfy all AND terms; for OR, satisfying the
        # first term is enough to make the branch selectable.
        values = node.values if isinstance(node.op, ast.And) else node.values[:1]
        for value in values:
            _fill_slots_for_node(value, slots)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        if isinstance(node.operand, ast.Name):
            slots[node.operand.id] = False
        return
    if isinstance(node, ast.Name):
        slots.setdefault(node.id, True)
        return
    if isinstance(node, ast.Compare):
        if not isinstance(node.left, ast.Name):
            return
        left = node.left.id
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(comp, ast.Constant):
                if isinstance(op, ast.Eq):
                    slots[left] = comp.value
                elif isinstance(comp.value, (int, float)):
                    slots[left] = _merge_numeric_constraint(slots.get(left), op, comp.value)
            elif isinstance(comp, ast.List) and isinstance(op, (ast.In, ast.NotIn)):
                constants = [elt.value for elt in comp.elts if isinstance(elt, ast.Constant)]
                if constants:
                    slots[left] = constants[0] if isinstance(op, ast.In) else f"not_{constants[0]}"
        return


def synthesize_expr_slots(expr: str) -> dict[str, Any]:
    if not expr:
        return {}
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return {}
    slots: dict[str, Any] = {}
    _fill_slots_for_node(tree, slots)
    return slots


def evaluate_skill(path: Path) -> tuple[dict[str, Any], list[BranchCase]]:
    skill = load_yaml(path)
    branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
    cases: list[BranchCase] = []
    for idx, branch in enumerate(branches):
        expected = str(branch.get("variant") or f"branch_{idx}")
        turns = branch_progression_turns(skill, branch)
        selected, score, runner, runner_score = select_branch("\n".join(turns), branches)
        margin = score - runner_score
        if selected == expected and score >= 0.26 and margin >= 0.03:
            status = "pass"
        elif selected == expected:
            status = "low_confidence"
        else:
            status = "fail"
        expr = str(branch.get("expr") or "")
        expr_slots = synthesize_expr_slots(expr)
        expr_selected: str | None = None
        if expr:
            expr_selected, _ = select_branch_variant(branches, expr_slots)
            expr_status = "pass" if expr_selected == expected else "fail"
        else:
            expr_status = "not_applicable"
        cases.append(
            BranchCase(
                skill_id=str(skill.get("skill_id") or path.stem),
                skill_name=str(skill.get("name") or path.stem),
                branch_index=idx,
                expected_variant=expected,
                selected_variant=selected,
                score=score,
                runner_up_variant=runner,
                runner_up_score=runner_score,
                status=status,
                runtime_mode=likely_runtime_mode(branch),
                expr_selected_variant=expr_selected,
                expr_status=expr_status,
                expr_slots=expr_slots,
                turns=turns,
                hint=str(branch.get("hint") or ""),
                expr=expr,
                note=str(branch.get("note") or ""),
            )
        )
    return skill, cases


def case_to_json(case: BranchCase) -> dict[str, Any]:
    return {
        "skill_id": case.skill_id,
        "skill_name": case.skill_name,
        "branch_index": case.branch_index,
        "expected_variant": case.expected_variant,
        "selected_variant": case.selected_variant,
        "score": case.score,
        "runner_up_variant": case.runner_up_variant,
        "runner_up_score": case.runner_up_score,
        "status": case.status,
        "runtime_mode": case.runtime_mode,
        "expr_selected_variant": case.expr_selected_variant,
        "expr_status": case.expr_status,
        "expr_slots": case.expr_slots,
        "turns": case.turns,
        "hint": case.hint,
        "expr": case.expr,
        "note": case.note,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Skill Branch 递进话术 Mock 评测",
        "",
        f"- 生成时间：{payload['generated_at']}",
        "- 口径：每个 `branch_conditions` 生成一组递进用户话术，在同一个 skill 内选择最匹配 branch，检查是否回到预期 `variant`。",
        "- 注意：这是离线 smoke test；生产链路中 `expr` 可确定性选择，`hint` 分支仍是传给 LLM 的软提示。",
        "",
        "## 总览",
        "",
        f"- Skill 总数：{payload['summary']['skill_count']}；有分支 skill：{payload['summary']['skills_with_branches']}；无分支 skill：{payload['summary']['skills_without_branches']}。",
        f"- Branch case：{payload['summary']['case_count']}；通过：{payload['summary']['pass']}；低置信：{payload['summary']['low_confidence']}；失败：{payload['summary']['fail']}。",
        f"- Expr 确定性分支：{payload['summary']['expr_case_count']}；实际 evaluator 通过：{payload['summary']['expr_pass']}；失败：{payload['summary']['expr_fail']}。",
        f"- Runtime 口径：expr_runtime={payload['summary']['runtime_modes'].get('expr_runtime', 0)}，expr_or_hint={payload['summary']['runtime_modes'].get('expr_or_hint', 0)}，expr_needs_slots_or_quotes={payload['summary']['runtime_modes'].get('expr_needs_slots_or_quotes', 0)}，hint_soft={payload['summary']['runtime_modes'].get('hint_soft', 0)}。",
        "",
        "## 异常清单",
        "",
    ]
    flagged = [
        c for c in payload["cases"]
        if c["status"] != "pass" or c["runtime_mode"] == "expr_needs_slots_or_quotes" or c["expr_status"] == "fail"
    ]
    if not flagged:
        lines.append("- 未发现错选、低置信或明显 expr 风险。")
    else:
        lines.append("| skill_id | branch | 结果 | selected | expr | score | runner_up | runtime | mock 末轮 |")
        lines.append("|---|---|---|---|---|---:|---|---|---|")
        for c in flagged[:120]:
            final_turn = c["turns"][-1].replace("|", "｜")
            if len(final_turn) > 70:
                final_turn = final_turn[:70] + "..."
            lines.append(
                f"| `{c['skill_id']}` | `{c['expected_variant']}` | {c['status']} | "
                f"`{c['selected_variant'] or '-'}` | {c['expr_status']} → `{c['expr_selected_variant'] or '-'}` | {c['score']:.3f} | "
                f"`{c['runner_up_variant'] or '-'}` {c['runner_up_score']:.3f} | "
                f"{c['runtime_mode']} | {final_turn} |"
            )
        if len(flagged) > 120:
            lines.append(f"- 仅展示前 120 条，完整见 JSON。")
    lines.extend(["", "## 逐个 Skill", ""])
    by_skill: dict[str, list[dict[str, Any]]] = {}
    for c in payload["cases"]:
        by_skill.setdefault(c["skill_id"], []).append(c)
    no_branch = payload["skills_without_branch_details"]
    for item in payload["skills"]:
        sid = item["skill_id"]
        cases = by_skill.get(sid, [])
        if not cases:
            lines.append(f"### `{sid}` {item['name']}")
            lines.append("- 无 `branch_conditions`，跳过 branch mock。")
            lines.append("")
            continue
        pass_count = sum(1 for c in cases if c["status"] == "pass")
        low_count = sum(1 for c in cases if c["status"] == "low_confidence")
        fail_count = sum(1 for c in cases if c["status"] == "fail")
        lines.append(f"### `{sid}` {item['name']}")
        expr_cases = [c for c in cases if c["expr_status"] != "not_applicable"]
        expr_pass = sum(1 for c in expr_cases if c["expr_status"] == "pass")
        lines.append(f"- 分支：{len(cases)}；通过：{pass_count}；低置信：{low_count}；失败：{fail_count}；expr evaluator：{expr_pass}/{len(expr_cases)}。")
        lines.append("| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |")
        lines.append("|---|---|---|---:|---|---|")
        for c in cases:
            final_turn = c["turns"][-1].replace("|", "｜")
            if len(final_turn) > 80:
                final_turn = final_turn[:80] + "..."
            lines.append(
                f"| `{c['expected_variant']}` | `{c['selected_variant'] or '-'}` | "
                f"`{c['expr_selected_variant'] or '-'}` | {c['score']:.3f} | {c['runtime_mode']} | {final_turn} |"
            )
        lines.append("")
    if no_branch:
        lines.extend(["## 无分支 Skill", ""])
        lines.append(", ".join(f"`{item['skill_id']}`" for item in no_branch))
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default=str(JSON_FILE))
    parser.add_argument("--md-out", default=str(REPORT_FILE))
    args = parser.parse_args()

    skills: list[dict[str, str]] = []
    no_branch: list[dict[str, str]] = []
    cases: list[BranchCase] = []
    for path in sorted(SKILL_DIR.glob("*.yaml")):
        skill, skill_cases = evaluate_skill(path)
        item = {
            "skill_id": str(skill.get("skill_id") or path.stem),
            "name": str(skill.get("name") or path.stem),
        }
        skills.append(item)
        if skill_cases:
            cases.extend(skill_cases)
        else:
            no_branch.append(item)

    runtime_modes: dict[str, int] = {}
    for c in cases:
        runtime_modes[c.runtime_mode] = runtime_modes.get(c.runtime_mode, 0) + 1
    expr_cases = [c for c in cases if c.expr_status != "not_applicable"]
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "skill_count": len(skills),
            "skills_with_branches": len(skills) - len(no_branch),
            "skills_without_branches": len(no_branch),
            "case_count": len(cases),
            "pass": sum(1 for c in cases if c.status == "pass"),
            "low_confidence": sum(1 for c in cases if c.status == "low_confidence"),
            "fail": sum(1 for c in cases if c.status == "fail"),
            "expr_case_count": len(expr_cases),
            "expr_pass": sum(1 for c in expr_cases if c.expr_status == "pass"),
            "expr_fail": sum(1 for c in expr_cases if c.expr_status == "fail"),
            "runtime_modes": runtime_modes,
        },
        "skills": skills,
        "skills_without_branch_details": no_branch,
        "cases": [case_to_json(c) for c in cases],
    }

    json_path = Path(args.json_out)
    md_path = Path(args.md_out)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
