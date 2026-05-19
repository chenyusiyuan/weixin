"""Analyze missed merged multi-turn eval cases against concrete skills.

The previous merged evaluation scored coarse `意图` labels against skill IDs.
This helper inspects each missed gold intent, adds source `小结名称`, query
evidence, predicted skills, and a suggested concrete skill mapping.

Run:
    python3 scripts/analyze_merged_error_skill_alignment.py
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_DIR = ROOT / "tests" / "reports" / "merged_multi_turn_20260427_153330"
DEFAULT_CALL_SCORES = DEFAULT_REPORT_DIR / "call_scores.jsonl"
DEFAULT_QUERY_PREDS = DEFAULT_REPORT_DIR / "query_predictions.jsonl"
DEFAULT_LABELS = ROOT / "tests" / "merged_turn_filter" / "merged_turn_labels.jsonl"
DEFAULT_CALL_INPUT = ROOT / "golden_test.jsonl"
DEFAULT_FEWSHOT_MAPPING = ROOT / "scripts" / "references" / "fewshot_label_mapping.json"
DEFAULT_SKILL_AUDIT = ROOT / "docs" / "sop_skill_coverage_audit.json"

OUT_JSONL = DEFAULT_REPORT_DIR / "error_skill_alignment.jsonl"
OUT_MD = DEFAULT_REPORT_DIR / "error_skill_alignment.md"


EXCLUDE_SESSION_SKILLS = {
    "greeting_opening",
    "identity_readback",
    "acknowledgement",
    "channel_check",
    "closing",
}


BASE_INTENT_SKILLS: dict[str, list[str]] = {
    "催收相关/协商还款": ["overdue_negotiation"],
    "催收相关/要求停催": ["stop_collection"],
    "催收相关/投诉催收": ["collection_complaint"],
    "催收相关/核实催收信息": ["post_loan_verification"],
    "还款相关/聚合码还款问题": ["repayment_method_inquiry"],
    "还款相关/提前清贷": ["early_loan_clearance"],
    "业务办理/账户注销": [
        "account_cancellation",
        "special_account_cancellation",
        "deactivated_customer_service",
    ],
    "业务办理/结清证明": ["clearance_certificate"],
    "业务办理/发票开具": ["invoice_issuance"],
    "业务办理/合同调取": ["contract_retrieval"],
    "申请咨询/额度获取咨询": ["quota_consultation", "no_quota_issue"],
    "申请咨询/放款时效": ["disbursement_progress"],
    "申请咨询/放款结果": ["disbursement_progress"],
    "申请咨询/贷款咨询": ["loan_consultation"],
    "申请咨询/预约借款": ["loan_termination"],
    "信息维护/换绑卡": ["card_rebinding"],
    "费用相关/退费进度": ["fee_refund_status"],
}


COARSE_INTENT_DEFAULTS: dict[str, list[str]] = {
    "还款相关/还款咨询": [
        "repayment_status_issue",
        "repayment_result_query",
        "repayment_method_inquiry",
        "deduction_issues",
        "early_deduction",
        "bill_date_credit_impact",
    ],
    "还款相关/账单信息查询": [
        "fee_detail_query",
        "bill_deduction_query",
        "repayment_result_query",
        "card_rebinding",
    ],
    "还款相关/存对公还款": [
        "repayment_method_inquiry",
        "repayment_status_issue",
        "overpayment_refund",
        "post_loan_verification",
    ],
    "费用相关/费用咨询": [
        "fee_consultation_tier1",
        "fee_consultation_tier2",
        "fee_detail_query",
        "bill_deduction_query",
    ],
    "费用相关/要求退费": [
        "fee_refund_tier1",
        "fee_refund_tier2",
        "loan_dispute_refund",
        "overpayment_refund",
    ],
    "营销活动/会员退费": [
        "member_refund",
        "member_cancel",
        "premium_card_refund",
        "premium_card_cancel",
        "light_card_cancel_refund",
    ],
    "营销活动/新活动咨询": [
        "premium_card_inquiry",
        "premium_card_cancel",
        "premium_card_refund",
        "value_added_service_inquiry",
        "cancel_value_added_service",
        "refund_value_added_service",
        "light_card_cancel_refund",
        "member_consultation",
        "member_cancel",
        "member_refund",
    ],
    "业务办理/征信相关": [
        "credit_inquiry",
        "credit_modification",
        "cancel_credit_authorization",
        "bill_date_credit_impact",
    ],
    "信息维护/资料信息修改": [],
    "产品与信息/非我司产品": [],
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_fewshot_mapping(path: Path) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for item in data.get("mappings", []):
        skill_id = item.get("skill_id")
        if skill_id:
            out[item["level3"]] = [skill_id]
    return out


def load_skill_sops(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for item in data:
        skill_id = item.get("skill_id")
        if skill_id:
            out[skill_id] = item.get("xlsx_paths") or item.get("xlsx_files") or []
    return out


def has_any(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def suggested_skills(intent: str, level3: str, queries: list[str], fewshot: dict[str, list[str]]) -> tuple[list[str], str]:
    joined = "\n".join(queries)

    if intent == "产品与信息/非我司产品":
        return [], "current_skill_gap: non-company product has no dedicated skill; exclude or create a skill"

    if intent == "信息维护/资料信息修改":
        if has_any(joined, ["换卡", "绑卡", "银行卡"]):
            return ["card_rebinding"], "fallback: current system only has card rebinding under information maintenance"
        return [], "current_skill_gap: generic profile/contact info modification has no dedicated skill"

    if intent == "还款相关/存对公还款":
        if has_any(joined, ["转错", "打错", "输错", "误转", "多转", "转多", "转少", "少转", "补差", "补一下"]):
            return ["overpayment_refund"], "corporate transfer exception; current closest skill is overpayment_refund, but short-paid/top-up is not perfectly covered"
        if has_any(joined, ["没入账", "未入账", "没到账", "未到账", "没更新", "还在催", "凭证", "截图"]):
            return ["repayment_status_issue"], "corporate transfer posted/not-updated issue"
        if has_any(joined, ["真假", "真实", "是不是你们", "核实", "确认账号"]):
            return ["post_loan_verification"], "verify corporate account authenticity"
        return ["repayment_method_inquiry"], "ordinary corporate repayment method/account inquiry"

    if intent == "还款相关/还款咨询":
        if level3 in fewshot:
            return fewshot[level3], "level3 mapping from fewshot_label_mapping"
        if has_any(joined, ["失败", "还不了", "还不进去", "没更新", "未更新", "没到账", "扣了一部分", "重复扣", "只扣"]):
            return ["repayment_status_issue"], "repayment abnormality by query wording"
        if has_any(joined, ["结果", "成功了吗", "到账了吗", "查一下", "还款中"]):
            return ["repayment_result_query"], "repayment result/progress query"
        if has_any(joined, ["怎么还", "还款方式", "二维码", "聚合码", "微信", "支付宝", "对公账号"]):
            return ["repayment_method_inquiry"], "repayment method query"
        return COARSE_INTENT_DEFAULTS[intent], "coarse intent; multiple repayment skills acceptable"

    if intent == "还款相关/账单信息查询":
        if level3 in fewshot:
            return fewshot[level3], "level3 mapping from fewshot_label_mapping"
        if has_any(joined, ["银行卡", "换卡", "绑定"]):
            return ["card_rebinding"], "repayment bank card query/update"
        if has_any(joined, ["还款结果", "成功", "到账"]):
            return ["repayment_result_query"], "repayment result query"
        if has_any(joined, ["扣款", "扣了"]):
            return ["bill_deduction_query"], "bill deduction status query"
        return ["fee_detail_query"], "bill amount/detail query"

    if intent == "营销活动/会员退费":
        if has_any(joined + level3, ["优享卡"]):
            if has_any(joined + level3, ["取消", "关闭", "自动续费"]):
                return ["premium_card_cancel", "premium_card_refund"], "premium-card cancel/refund mixed into member-refund label"
            return ["premium_card_refund"], "premium-card refund mixed into member-refund label"
        if has_any(joined + level3, ["轻享卡"]):
            return ["light_card_cancel_refund"], "light-card cancel/refund mixed into member-refund label"
        if has_any(joined + level3, ["取消", "关闭", "自动续费", "扣款前"]):
            return ["member_cancel"], "member cancel / close auto-renew"
        return ["member_refund"], "member refund"

    if intent == "营销活动/新活动咨询":
        text = joined + "\n" + level3
        if "优享卡" in text:
            if has_any(text, ["退", "扣费", "退款"]):
                return ["premium_card_refund"], "premium-card refund under new-activity label"
            if has_any(text, ["取消", "关闭"]):
                return ["premium_card_cancel"], "premium-card cancel under new-activity label"
            return ["premium_card_inquiry"], "premium-card inquiry under new-activity label"
        if "轻享卡" in text:
            return ["light_card_cancel_refund"], "light-card cancel/refund/inquiry under new-activity label"
        if has_any(text, ["增值服务", "债务咨询", "服务费"]):
            if has_any(text, ["退"]):
                return ["refund_value_added_service"], "value-added service refund"
            if has_any(text, ["取消", "关闭"]):
                return ["cancel_value_added_service"], "value-added service cancellation"
            return ["value_added_service_inquiry"], "value-added service inquiry"
        if has_any(text, ["会员", "先享后付"]):
            return ["member_consultation", "member_cancel", "member_refund"], "member service under new-activity label"
        return COARSE_INTENT_DEFAULTS[intent], "coarse new-activity label; needs level3 split"

    if intent == "业务办理/征信相关":
        if level3 in fewshot:
            return fewshot[level3], "level3 mapping from fewshot_label_mapping"
        if has_any(joined + level3, ["修改征信", "改征信", "修复征信"]):
            return ["credit_modification"], "credit modification"
        if has_any(joined + level3, ["注销授信", "关闭额度", "关掉额度"]):
            return ["cancel_credit_authorization"], "cancel credit authorization"
        if has_any(joined + level3, ["影响征信", "上征信"]):
            return ["credit_inquiry", "bill_date_credit_impact"], "credit impact inquiry"
        return COARSE_INTENT_DEFAULTS[intent], "coarse credit-related label"

    if intent == "费用相关/要求退费":
        if level3 in fewshot:
            return fewshot[level3], "level3 mapping from fewshot_label_mapping"
        if has_any(joined + level3, ["溢余", "对公转", "转错"]):
            return ["overpayment_refund"], "overpayment refund"
        if has_any(joined + level3, ["争议", "非本人", "未授权"]):
            return ["loan_dispute_refund"], "loan-dispute refund"
        return ["fee_refund_tier1", "fee_refund_tier2"], "generic fee refund"

    if intent == "费用相关/费用咨询":
        if level3 in fewshot:
            return fewshot[level3], "level3 mapping from fewshot_label_mapping"
        if has_any(joined, ["明细", "综合费率", "本金", "利息多少"]):
            return ["fee_detail_query"], "fee detail query"
        return ["fee_consultation_tier1", "fee_consultation_tier2"], "generic fee consultation"

    if level3 in fewshot:
        return fewshot[level3], "level3 mapping from fewshot_label_mapping"

    if intent in BASE_INTENT_SKILLS:
        return BASE_INTENT_SKILLS[intent], "direct intent mapping"

    if intent in COARSE_INTENT_DEFAULTS:
        return COARSE_INTENT_DEFAULTS[intent], "coarse intent fallback"

    return [], "unmapped intent"


def classify_status(
    current_gold_skills: list[str],
    suggested: list[str],
    predicted_topk: list[str],
    ranking: list[dict[str, Any]],
    reason: str,
) -> str:
    ranking_ids = [r.get("skill_id") for r in ranking if r.get("skill_id") not in EXCLUDE_SESSION_SKILLS]
    if not suggested:
        return "not_applicable_or_missing_skill"
    if set(predicted_topk) & set(suggested):
        if set(current_gold_skills) & set(suggested):
            return "already_should_have_hit_under_current_mapping"
        return "current_mapping_miss_prediction_plausible"
    if set(ranking_ids) & set(suggested):
        return "aggregation_miss_skill_seen_below_topk"
    if "not perfectly covered" in reason:
        return "needs_new_skill_or_skill_split"
    if set(current_gold_skills) == set(suggested):
        return "router_or_context_miss"
    return "mapping_or_granularity_mismatch"


def compact_queries(pred_rows: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in pred_rows[:limit]:
        out.append({
            "query_index": row.get("query_index"),
            "query": row.get("query"),
            "pred_skill": row.get("pred_skill"),
            "confidence": row.get("confidence"),
            "topk_skills": row.get("topk_skills"),
        })
    return out


def main() -> None:
    call_scores = load_jsonl(DEFAULT_CALL_SCORES)
    query_preds = load_jsonl(DEFAULT_QUERY_PREDS)
    labels = {r["call_id"]: r for r in load_jsonl(DEFAULT_LABELS)}
    call_inputs = {r["call_id"]: r for r in load_jsonl(DEFAULT_CALL_INPUT)}
    fewshot = load_fewshot_mapping(DEFAULT_FEWSHOT_MAPPING)
    skill_sops = load_skill_sops(DEFAULT_SKILL_AUDIT)

    preds_by_call: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in query_preds:
        preds_by_call[row["call_id"]].append(row)
    for rows in preds_by_call.values():
        rows.sort(key=lambda r: r.get("query_index") or 0)

    analysis_rows: list[dict[str, Any]] = []
    for score in call_scores:
        missed = score.get("missed_gold_intents") or []
        if not missed:
            continue
        call_id = score["call_id"]
        label = labels.get(call_id, {})
        source_labels = label.get("source_labels") or {}
        level3 = source_labels.get("小结名称") or ""
        input_call = call_inputs.get(call_id, {})
        queries = [q.get("query", "") for q in input_call.get("queries", [])]
        pred_rows = preds_by_call.get(call_id, [])
        for miss in missed:
            intent = miss["intent"]
            current_gold_skills = miss.get("skill_ids") or []
            suggested, reason = suggested_skills(intent, level3, queries, fewshot)
            status = classify_status(
                current_gold_skills,
                suggested,
                score.get("predicted_topk") or [],
                score.get("predicted_skill_ranking") or [],
                reason,
            )
            analysis_rows.append({
                "record_index": score.get("record_index"),
                "call_id": call_id,
                "missed_intent": intent,
                "source_level3": level3,
                "source_labels": source_labels,
                "current_gold_skill_ids": current_gold_skills,
                "suggested_skill_ids": suggested,
                "suggested_sop_paths": {
                    skill_id: skill_sops.get(skill_id, [])
                    for skill_id in suggested
                },
                "predicted_topk": score.get("predicted_topk") or [],
                "predicted_skill_ranking": score.get("predicted_skill_ranking") or [],
                "status": status,
                "reason": reason,
                "score": score.get("score"),
                "gold_k": score.get("gold_k"),
                "query_count": score.get("query_count"),
                "query_predictions": compact_queries(pred_rows, limit=6),
            })

    OUT_JSONL.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in analysis_rows) + "\n",
        encoding="utf-8",
    )

    status_counts = Counter(row["status"] for row in analysis_rows)
    intent_counts = Counter(row["missed_intent"] for row in analysis_rows)
    intent_status = defaultdict(Counter)
    for row in analysis_rows:
        intent_status[row["missed_intent"]][row["status"]] += 1

    lines: list[str] = []
    lines.append("# Merged 错例到 Skill 对齐分析")
    lines.append("")
    lines.append(f"- 来源报告：`{DEFAULT_REPORT_DIR}`")
    lines.append(f"- 错例 miss item 数：{len(analysis_rows)}")
    lines.append(f"- 明细 JSONL：`{OUT_JSONL}`")
    lines.append("")
    lines.append("## 状态汇总")
    lines.append("")
    lines.append("| 状态 | 数量 | 含义 |")
    lines.append("|---|---:|---|")
    status_desc = {
        "current_mapping_miss_prediction_plausible": "当前二级 gold 映射漏掉了模型预测的合理 skill",
        "mapping_or_granularity_mismatch": "需要用三级标签或 query 语义重映射",
        "aggregation_miss_skill_seen_below_topk": "对应 skill 出现过，但被频次 TopK 挤掉",
        "router_or_context_miss": "当前映射基本正确，路由或上下文未命中",
        "not_applicable_or_missing_skill": "当前 skill/SOP 体系无对应，建议排除或新增 skill",
        "needs_new_skill_or_skill_split": "现有 skill 只能近似承接，建议拆新 skill/分支",
        "already_should_have_hit_under_current_mapping": "按当前映射也应命中，需检查评分/过滤逻辑",
    }
    for status, count in status_counts.most_common():
        lines.append(f"| `{status}` | {count} | {status_desc.get(status, '')} |")
    lines.append("")
    lines.append("## 按 Missed Intent 汇总")
    lines.append("")
    lines.append("| missed_intent | miss数 | 主要状态 |")
    lines.append("|---|---:|---|")
    for intent, count in intent_counts.most_common():
        top_status = ", ".join(f"{k}:{v}" for k, v in intent_status[intent].most_common(3))
        lines.append(f"| {intent} | {count} | {top_status} |")
    lines.append("")
    lines.append("## 逐条明细")
    lines.append("")
    lines.append("| record | missed_intent | source_level3 | current_gold | suggested_skill | pred_topk | status | query evidence |")
    lines.append("|---:|---|---|---|---|---|---|---|")
    for row in sorted(analysis_rows, key=lambda r: (r["missed_intent"], r["record_index"] or 0)):
        evidence = " / ".join(
            re.sub(r"\s+", " ", item["query"]).strip()[:80]
            for item in row["query_predictions"][:2]
            if item.get("query")
        )
        lines.append(
            "| {record} | {intent} | {level3} | `{current}` | `{suggested}` | `{pred}` | `{status}` | {evidence} |".format(
                record=row["record_index"],
                intent=row["missed_intent"],
                level3=row["source_level3"],
                current=", ".join(row["current_gold_skill_ids"]),
                suggested=", ".join(row["suggested_skill_ids"]) or "NO_CURRENT_SKILL",
                pred=", ".join(row["predicted_topk"]),
                status=row["status"],
                evidence=evidence.replace("|", "\\|"),
            )
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "miss_items": len(analysis_rows),
        "output_jsonl": str(OUT_JSONL),
        "output_md": str(OUT_MD),
        "status_counts": dict(status_counts),
        "top_intents": intent_counts.most_common(20),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
