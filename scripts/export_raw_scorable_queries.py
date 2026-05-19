"""Export exact customer utterances from merged turn labels.

This is the strict/raw variant of the merged-turn filter output:

- `query` is always the original customer turn text.
- No summarization, paraphrasing, or cross-turn merging is performed.
- If one raw turn appears to contain multiple explicit requests, it is kept as
  raw text and flagged for optional split review instead of rewritten.

Inputs:
    tests/merged_turn_filter/chunks/chunk_*.jsonl
    tests/merged_turn_filter/merged_turn_labels.jsonl

Writes:
    tests/merged_turn_filter/scorable_raw_queries.jsonl
    tests/merged_turn_filter/scorable_raw_query_summary.json

Run:
    python3 scripts/export_raw_scorable_queries.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = ROOT / "tests" / "merged_turn_filter"


MULTI_INTENT_MARKERS = (
    "两个诉求",
    "两个问题",
    "两个事情",
    "两个事",
    "有两个",
    "第一个",
    "第一",
    "第二个",
    "第二",
    "一方面",
    "另一方面",
    "还有一个",
    "另外一个",
    "还有就是",
    "另外就是",
)

BUSINESS_MARKERS = (
    # question / action words
    "怎么", "为什么", "什么", "多少", "多久", "哪里", "哪个", "哪家",
    "能不能", "可不可以", "行不行", "是不是", "有没有", "怎么办",
    "查询", "查一下", "确认", "核实", "申请", "办理", "开具", "调取",
    "修改", "取消", "注销", "关闭", "退订", "投诉", "反馈", "处理",
    # business nouns / verbs
    "还款", "还不了", "还不上", "扣款", "账单", "欠款", "本金", "利息",
    "罚息", "费用", "担保费", "费率", "退款", "退费", "到账", "入账",
    "结清", "提前还", "提前结清", "清贷", "银行卡", "换卡", "对公",
    "二维码", "微信", "支付宝", "征信", "逾期", "协商", "延期", "宽限",
    "催收", "停催", "缓催", "骚扰", "联系人", "电话", "短信", "威胁",
    "额度", "贷款", "借款", "放款", "合同", "证明", "发票", "账户",
    "账号", "会员", "优享卡", "轻享卡", "增值服务", "营销",
    "非我司", "不是你们", "你们公司", "哪个公司的",
)

BACKGROUND_ONLY_PATTERNS = (
    "不太方便",
    "最近不方便",
    "这两天不方便",
    "有点困难",
    "资金困难",
    "资金紧张",
    "周转不开",
    "没有能力",
    "我知道",
    "我明白",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def looks_multi_intent(text: str) -> bool:
    if any(marker in text for marker in MULTI_INTENT_MARKERS):
        return True
    # Several explicit action verbs in a long turn often means the customer
    # bundled multiple business requests into one utterance. Keep this as a
    # review flag, not an automatic split.
    action_markers = (
        "查询", "申请", "办理", "取消", "注销", "开具", "调取", "修改",
        "停催", "协商", "还款", "退费", "投诉", "核实", "确认",
    )
    hits = sum(1 for marker in action_markers if marker in text)
    compact_len = len(re.sub(r"\s+", "", text))
    return compact_len >= 60 and hits >= 3


def has_standalone_business_signal(text: str) -> bool:
    """Whether a raw customer turn itself is suitable as a router query.

    The previous grouped labels can include context/background turns such as
    "我这两天不太方便". Those are evidence for a nearby business request, but
    should not be sent to the router alone.
    """
    t = text.strip()
    compact = re.sub(r"[\s，,。.!！?？…]", "", t)
    if len(compact) < 5:
        return False
    if any(marker in t for marker in BUSINESS_MARKERS):
        return True
    # Long customer narratives can be business-bearing even when they lack a
    # short keyword, but short hardship/background lines are not standalone.
    if len(compact) >= 28 and not any(pat in t for pat in BACKGROUND_ONLY_PATTERNS):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    args = parser.parse_args()

    chunk_records: dict[int, dict[str, Any]] = {}
    for path in sorted((args.base_dir / "chunks").glob("chunk_*.jsonl")):
        for record in load_jsonl(path):
            chunk_records[int(record["record_index"])] = record

    labels = load_jsonl(args.base_dir / "merged_turn_labels.jsonl")
    out: list[dict[str, Any]] = []
    split_review: list[dict[str, Any]] = []

    for label in labels:
        record_index = int(label["record_index"])
        chunk_record = chunk_records[record_index]
        turns_by_id = {
            int(turn["turn_id"]): turn
            for turn in chunk_record.get("turns", [])
            if turn.get("role") == "customer"
        }

        query_no = 0
        for group_index, group in enumerate(label.get("scorable_customer_turns", []), 1):
            for turn_id in group.get("turn_ids", []):
                turn = turns_by_id.get(int(turn_id))
                if not turn:
                    continue
                query_no += 1
                text = str(turn.get("text") or "").strip()
                if not has_standalone_business_signal(text):
                    continue
                needs_split = looks_multi_intent(text)
                row = {
                    "query_id": f"{label['call_id']}#raw{query_no:02d}",
                    "record_index": record_index,
                    "call_id": label["call_id"],
                    "gold_intents": label.get("gold_intents", []),
                    "turn_id": int(turn_id),
                    "query": text,
                    "source_group_index": group_index,
                    "source_group_reason": group.get("reason", ""),
                    "needs_split_review": needs_split,
                }
                out.append(row)
                if needs_split:
                    split_review.append(row)

    output_path = args.base_dir / "scorable_raw_queries.jsonl"
    with output_path.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    query_count_by_call = Counter(row["call_id"] for row in out)
    summary = {
        "output": str(output_path),
        "calls": len(labels),
        "raw_queries": len(out),
        "calls_with_raw_queries": len(query_count_by_call),
        "calls_without_raw_queries": len(labels) - len(query_count_by_call),
        "needs_split_review": len(split_review),
        "query_count_per_call": dict(sorted(Counter(query_count_by_call.values()).items())),
        "split_review_examples": split_review[:20],
    }
    summary_path = args.base_dir / "scorable_raw_query_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
