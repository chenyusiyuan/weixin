"""Populate escalation_signals + add priority where routing is ambiguous.

Seeds the `escalation_signals` list on tier2 / high-risk skills so Chain A
can pre-match keywords like 律师/消协/上级/高阶 and force tier2 routing.

Also sets a `priority` integer on overlapping skills (higher wins when L1
classifier returns a tie):
  - deactivated_customer_service (priority 20, beats account_cancellation)
  - account_cancellation (priority 10)
  - special_account_cancellation (priority 30, hardcoded scenarios win outright)

Idempotent.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills" / "definitions"

# skill_id -> list of escalation-signal keywords
ESCALATION_SIGNALS: dict[str, list[str]] = {
    "fee_refund_tier2": [
        "律师", "法院", "起诉", "消费者协会", "消协", "媒体",
        "投诉到底", "找上级", "坚持退费", "内诉",
    ],
    "fee_consultation_tier2": [
        "投诉违法", "违法收费", "监管", "银保监", "内诉", "找上级",
    ],
    "collection_complaint": [
        "投诉催收", "催收违规", "骚扰", "威胁", "爆通讯录", "监管投诉",
    ],
    "stop_collection": [
        "停催", "停止催收", "法院", "起诉", "律师函",
    ],
    "credit_inquiry": [
        "征信投诉", "人行投诉", "征信异议", "征信错误",
    ],
    "credit_modification": [
        "删除征信", "消除征信", "修改征信", "征信异议",
    ],
    "overdue_negotiation": [
        "协商还款", "延期", "困难证明",
    ],
    "fee_refund_tier1": [],  # leave empty so Chain A doesn't over-escalate tier1
    "fee_consultation_tier1": [],
}

# skill_id -> priority integer (higher wins)
PRIORITIES: dict[str, int] = {
    "special_account_cancellation": 30,
    "deactivated_customer_service": 20,
    "account_cancellation": 10,
    "fee_refund_tier2": 20,
    "fee_refund_tier1": 10,
    "fee_consultation_tier2": 20,
    "fee_consultation_tier1": 10,
}


yaml_rt = YAML(typ="rt")
yaml_rt.preserve_quotes = True
yaml_rt.width = 4096
yaml_rt.indent(mapping=2, sequence=4, offset=2)


def fix_file(path: Path) -> bool:
    sid = path.stem
    signals = ESCALATION_SIGNALS.get(sid)
    priority = PRIORITIES.get(sid)
    if signals is None and priority is None:
        return False

    with open(path, encoding="utf-8") as f:
        docs = [d for d in yaml_rt.load_all(f) if d is not None]
    if not docs:
        return False
    if len(docs) == 1:
        front, body = None, docs[0]
    else:
        front, body = docs[0], docs[1]

    changed = False
    if signals is not None:
        current = list(body.get("escalation_signals") or [])
        if set(current) != set(signals):
            body["escalation_signals"] = CommentedSeq(signals)
            changed = True
    if priority is not None and body.get("priority") != priority:
        body["priority"] = priority
        changed = True

    if not changed:
        return False

    buf = StringIO()
    buf.write("---\n")
    if front is not None:
        yaml_rt.dump(front, buf)
        buf.write("\n")
    yaml_rt.dump(body, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return True


def main() -> None:
    changed = 0
    for path in sorted(SKILLS_DIR.glob("*.yaml")):
        if fix_file(path):
            changed += 1
            print(f"[FIX] {path.name}")
    print(f"{changed} file(s) updated")


if __name__ == "__main__":
    main()
