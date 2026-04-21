"""Stage C — Interactive audit tool for `needs_review` records.

Walks every record with verdict='needs_review' and lets the reviewer:
  - [1] accept path_a as gold
  - [2] accept path_b as gold
  - [3] pick a different skill_id (freeform)
  - [4] drop this record
  - [s] skip (decide later)
  - [q] quit

Reviews are persisted to tests/golden_reviewed.jsonl (append-only).
Re-running resumes from the first unreviewed record.

Run:
    python scripts/audit_reviewed.py
    python scripts/audit_reviewed.py --verdict-filter needs_review
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPPED_PATH = ROOT / "tests" / "golden_mapped.jsonl"
REVIEWED_PATH = ROOT / "tests" / "golden_reviewed.jsonl"


def load_reviewed() -> dict[str, dict]:
    if not REVIEWED_PATH.exists():
        return {}
    out: dict[str, dict] = {}
    for line in REVIEWED_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["call_id"]] = r
    return out


def save_review(record: dict) -> None:
    with open(REVIEWED_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def print_record(r: dict) -> None:
    print("\n" + "=" * 80)
    print(f"call_id : {r['call_id']}")
    print(f"level3  : {r.get('level3')}")
    print(f"quality : {r.get('quality')}    confidence: {r.get('confidence')}")
    print(f"reason  : {r.get('review_reason')}")
    print(f"\nquery   : {r.get('primary_query_polished') or r.get('primary_query_raw')}")
    print(f"intent  : {r.get('intent')}")
    print()
    print(f"path_a (level3 → skill):  {r.get('path_a_skill')}")
    print(f"path_b (embedding):       {r.get('path_b_skill')}  score={r.get('path_b_score')}")
    top3 = r.get("path_b_top3") or []
    if top3:
        print("path_b top-3:")
        for sid, sc in top3:
            print(f"    {sc:.3f}  {sid}")
    print()


def prompt_action(r: dict) -> dict | None:
    while True:
        cmd = input("  action [1=path_a  2=path_b  3=other  4=drop  s=skip  q=quit] > ").strip().lower()
        if cmd == "q":
            return None
        if cmd == "s":
            return {"_skip": True}
        if cmd == "1":
            if r.get("path_a_skill"):
                return {"gold_skill": r["path_a_skill"], "verdict": "reviewed", "chosen_by": "path_a"}
            print("  path_a not available")
            continue
        if cmd == "2":
            if r.get("path_b_skill"):
                return {"gold_skill": r["path_b_skill"], "verdict": "reviewed", "chosen_by": "path_b"}
            print("  path_b not available")
            continue
        if cmd == "3":
            sid = input("  enter skill_id: ").strip()
            if sid:
                return {"gold_skill": sid, "verdict": "reviewed", "chosen_by": "manual"}
        if cmd == "4":
            return {"gold_skill": None, "verdict": "drop", "chosen_by": "reviewer"}
        print("  invalid")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict-filter", default="needs_review",
                    help="which verdict to audit (needs_review / auto_pass / drop)")
    args = ap.parse_args()

    if not MAPPED_PATH.exists():
        print(f"missing {MAPPED_PATH} — run map_intent_to_skill.py first")
        sys.exit(1)

    reviewed = load_reviewed()
    records = [json.loads(line) for line in MAPPED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    pending = [r for r in records if r.get("verdict") == args.verdict_filter and r["call_id"] not in reviewed]

    print(f"loaded {len(records)} mapped records; {len(reviewed)} already reviewed; {len(pending)} pending")

    for i, r in enumerate(pending):
        print(f"\n── [{i+1}/{len(pending)}] ──", end="")
        print_record(r)
        decision = prompt_action(r)
        if decision is None:
            print("\nquitting. progress saved.")
            break
        if decision.get("_skip"):
            continue
        save_review({
            "call_id": r["call_id"],
            "level3": r.get("level3"),
            "primary_query_polished": r.get("primary_query_polished"),
            "intent": r.get("intent"),
            **decision,
        })
        print(f"  saved: {decision}")

    print("\ndone")


if __name__ == "__main__":
    main()
