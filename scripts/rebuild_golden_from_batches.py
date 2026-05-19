"""Rebuild raw_test.jsonl from sub-agent batch outputs.

Sources:
  - tests/verification/batch_*_output.jsonl : sub-agent labels (call_id, skill_id, confidence, reason)
  - tests/golden_raw_intent.jsonl           : polished query + level3 (Stage A output)

Applies two post-hoc corrections (previously agreed with user):
  - level3 under "存对公还款/*" + skill_id == "overpayment_refund"
      → rewrite skill_id to "repayment_method_inquiry"
  - level3 under "账单信息查询/*" + skill_id == "bill_deduction_query"
      → rewrite skill_id to "fee_detail_query"

Output schema (one row per record):
  {call_id, query, gold_skill, confidence}
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH_DIR = ROOT / "tests" / "verification"
RAW_INTENT = ROOT / "tests" / "golden_raw_intent.jsonl"
OUTPUT = ROOT / "raw_test.jsonl"


def main() -> None:
    raw_by_cid: dict[str, dict] = {}
    for line in RAW_INTENT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw_by_cid[r["call_id"]] = r

    label_by_cid: dict[str, dict] = {}
    dup = 0
    bad_json = 0
    for path in sorted(BATCH_DIR.glob("batch_*_output.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad_json += 1
                continue
            cid = r.get("call_id")
            if not cid:
                continue
            if cid in label_by_cid:
                dup += 1
            label_by_cid[cid] = r

    print(f"batches: {len(label_by_cid)} labeled (dup={dup}, bad_json={bad_json})")
    print(f"raw intents: {len(raw_by_cid)}")

    out_rows: list[dict] = []
    stats: Counter = Counter()
    correction_log: list[str] = []

    for cid, lab in label_by_cid.items():
        skill_id = lab.get("skill_id")
        confidence = lab.get("confidence", 0.0)

        if skill_id in (None, "None", "null", "") or skill_id == "unusable":
            stats["skipped_no_skill"] += 1
            continue

        raw = raw_by_cid.get(cid)
        if not raw:
            stats["skipped_no_raw"] += 1
            continue

        if raw.get("quality") == "unusable":
            stats["skipped_unusable"] += 1
            continue

        query = raw.get("primary_query_polished") or raw.get("primary_query_raw")
        if not query:
            stats["skipped_no_query"] += 1
            continue

        level3 = raw.get("level3") or ""
        if not isinstance(level3, str):
            level3 = ""

        original_skill = skill_id
        if "存对公还款" in level3 and skill_id == "overpayment_refund":
            skill_id = "repayment_method_inquiry"
            stats["corrected_dui_gong"] += 1
            correction_log.append(f"{cid[:8]}... {level3[-20:]}: overpayment_refund → repayment_method_inquiry")
        elif "账单信息查询" in level3 and skill_id == "bill_deduction_query":
            skill_id = "fee_detail_query"
            stats["corrected_bill_query"] += 1
            correction_log.append(f"{cid[:8]}... {level3[-20:]}: bill_deduction_query → fee_detail_query")

        out_rows.append({
            "call_id": cid,
            "query": query,
            "gold_skill": skill_id,
            "confidence": confidence,
        })
        stats["kept"] += 1

    with OUTPUT.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(out_rows)} rows to {OUTPUT}")
    print("Stats:")
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<25} {v}")

    skill_dist = Counter(r["gold_skill"] for r in out_rows)
    print(f"\nSkill coverage: {len(skill_dist)} unique skills")
    for sid, n in skill_dist.most_common(12):
        print(f"  {n:>4}  {sid}")

    if correction_log:
        print(f"\nFirst 10 corrections (of {len(correction_log)}):")
        for line in correction_log[:10]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
