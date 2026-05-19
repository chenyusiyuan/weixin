"""Export a clean raw-query eval dataset from merged-turn filtering results.

The output is intentionally small and script-friendly:

Query-level JSONL:
    {sample_id, call_id, record_index, query_index, turn_id, query,
     gold_intents, gold_intent_count, source}

Call-level JSONL:
    {call_id, record_index, gold_intents, gold_intent_count, queries}

Every `query` is exact customer text, or an exact contiguous substring when a
single customer utterance explicitly contains multiple independent requests.

Run:
    python3 scripts/export_merged_raw_eval_dataset.py
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "tests" / "merged_turn_filter" / "scorable_raw_queries_split.jsonl"
DEFAULT_QUERY_OUTPUT = ROOT / "tests" / "merged_turn_filter" / "merged_raw_eval_queries.jsonl"
DEFAULT_CALL_OUTPUT = ROOT / "golden_test.jsonl"
DEFAULT_SUMMARY_OUTPUT = ROOT / "tests" / "merged_turn_filter" / "merged_raw_eval_summary.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--query-output", type=Path, default=DEFAULT_QUERY_OUTPUT)
    parser.add_argument("--call-output", type=Path, default=DEFAULT_CALL_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    args = parser.parse_args()

    source_rows = load_jsonl(args.input)
    query_rows: list[dict[str, Any]] = []
    per_call: dict[str, dict[str, Any]] = {}
    query_counter_by_call: defaultdict[str, int] = defaultdict(int)

    for row in source_rows:
        call_id = str(row["call_id"])
        query_counter_by_call[call_id] += 1
        query_index = query_counter_by_call[call_id]
        gold_intents = list(row.get("gold_intents") or [])
        sample_id = f"{call_id}#q{query_index:03d}"

        query_row = {
            "sample_id": sample_id,
            "call_id": call_id,
            "record_index": int(row["record_index"]),
            "query_index": query_index,
            "turn_id": int(row["turn_id"]),
            "query": row["query"],
            "gold_intents": gold_intents,
            "gold_intent_count": len(gold_intents),
            "source": "merged.jsonl",
        }
        query_rows.append(query_row)

        if call_id not in per_call:
            per_call[call_id] = {
                "call_id": call_id,
                "record_index": int(row["record_index"]),
                "gold_intents": gold_intents,
                "gold_intent_count": len(gold_intents),
                "queries": [],
            }
        per_call[call_id]["queries"].append({
            "sample_id": sample_id,
            "query_index": query_index,
            "turn_id": int(row["turn_id"]),
            "query": row["query"],
        })

    call_rows = sorted(per_call.values(), key=lambda item: item["record_index"])

    args.query_output.parent.mkdir(parents=True, exist_ok=True)
    with args.query_output.open("w", encoding="utf-8") as f:
        for row in query_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with args.call_output.open("w", encoding="utf-8") as f:
        for row in call_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "input": str(args.input),
        "query_output": str(args.query_output),
        "call_output": str(args.call_output),
        "query_records": len(query_rows),
        "call_records": len(call_rows),
        "calls_without_query": 297 - len(call_rows),
        "schema": {
            "query_level": list(query_rows[0].keys()) if query_rows else [],
            "call_level": list(call_rows[0].keys()) if call_rows else [],
        },
    }
    args.summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
