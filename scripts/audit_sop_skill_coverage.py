#!/usr/bin/env python3
"""Audit direct XLSX SOP to YAML skill coverage.

The user-facing question here is not whether RAG chunks exist. It is whether
each original xlsx SOP has been abstracted into the corresponding YAML skill
tree with enough triggers, branches, templates, and compliance notes.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
import yaml


ROOT = Path(__file__).resolve().parents[1]
MAPPING_DOC = ROOT / "docs" / "skill-sop.md"
SKILL_DIR = ROOT / "skills" / "definitions"
REPORT_FILE = ROOT / "docs" / "sop_skill_coverage_audit.md"
JSON_FILE = ROOT / "docs" / "sop_skill_coverage_audit.json"

GENERIC_STEP_RE = re.compile(
    r"(开头语|验证用户信息|核身|确认客户问题|确认客户订单|确认客户信息|"
    r"询问用户是否还有其他问题|邀评|结束语|询问客户姓氏)"
)
GENERIC_QUERY_RE = re.compile(r"^(你好|您好|好的|好|嗯|嗯好|谢谢|ok|OK|是的|对|好了)[/，。！？、\s]*(.*)?$")
PUNCT_RE = re.compile(r"[\s，。！？；：、/（）()【】\[\]\"“”‘’\-—~·,.;:!?\\]+")


def normalize(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("XX", "").replace("xxxx", "").replace("XXXX", "")
    text = text.lower()
    return PUNCT_RE.sub("", text)


def bigrams(value: Any) -> set[str]:
    text = normalize(value)
    return {text[i : i + 2] for i in range(max(0, len(text) - 1)) if len(text[i : i + 2]) == 2}


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "\n".join(flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(flatten_text(v) for v in value)
    return str(value)


def parse_mapping() -> dict[str, dict[str, Any]]:
    """Parse only xlsx mappings from docs/skill-sop.md."""
    rows: dict[str, dict[str, Any]] = {}
    for raw_line in MAPPING_DOC.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        skill_match = re.search(r"`([^`]+)`", cells[0])
        if not skill_match:
            continue
        skill_id = skill_match.group(1)
        xlsx_paths = [
            item
            for item in re.findall(r"`([^`]+\.xlsx)`", cells[4])
            if item.startswith("sop/")
        ]
        rows[skill_id] = {
            "skill_id": skill_id,
            "name": cells[1],
            "route_risk": cells[2],
            "intent": cells[3],
            "xlsx_paths": xlsx_paths,
            "mapping_note": cells[5],
        }
    return rows


def load_yaml(skill_id: str) -> tuple[dict[str, Any], str]:
    path = SKILL_DIR / f"{skill_id}.yaml"
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}, text


def row_is_header(values: list[Any]) -> bool:
    joined = "|".join(str(v or "") for v in values[:5])
    return "步骤" in joined and "用户问句" in joined


def read_xlsx_rows(path: Path) -> list[dict[str, Any]]:
    """Read original xlsx rows and forward-fill merged/blank logical cells."""
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    records: list[dict[str, Any]] = []
    for sheet in wb.worksheets:
        last_step = ""
        last_query = ""
        last_notes = ""
        for raw_values in sheet.iter_rows(values_only=True):
            values = list(raw_values[:5]) + [None] * max(0, 5 - len(raw_values))
            if not any(v not in (None, "") for v in values):
                continue
            if row_is_header(values):
                continue

            step, query, response, notes, solution = values[:5]
            if step not in (None, ""):
                last_step = str(step).strip()
            if query not in (None, ""):
                last_query = str(query).strip()
            if notes not in (None, ""):
                last_notes = str(notes).strip()

            record = {
                "file": str(path.relative_to(ROOT)),
                "sheet": sheet.title,
                "step": str(step).strip() if step not in (None, "") else last_step,
                "user_query": str(query).strip() if query not in (None, "") else last_query,
                "response": str(response).strip() if response not in (None, "") else "",
                "notes": str(notes).strip() if notes not in (None, "") else last_notes,
                "solution": str(solution).strip() if solution not in (None, "") else "",
            }
            if any(record[key] for key in ["step", "user_query", "response", "notes", "solution"]):
                records.append(record)
    return records


def is_generic_row(row: dict[str, Any]) -> bool:
    step = str(row.get("step") or "")
    query = str(row.get("user_query") or "").strip()
    if GENERIC_STEP_RE.search(step):
        return True
    return bool(GENERIC_QUERY_RE.match(query))


def split_query_fragments(text: str) -> list[str]:
    parts = re.split(r"[/，。！？；：、()（）【】\[\]\"“”‘’\n]+", text or "")
    fragments: list[str] = []
    for part in parts:
        part = part.strip()
        if len(normalize(part)) < 4:
            continue
        if GENERIC_QUERY_RE.match(part):
            continue
        fragments.append(part)
    return fragments


def score_row_against_yaml(row: dict[str, Any], yaml_norm: str, yaml_bigrams: set[str]) -> dict[str, Any]:
    query = str(row.get("user_query") or "")
    probe = "\n".join(str(row.get(key) or "") for key in ["step", "user_query", "notes", "solution", "response"])
    grams = bigrams(probe[:900])
    gram_score = (sum(1 for gram in grams if gram in yaml_bigrams) / len(grams)) if grams else 0.0

    exact_hits = []
    for fragment in split_query_fragments(query):
        normalized = normalize(fragment)
        if normalized and normalized in yaml_norm:
            exact_hits.append(fragment)

    step_hit = bool(normalize(row.get("step")) and normalize(row.get("step")) in yaml_norm)
    solution_hit = bool(normalize(row.get("solution")) and normalize(row.get("solution"))[:20] in yaml_norm)
    covered = bool(exact_hits or step_hit or solution_hit or gram_score >= 0.24)
    return {
        "covered": covered,
        "gram_score": round(gram_score, 3),
        "exact_hits": exact_hits[:3],
        "step_hit": step_hit,
        "solution_hit": solution_hit,
    }


def audit() -> list[dict[str, Any]]:
    mapping = parse_mapping()
    results: list[dict[str, Any]] = []
    missing_files: list[str] = []

    for skill_id, item in sorted(mapping.items()):
        yaml_data, yaml_text = load_yaml(skill_id)
        yaml_all_text = flatten_text(yaml_data)
        yaml_norm = normalize(yaml_all_text)
        yaml_bg = bigrams(yaml_all_text)

        xlsx_rows: list[dict[str, Any]] = []
        for xlsx_path in item["xlsx_paths"]:
            path = ROOT / xlsx_path
            if not path.exists():
                missing_files.append(xlsx_path)
                continue
            xlsx_rows.extend(read_xlsx_rows(path))

        business_rows = [row for row in xlsx_rows if not is_generic_row(row)]
        row_scores = [
            {
                "file": row["file"],
                "sheet": row["sheet"],
                "step": row.get("step") or "",
                "user_query": row.get("user_query") or "",
                **score_row_against_yaml(row, yaml_norm, yaml_bg),
            }
            for row in business_rows
        ]

        covered_count = sum(1 for row in row_scores if row["covered"])
        business_count = len(row_scores)
        coverage_rate = covered_count / business_count if business_count else None

        branch_count = len(yaml_data.get("branch_conditions") or [])
        trigger_count = len((yaml_data.get("triggers") or {}).get("keywords") or []) + len(
            (yaml_data.get("triggers") or {}).get("examples") or []
        )
        template_count = len(yaml_data.get("templates") or {})
        tool_count = len((yaml_data.get("tools") or {}).get("required") or []) + len(
            (yaml_data.get("tools") or {}).get("optional") or []
        )

        risk_text = item["route_risk"]
        is_high_risk_skill = "high" in risk_text
        if not item["xlsx_paths"]:
            severity = "共性抽象"
            reason = "无独立 xlsx SOP，属于跨域共性 skill，本报告不按 xlsx 覆盖评价。"
        elif business_count == 0:
            severity = "低"
            reason = "xlsx 中除开场/核身/结束等通用节点外，业务行很少。"
        elif is_high_risk_skill and coverage_rate is not None and coverage_rate < 0.25 and business_count >= 3:
            severity = "高"
            reason = "高风险业务的 xlsx 关键问句在 YAML 中几乎没有形成可见主干。"
        elif coverage_rate is not None and coverage_rate < 0.35 and business_count >= 6:
            severity = "高"
            reason = "xlsx 业务行与 YAML 主干匹配弱，可能只保留了场景名或少数泛化分支。"
        elif is_high_risk_skill and coverage_rate is not None and coverage_rate < 0.55 and business_count >= 3:
            severity = "中"
            reason = "高风险业务存在低匹配 xlsx 问句，需确认是否只靠泛化回复承接。"
        elif coverage_rate is not None and coverage_rate < 0.55 and business_count >= 8:
            severity = "中"
            reason = "有一批 xlsx 问句/分支未在 YAML 中形成可见触发或分支。"
        elif coverage_rate is not None and coverage_rate < 0.35 and business_count >= 3:
            severity = "中"
            reason = "业务行数量不大，但核心问句与 YAML 主干匹配弱，建议抽查。"
        elif branch_count <= 3 and business_count >= 12:
            severity = "中"
            reason = "xlsx 业务行较多，但 YAML 分支数量偏少，建议人工复核。"
        else:
            severity = "低"
            reason = "YAML 对主要 xlsx 业务问法/分支有较明显覆盖。"

        weak_examples = [
            row
            for row in sorted(row_scores, key=lambda row: row["gram_score"])
            if not row["covered"]
        ][:5]
        strong_examples = [
            row
            for row in sorted(row_scores, key=lambda row: row["gram_score"], reverse=True)
            if row["covered"]
        ][:3]

        results.append(
            {
                **item,
                "xlsx_files": item["xlsx_paths"],
                "total_xlsx_rows": len(xlsx_rows),
                "business_rows": business_count,
                "covered_business_rows": covered_count,
                "coverage_rate": round(coverage_rate, 3) if coverage_rate is not None else None,
                "branch_count": branch_count,
                "trigger_count": trigger_count,
                "template_count": template_count,
                "tool_count": tool_count,
                "severity": severity,
                "reason": reason,
                "weak_examples": weak_examples,
                "strong_examples": strong_examples,
            }
        )

    if missing_files:
        results.append({"missing_files": sorted(missing_files)})
    return results


def fmt_rate(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def render_markdown(results: list[dict[str, Any]]) -> str:
    rows = [row for row in results if "skill_id" in row]
    order = {"高": 0, "中": 1, "低": 2, "共性抽象": 3}
    sorted_rows = sorted(rows, key=lambda row: (order.get(row["severity"], 9), row["skill_id"]))

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["severity"]] += 1

    high_or_mid = [row for row in sorted_rows if row["severity"] in {"高", "中"}]
    xlsx_count = len({path for row in rows for path in row["xlsx_paths"]})

    lines: list[str] = []
    lines.append("# XLSX SOP 到 YAML Skill 覆盖度审计")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("- 审计口径：直接读取 `docs/skill-sop.md` 中映射的原始 `.xlsx` SOP，并与对应 `skills/definitions/*.yaml` 对比。")
    lines.append("- 本报告不使用 `sop/clean/*` 的 chunk 作为判断依据；chunk 只属于运行时 RAG/清洗链路，不作为这次覆盖度口径。")
    lines.append("- Excel 读取说明：对合并单元格/空白逻辑单元做向下填充；开场、核身、确认、结束语等通用步骤不计入业务覆盖率。")
    lines.append("- 注意：这是启发式文本覆盖检查，用来发现“YAML 话术树抽象过薄”的风险；最终仍需人工确认语义。")
    lines.append("")
    lines.append("## 结论概览")
    lines.append("")
    lines.append(f"- 覆盖对象：{len(rows)} 个 skill，其中 {counts['共性抽象']} 个无独立 xlsx；直接检查了 {xlsx_count} 份 xlsx SOP。")
    lines.append(f"- 高风险：{counts['高']} 个；中风险：{counts['中']} 个；低风险：{counts['低']} 个；共性抽象：{counts['共性抽象']} 个。")
    if high_or_mid:
        lines.append("- 优先处理：先补高风险 skill 的 `triggers.examples` 和 `branch_conditions`，再看中风险。")
    else:
        lines.append("- 当前未发现高/中风险项；后续可按业务重要度继续人工精修低风险项。")
    lines.append("")
    lines.append("## 高/中风险清单")
    lines.append("")
    lines.append("| 等级 | skill_id | 名称 | xlsx 行 | 业务行覆盖 | YAML 分支/触发 | 主要原因 |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    for row in high_or_mid:
        lines.append(
            "| {severity} | `{skill_id}` | {name} | {total_rows} | {covered}/{business} ({rate}) | {branches}/{triggers} | {reason} |".format(
                severity=row["severity"],
                skill_id=row["skill_id"],
                name=row["name"],
                total_rows=row["total_xlsx_rows"],
                covered=row["covered_business_rows"],
                business=row["business_rows"],
                rate=fmt_rate(row["coverage_rate"]),
                branches=row["branch_count"],
                triggers=row["trigger_count"],
                reason=row["reason"],
            )
        )
    if not high_or_mid:
        lines.append("| - | - | - | - | - | - | 未发现高/中风险项 |")
    lines.append("")
    lines.append("## 逐个 Skill 结果")
    lines.append("")

    for row in sorted_rows:
        lines.append(f"### {row['severity']} `{row['skill_id']}` {row['name']}")
        sop = "；".join(row["xlsx_files"]) if row["xlsx_files"] else "无独立 xlsx"
        lines.append(
            f"- XLSX：{sop}；原始行：{row['total_xlsx_rows']}，业务行：{row['business_rows']}，覆盖：{row['covered_business_rows']}/{row['business_rows']} ({fmt_rate(row['coverage_rate'])})。"
        )
        lines.append(
            f"- YAML：分支 {row['branch_count']}，触发样例/关键词 {row['trigger_count']}，模板 {row['template_count']}，工具 {row['tool_count']}。"
        )
        lines.append(f"- 判断：{row['reason']}")
        if row["weak_examples"]:
            lines.append("- 低匹配 xlsx 问句示例：")
            for example in row["weak_examples"][:3]:
                query = str(example["user_query"]).replace("\n", " ")[:90]
                step = str(example["step"]).replace("\n", " ")[:30]
                lines.append(f"  - `{example['file']}` / {step}：{query}（score={example['gram_score']}）")
        lines.append("")

    lines.append("## 后续建议")
    lines.append("")
    lines.append("1. 对高风险 skill，把低匹配 xlsx 问句归并成新的 `branch_conditions.variant`，并补充 `triggers.examples`。")
    lines.append("2. 对 xlsx 中只有少量业务行但全部低匹配的 skill，人工判断是“可泛化”还是“必须显式进树”。")
    lines.append("3. 对共性抽象 skill 单独按“跨 xlsx 重复步骤”审计，不和业务 xlsx 一起算覆盖率。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    results = audit()
    JSON_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_FILE.write_text(render_markdown(results), encoding="utf-8")
    print(f"Wrote {REPORT_FILE}")
    print(f"Wrote {JSON_FILE}")


if __name__ == "__main__":
    main()
