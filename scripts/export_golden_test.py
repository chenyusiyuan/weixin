"""Stage D — Export the final single-turn test set from mapped + reviewed data.

Reads  tests/golden_mapped.jsonl     (all mapped records)
       tests/golden_reviewed.jsonl   (manual overrides for needs_review)
Writes raw_test.jsonl                (legacy single-query gold test set)
         {call_id, query, gold_skill, gold_level3, source}

A record is included iff:
  - mapped.verdict == auto_pass, OR
  - reviewed[call_id].verdict == reviewed (and gold_skill != None)

Also emits a short coverage/quality summary.

Run:
    python scripts/export_golden_test.py
    python scripts/export_golden_test.py --include-unreviewed  # include needs_review without review (risky)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPPED_PATH = ROOT / "tests" / "golden_mapped.jsonl"
REVIEWED_PATH = ROOT / "tests" / "golden_reviewed.jsonl"
OUTPUT_PATH = ROOT / "raw_test.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-unreviewed", action="store_true",
                    help="include needs_review records using path_a (risky — not audited)")
    args = ap.parse_args()

    mapped = load_jsonl(MAPPED_PATH)
    reviewed = {r["call_id"]: r for r in load_jsonl(REVIEWED_PATH)}
    print(f"mapped: {len(mapped)} records; reviewed: {len(reviewed)}")

    out_records: list[dict] = []
    stats: Counter = Counter()

    for r in mapped:
        cid = r["call_id"]
        verdict = r.get("verdict")

        if verdict == "drop":
            stats["dropped"] += 1
            continue

        gold = None
        source = None
        if verdict == "auto_pass":
            gold = r.get("gold_skill")
            source = "auto_pass"
        elif cid in reviewed:
            rev = reviewed[cid]
            if rev.get("verdict") == "drop":
                stats["reviewed_dropped"] += 1
                continue
            gold = rev.get("gold_skill")
            source = f"reviewed:{rev.get('chosen_by', 'manual')}"
        elif verdict == "needs_review" and args.include_unreviewed:
            gold = r.get("path_a_skill") or r.get("path_b_skill")
            source = "unreviewed_fallback"
        else:
            stats["skipped_unreviewed"] += 1
            continue

        if not gold:
            stats["no_gold_skill"] += 1
            continue

        query = r.get("primary_query_polished") or r.get("primary_query_raw") or ""
        if not query.strip():
            stats["empty_query"] += 1
            continue

        out_records.append({
            "call_id": cid,
            "query": query,
            "gold_skill": gold,
            "gold_level3": r.get("level3"),
            "source": source,
        })
        stats[source] += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(out_records)} records to {OUTPUT_PATH}")
    print("\nBreakdown:")
    for k, v in stats.most_common():
        print(f"  {k:<30} {v:>5}")

    # Per-skill distribution
    per_skill = Counter(r["gold_skill"] for r in out_records)
    print(f"\nPer-skill distribution ({len(per_skill)} unique skills):")
    for sid, n in per_skill.most_common(25):
        print(f"  {n:>4}  {sid}")


if __name__ == "__main__":
    main()
