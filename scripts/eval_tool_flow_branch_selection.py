#!/usr/bin/env python3
"""Evaluate branch selection after mock tool execution.

This skips skill routing entirely:
  real query + gold_skill -> verified mock customer -> execute mock tools ->
  merge tool results + lightweight extracted slots -> select branch.

The deterministic result uses the real runtime function
`select_branch_variant`. Hint-only branches are still LLM-soft in production,
so this script also records a lightweight text candidate for them as
`semantic_candidate_variant`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fin_copilot.skills.branch_evaluator import select_branch_variant  # noqa: E402
from scripts.eval_real_query_branch_selection import rank_branch, classify_selection  # noqa: E402
from tools.executor import execute_tools  # noqa: E402
from tools.registry import TOOL_REGISTRY_META  # noqa: E402


GOLDEN_PATH = ROOT / "raw_test.jsonl"
SKILL_DIR = ROOT / "skills" / "definitions"
REPORT_FILE = ROOT / "docs" / "tool_flow_branch_eval.md"
JSON_FILE = ROOT / "docs" / "tool_flow_branch_eval.json"

PERSONAS = {
    "C100": "张三-逾期45天",
    "C101": "李四-正常还款",
    "C102": "王五-轻逾期/额度冻结",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_skill(path: Path) -> dict[str, Any]:
    docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    raw: dict[str, Any] = {}
    for doc in docs:
        if isinstance(doc, dict):
            raw.update(doc)
    return raw


def tool_scope_for_skill(skill: dict[str, Any], scope: str) -> list[str]:
    tools = skill.get("tools") or {}
    names: list[str] = list(tools.get("required") or [])
    if scope == "read-all":
        for name in tools.get("optional") or []:
            if TOOL_REGISTRY_META.get(name, {}).get("permission") == "read" and name not in names:
                names.append(name)
    return [name for name in names if name in TOOL_REGISTRY_META]


def flatten_tool_slots(tool_results: dict[str, Any]) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    for result in tool_results.values():
        if isinstance(result, dict):
            slots.update(result)
    overdue_days = slots.get("overdue_days")
    if isinstance(overdue_days, (int, float)):
        slots.setdefault("no_overdue", overdue_days <= 0)
        slots.setdefault("has_overdue", overdue_days > 0)
    loan_status = slots.get("loan_status")
    if loan_status:
        slots.setdefault("order_not_cleared", loan_status not in {"cleared", "settled", "closed"})
        slots.setdefault("order_cleared", loan_status in {"cleared", "settled", "closed"})
    return slots


def _has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _extract_days(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*天", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d{1,2})\s*个?月", text)
    if match:
        return int(match.group(1)) * 30
    return None


def extract_query_slots(query: str, skill_id: str, persona_id: str, slots: dict[str, Any]) -> dict[str, Any]:
    text = query or ""
    out: dict[str, Any] = {"customer_request": text}

    if _has_any(text, ["投诉", "生气", "不满"]):
        out["emotion"] = "angry"
    elif _has_any(text, ["担心", "着急", "急"]):
        out["emotion"] = "anxious"
    else:
        out["emotion"] = "neutral"

    if skill_id in {"collection_complaint"}:
        if _has_any(text, ["通讯录", "联系人", "亲友", "家人", "朋友"]):
            out["complaint_type"] = "expose_contacts"
        elif _has_any(text, ["威胁", "恐吓", "暴力", "上门", "法院", "短信威胁"]):
            out["complaint_type"] = "violence"
        elif _has_any(text, ["态度", "骂", "辱骂", "凶"]):
            out["complaint_type"] = "attitude"
        elif _has_any(text, ["频繁", "一直", "多次", "十几", "骚扰", "电话", "短信", "响一声"]):
            out["complaint_type"] = "frequency"

    if skill_id in {"credit_inquiry"}:
        if _has_any(text, ["非本人", "没申请", "没授权", "不是我", "莫名", "未经"]):
            out["inquiry_type"] = "unauthorized_query"
        elif _has_any(text, ["多次", "好多次", "几次", "频繁查询"]):
            out["inquiry_type"] = "multiple_queries"
        elif _has_any(text, ["逾期", "影响征信", "信用记录"]):
            out["inquiry_type"] = "overdue_impact"
        elif _has_any(text, ["上报", "报送", "多久", "规则"]):
            out["inquiry_type"] = "reporting_rules"
        elif _has_any(text, ["分数", "评分", "信用分"]):
            out["inquiry_type"] = "credit_score"
        elif _has_any(text, ["冻结", "关注状态"]):
            out["inquiry_type"] = "credit_freeze"

    if skill_id in {"credit_modification", "cancel_credit_authorization"}:
        out.setdefault("institution_type", "self_operated")
        if _has_any(text, ["资方", "银行", "第三方", "非你们", "中介"]):
            out["institution_type"] = "non_self_operated"
        if _has_any(text, ["系统错", "不是本人", "错误", "误报"]):
            out["overdue_reason"] = "genuine_error"
        elif _has_any(text, ["疾病", "住院", "灾", "疫情"]):
            out["overdue_reason"] = "major_illness_or_disaster"
        elif _has_any(text, ["忘记", "自己", "没还", "逾期"]):
            out["overdue_reason"] = "customer_own_fault"
        out["all_loans_cleared"] = bool(_has_any(text, ["全部结清", "都还清", "已还清", "还完"]))
        out["has_active_loan"] = not out["all_loans_cleared"]
        if _has_any(text, ["申请记录", "贷款记录", "授信额度"]):
            out["customer_confuses_quota_with_loan_record"] = True
        if _has_any(text, ["之前反馈", "不满意", "还没处理"]):
            out["customer_dissatisfied_with_previous_feedback"] = True
        if _has_any(text, ["哪家", "你看下", "查一下"]):
            out["customer_only_names_institution_or_loan"] = True

    if skill_id in {"invoice_issuance"}:
        out["platform"] = "kakadai" if "卡卡" in text else "doudouqian"
        out["self_service_supported"] = True
        if _has_any(text, ["本金"]):
            out["customer_asks_principal_invoice"] = True
        if _has_any(text, ["抬头", "内容", "修改"]):
            out["customer_asks_title_or_content_change"] = True
        if _has_any(text, ["不支持", "无法开具", "不能开"]):
            out["funder_or_partner_not_support_invoice"] = True
        if _has_any(text, ["不接受", "人工", "帮我开"]):
            out["customer_refuses_self_service"] = True

    if skill_id in {"clearance_certificate"}:
        if _has_any(text, ["已结清", "结清了", "还完", "还清"]):
            out["order_cleared"] = True
            out["order_not_cleared"] = False
            out["cleared_within_2_years"] = True
            out["cleared_over_2_years"] = False
        else:
            out.setdefault("order_not_cleared", slots.get("order_not_cleared", True))
        if _has_any(text, ["公章", "资方章", "官方"]):
            out["customer_requires_official_seal"] = True
        if _has_any(text, ["开不出来", "失败"]):
            out["system_issuance_failed"] = True
        if re.search(r"\d{4}年|\d{1,2}月|\d{1,2}日", text):
            out["customer_only_provides_loan_date"] = True

    if skill_id in {"contract_retrieval"}:
        if _has_any(text, ["注销"]):
            out["account_cancelled"] = True
        if _has_any(text, ["保留", "为什么没有", "发票", "个人信息"]):
            out["customer_disputes_data_retention"] = True
        if _has_any(text, ["纸质", "原件"]):
            out["customer_requires_paper_copy"] = True
        if _has_any(text, ["哪些材料", "提供什么"]):
            out["customer_asks_required_materials"] = True
        if _has_any(text, ["所有合同", "全部合同"]):
            out["customer_requires_all_contracts"] = True

    if skill_id in {"other_certificate"}:
        if _has_any(text, ["非恶意"]):
            out["certificate_type"] = "non_malicious"
        elif _has_any(text, ["逾期还款证明", "逾期证明"]):
            out["certificate_type"] = "overdue_proof"
            out["funder_supports"] = "支持" in text
        elif _has_any(text, ["放款凭证", "打款凭证"]):
            out["certificate_type"] = "loan_voucher"
        if _has_any(text, ["坚持", "必须", "一定要"]):
            out["customer_insists"] = True
        if _has_any(text, ["解冻"]):
            out["customer_requests_account_unfreeze_statement"] = True
        if _has_any(text, ["没贷款成功", "审查记录"]):
            out["no_successful_loan_but_credit_inquiry_record"] = True

    if skill_id in {"post_loan_verification"}:
        if _has_any(text, ["对公", "账号", "账户"]):
            out["verification_type"] = "account"
        elif _has_any(text, ["工号", "工作人员", "专员"]):
            out["verification_type"] = "staff_id"
        elif _has_any(text, ["机构", "调解", "法院", "中心"]):
            out["verification_type"] = "institution"

    if skill_id in {"stop_collection"}:
        if _has_any(text, ["IVR", "语音"]):
            out["collection_type"] = "IVR"
        elif _has_any(text, ["AI", "机器人", "系统"]):
            out["collection_type"] = "AI"
        days = _extract_days(text)
        if days is not None:
            out["stop_days_requested"] = days
        elif _has_any(text, ["永久", "一直", "以后都"]):
            out["stop_days_requested"] = 31
        else:
            out["stop_days_requested"] = 15
        out["target"] = "third_party" if _has_any(text, ["家人", "朋友", "联系人", "三方"]) else "self"

    if skill_id in {"close_pre_reminder"}:
        out["customer_has_multiple_orders"] = bool(_has_any(text, ["多笔", "两个", "几笔"]))
        out["ivr_shows_no_customer_info"] = bool(_has_any(text, ["没有信息", "查不到"]))
        out["customer_insists_close"] = bool(_has_any(text, ["关闭", "不要", "别提醒", "取消"]))

    return out


def choose_personas(policy: str, query: str, skill_id: str) -> list[str]:
    if policy == "all":
        return list(PERSONAS)
    text = query or ""
    if skill_id in {"no_quota_issue", "repayment_status_issue"} and _has_any(text, ["冻结", "失败", "没额度"]):
        return ["C102"]
    if skill_id in {"early_loan_clearance", "fee_refund_status"}:
        return ["C101"]
    if skill_id in {"overdue_negotiation", "collection_complaint", "stop_collection"}:
        return ["C100"]
    if _has_any(text, ["逾期", "催收", "协商", "还不上"]):
        return ["C100"]
    if _has_any(text, ["正常", "提前结清", "优质", "已结清"]):
        return ["C101"]
    return ["C100"]


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    skills = {path.stem: load_skill(path) for path in sorted(SKILL_DIR.glob("*.yaml"))}
    rows = [
        row for row in load_jsonl(GOLDEN_PATH)
        if row.get("gold_skill") in skills
        and float(row.get("confidence", 1.0)) >= args.min_gold_confidence
    ]
    if args.limit:
        rows = rows[: args.limit]

    records: list[dict[str, Any]] = []
    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        skill_id = row["gold_skill"]
        skill = skills[skill_id]
        branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
        if not branches:
            continue
        query = str(row.get("query") or "")
        tools = tool_scope_for_skill(skill, args.tool_scope)
        for persona_id in choose_personas(args.persona_policy, query, skill_id):
            state = {
                "customer": {
                    "customer_id": persona_id,
                    "verified": True,
                    "verification_level": "full",
                },
                "slots": {},
                "intent": {"current_skill_id": skill_id},
            }
            exec_result = await execute_tools(tools, state, tool_cache=None)
            tool_results = exec_result.get("tool_results", {})
            slots = flatten_tool_slots(tool_results)
            slots.update(extract_query_slots(query, skill_id, persona_id, slots))
            expr_variant, hint_branches = select_branch_variant(branches, slots)
            semantic_context = json.dumps(
                {
                    "query": query,
                    "persona": PERSONAS[persona_id],
                    "slots": slots,
                },
                ensure_ascii=False,
                default=str,
            )
            semantic_variant, semantic_score, runner, runner_score = rank_branch(semantic_context, branches)
            semantic_status = classify_selection(semantic_variant, semantic_score, runner_score)
            record = {
                "call_id": row.get("call_id"),
                "query": query,
                "gold_skill": skill_id,
                "skill_name": skill.get("name") or skill_id,
                "gold_confidence": row.get("confidence"),
                "persona_id": persona_id,
                "persona_name": PERSONAS[persona_id],
                "tools_called": tools,
                "execution_status": exec_result.get("execution_status"),
                "expr_selected_variant": expr_variant,
                "hint_branch_count": len(hint_branches),
                "semantic_candidate_variant": semantic_variant,
                "semantic_score": semantic_score,
                "semantic_runner_up_variant": runner,
                "semantic_runner_up_score": runner_score,
                "semantic_status": semantic_status,
                "slots_used": slots,
            }
            records.append(record)
            by_skill[skill_id].append(record)

    skill_summaries: list[dict[str, Any]] = []
    for skill_id, skill in sorted(skills.items()):
        branches = [br for br in skill.get("branch_conditions") or [] if isinstance(br, dict)]
        if not branches:
            continue
        skill_records = by_skill.get(skill_id, [])
        skill_summaries.append(
            {
                "skill_id": skill_id,
                "name": skill.get("name") or skill_id,
                "branch_count": len(branches),
                "record_count": len(skill_records),
                "expr_selected_count": sum(1 for r in skill_records if r["expr_selected_variant"]),
                "expr_variant_counts": dict(Counter(r["expr_selected_variant"] for r in skill_records if r["expr_selected_variant"])),
                "semantic_status_counts": dict(Counter(r["semantic_status"] for r in skill_records)),
                "semantic_variant_counts": dict(Counter(r["semantic_candidate_variant"] for r in skill_records if r["semantic_candidate_variant"])),
            }
        )
    summary_counter = Counter(r["semantic_status"] for r in records)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(GOLDEN_PATH.relative_to(ROOT)),
        "tool_scope": args.tool_scope,
        "persona_policy": args.persona_policy,
        "min_gold_confidence": args.min_gold_confidence,
        "summary": {
            "golden_rows_used": len(rows),
            "evaluated_records": len(records),
            "skills_with_records": sum(1 for s in skill_summaries if s["record_count"] > 0),
            "expr_selected": sum(1 for r in records if r["expr_selected_variant"]),
            "expr_not_selected": sum(1 for r in records if not r["expr_selected_variant"]),
            "semantic_confident": summary_counter.get("confident", 0),
            "semantic_low_confidence": summary_counter.get("low_confidence", 0),
            "semantic_no_select": summary_counter.get("no_select", 0),
        },
        "skills": skill_summaries,
        "records": records,
    }


def _short(text: str, limit: int = 80) -> str:
    text = str(text or "").replace("|", "｜").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def render_markdown(payload: dict[str, Any], examples_per_skill: int) -> str:
    summary = payload["summary"]
    lines = [
        "# Mock 工具槽位后的 Branch 选择评估",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 数据源：`{payload['source']}`。",
        "- 口径：跳过 skill 选择，使用真实 query 的 `gold_skill`；模拟已核身客户，执行 mock 工具，把工具结果和 query 抽取槽位合并后跑真实 `select_branch_variant`。",
        f"- 工具范围：`{payload['tool_scope']}`；persona 策略：`{payload['persona_policy']}`。",
        "- `expr_selected` 是生产确定性分支；`semantic_candidate` 只是 hint 分支的离线文本候选，不等价于 LLM 真实选择。",
        "",
        "## 总览",
        "",
        f"- 真实 query：{summary['golden_rows_used']}；评估记录：{summary['evaluated_records']}。",
        f"- expr selected：{summary['expr_selected']}；expr not selected：{summary['expr_not_selected']}。",
        f"- semantic candidate：confident {summary['semantic_confident']}；low {summary['semantic_low_confidence']}；no_select {summary['semantic_no_select']}。",
        "",
        "## Skill 汇总",
        "",
        "| skill_id | 名称 | records | expr selected | expr top | semantic top |",
        "|---|---|---:|---:|---|---|",
    ]
    records_by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in payload["records"]:
        records_by_skill[record["gold_skill"]].append(record)
    for skill in payload["skills"]:
        if skill["record_count"] == 0:
            continue
        expr_top = "；".join(f"`{k}` {v}" for k, v in Counter(skill["expr_variant_counts"]).most_common(4)) or "-"
        sem_top = "；".join(f"`{k}` {v}" for k, v in Counter(skill["semantic_variant_counts"]).most_common(4)) or "-"
        lines.append(
            f"| `{skill['skill_id']}` | {skill['name']} | {skill['record_count']} | "
            f"{skill['expr_selected_count']} | {expr_top} | {sem_top} |"
        )
    lines.extend(["", "## 抽样明细", ""])
    for skill in payload["skills"]:
        records = records_by_skill.get(skill["skill_id"], [])
        if not records:
            continue
        selected = [r for r in records if r["expr_selected_variant"]]
        unselected = [r for r in records if not r["expr_selected_variant"]]
        sample = selected[:examples_per_skill]
        if unselected:
            sample = sample[: max(0, examples_per_skill - min(2, len(unselected)))] + unselected[:2]
        lines.append(f"### `{skill['skill_id']}` {skill['name']}")
        lines.append(f"- records：{len(records)}；expr selected：{len(selected)}；not selected：{len(unselected)}。")
        lines.append("| query | persona | expr selected | semantic candidate | score | key slots |")
        lines.append("|---|---|---|---|---:|---|")
        for r in sample:
            key_slots = {
                k: r["slots_used"].get(k)
                for k in [
                    "overdue_days",
                    "loan_status",
                    "repayment_status",
                    "complaint_type",
                    "inquiry_type",
                    "institution_type",
                    "platform",
                    "certificate_type",
                    "verification_type",
                    "collection_type",
                    "stop_days_requested",
                    "target",
                ]
                if k in r["slots_used"]
            }
            lines.append(
                f"| {_short(r['query'])} | {r['persona_id']} | `{r['expr_selected_variant'] or '-'}` | "
                f"`{r['semantic_candidate_variant'] or '-'}`/{r['semantic_status']} | {r['semantic_score']:.3f} | "
                f"`{json.dumps(key_slots, ensure_ascii=False)}` |"
            )
        lines.append("")
    return "\n".join(lines)


async def amain() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool-scope", choices=["required", "read-all"], default="read-all")
    parser.add_argument("--persona-policy", choices=["auto", "all"], default="all")
    parser.add_argument("--min-gold-confidence", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--examples-per-skill", type=int, default=6)
    parser.add_argument("--json-out", default=str(JSON_FILE))
    parser.add_argument("--md-out", default=str(REPORT_FILE))
    args = parser.parse_args()

    payload = await evaluate(args)
    Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    Path(args.md_out).write_text(render_markdown(payload, args.examples_per_skill), encoding="utf-8")
    print(f"Wrote {args.md_out}")
    print(f"Wrote {args.json_out}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(amain())
