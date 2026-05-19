"""Apply exact-text split decisions to raw scorable queries.

Reads:
    tests/merged_turn_filter/scorable_raw_queries.jsonl
    tests/merged_turn_filter/scorable_raw_split_decisions.jsonl

Writes:
    tests/merged_turn_filter/scorable_raw_queries_split.jsonl
    tests/merged_turn_filter/scorable_raw_queries_split_summary.json

Split decisions must preserve exact substrings from the original query. This
script validates that invariant before writing output.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = ROOT / "tests" / "merged_turn_filter"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    args = parser.parse_args()

    raw_path = args.base_dir / "scorable_raw_queries.jsonl"
    decisions_path = args.base_dir / "scorable_raw_split_decisions.jsonl"
    raw_rows = load_jsonl(raw_path)
    decisions = {row["query_id"]: row for row in load_jsonl(decisions_path)}

    out: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    split_source_count = 0

    for row in raw_rows:
        decision = decisions.get(row["query_id"])
        if not decision:
            out.append({**row, "split_from_query_id": "", "split_decision": "not_reviewed"})
            continue

        pieces = decision.get("split_queries") or [row["query"]]
        if decision.get("decision") == "split" and len(pieces) > 1:
            split_source_count += 1
        for idx, piece in enumerate(pieces, 1):
            if piece not in row["query"]:
                errors.append({
                    "query_id": row["query_id"],
                    "piece": piece,
                    "error": "split_piece_not_substring",
                })
            new_row = {
                **row,
                "query_id": row["query_id"] if len(pieces) == 1 else f"{row['query_id']}.s{idx}",
                "query": piece,
                "split_from_query_id": row["query_id"] if len(pieces) > 1 else "",
                "split_decision": decision.get("decision", "keep"),
                "split_reason": decision.get("reason", ""),
            }
            out.append(new_row)

    if errors:
        raise SystemExit(json.dumps({
            "error": "invalid split decisions",
            "errors": errors[:20],
            "error_count": len(errors),
        }, ensure_ascii=False, indent=2))

    output_path = args.base_dir / "scorable_raw_queries_split.jsonl"
    with output_path.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_call = Counter(row["call_id"] for row in out)
    summary = {
        "input_raw_queries": len(raw_rows),
        "reviewed_candidates": len(decisions),
        "split_source_queries": split_source_count,
        "output_queries": len(out),
        "calls_with_queries": len(by_call),
        "query_count_per_call": dict(sorted(Counter(by_call.values()).items())),
        "output": str(output_path),
    }
    summary_path = args.base_dir / "scorable_raw_queries_split_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
