"""Validate and merge LLM customer-turn labels for 原始300条数据.jsonl.

Reads:
    tests/merged_turn_filter/chunks/chunk_*.jsonl
    tests/merged_turn_filter/labels/chunk_*.labels.jsonl

Writes:
    tests/merged_turn_filter/merged_turn_labels.jsonl
    tests/merged_turn_filter/scorable_queries.jsonl
    tests/merged_turn_filter/label_validation_summary.json

Run after all chunk label files are present:
    python3 scripts/merge_merged_turn_labels.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = ROOT / "tests" / "merged_turn_filter"


REQUIRED_KEYS = {
    "record_index",
    "call_id",
    "gold_intents",
    "scorable_customer_turns",
    "ignored_customer_turns",
    "notes",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: expected object")
            records.append(value)
    return records


def customer_turn_ids(chunk_record: dict[str, Any]) -> set[int]:
    return {
        int(turn["turn_id"])
        for turn in chunk_record.get("turns", [])
        if turn.get("role") == "customer"
    }


def flatten_scorable_turn_ids(label: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for item in label.get("scorable_customer_turns", []):
        for turn_id in item.get("turn_ids", []):
            out.append(int(turn_id))
    return out


def flatten_ignored_turn_ids(label: dict[str, Any]) -> list[int]:
    return [int(item.get("turn_id")) for item in label.get("ignored_customer_turns", [])]


def validate_label(
    chunk_record: dict[str, Any],
    label: dict[str, Any],
    errors: list[dict[str, Any]],
) -> None:
    missing_keys = sorted(REQUIRED_KEYS - set(label))
    if missing_keys:
        errors.append({
            "record_index": chunk_record.get("record_index"),
            "call_id": chunk_record.get("call_id"),
            "error": "missing_keys",
            "details": missing_keys,
        })
        return

    for key in ("record_index", "call_id"):
        if label.get(key) != chunk_record.get(key):
            errors.append({
                "record_index": chunk_record.get("record_index"),
                "call_id": chunk_record.get("call_id"),
                "error": f"{key}_mismatch",
                "expected": chunk_record.get(key),
                "actual": label.get(key),
            })

    if label.get("gold_intents") != chunk_record.get("gold_intents"):
        errors.append({
            "record_index": chunk_record.get("record_index"),
            "call_id": chunk_record.get("call_id"),
            "error": "gold_intents_mismatch",
            "expected": chunk_record.get("gold_intents"),
            "actual": label.get("gold_intents"),
        })

    expected = customer_turn_ids(chunk_record)
    scorable_ids = flatten_scorable_turn_ids(label)
    ignored_ids = flatten_ignored_turn_ids(label)
    all_ids = scorable_ids + ignored_ids
    counts = Counter(all_ids)
    duplicate_ids = sorted([turn_id for turn_id, count in counts.items() if count > 1])
    unknown_ids = sorted(set(all_ids) - expected)
    missing_ids = sorted(expected - set(all_ids))

    if duplicate_ids or unknown_ids or missing_ids:
        errors.append({
            "record_index": chunk_record.get("record_index"),
            "call_id": chunk_record.get("call_id"),
            "error": "turn_coverage_error",
            "duplicate_ids": duplicate_ids,
            "unknown_ids": unknown_ids,
            "missing_ids": missing_ids,
        })


def merge(base_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    chunk_paths = sorted((base_dir / "chunks").glob("chunk_*.jsonl"))
    if not chunk_paths:
        raise FileNotFoundError(f"no chunks found under {base_dir / 'chunks'}")

    labels_by_call: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    input_records: list[dict[str, Any]] = []
    label_paths: list[str] = []

    for chunk_path in chunk_paths:
        chunk_records = load_jsonl(chunk_path)
        label_path = base_dir / "labels" / chunk_path.name.replace(".jsonl", ".labels.jsonl")
        label_paths.append(str(label_path))
        if not label_path.exists():
            errors.append({
                "chunk": str(chunk_path),
                "error": "missing_label_file",
                "expected": str(label_path),
            })
            input_records.extend(chunk_records)
            continue

        labels = load_jsonl(label_path)
        if len(labels) != len(chunk_records):
            errors.append({
                "chunk": str(chunk_path),
                "error": "line_count_mismatch",
                "expected": len(chunk_records),
                "actual": len(labels),
            })

        for chunk_record, label in zip(chunk_records, labels):
            validate_label(chunk_record, label, errors)
            call_id = str(label.get("call_id") or "")
            if call_id in labels_by_call:
                errors.append({
                    "record_index": label.get("record_index"),
                    "call_id": call_id,
                    "error": "duplicate_label_call_id",
                })
            labels_by_call[call_id] = label
        input_records.extend(chunk_records)

    merged_labels: list[dict[str, Any]] = []
    scorable_queries: list[dict[str, Any]] = []
    for chunk_record in sorted(input_records, key=lambda r: int(r["record_index"])):
        call_id = str(chunk_record.get("call_id"))
        label = labels_by_call.get(call_id)
        if not label:
            continue
        merged = {
            "record_index": chunk_record["record_index"],
            "call_id": call_id,
            "gold_intents": label.get("gold_intents", []),
            "source_labels": chunk_record.get("source_labels", {}),
            "dialogue_source": chunk_record.get("dialogue_source"),
            "scorable_customer_turns": label.get("scorable_customer_turns", []),
            "ignored_customer_turns": label.get("ignored_customer_turns", []),
            "notes": label.get("notes", ""),
        }
        merged_labels.append(merged)

        for query_idx, item in enumerate(merged["scorable_customer_turns"], 1):
            query = str(item.get("standalone_query") or item.get("original_text") or "").strip()
            if not query:
                continue
            scorable_queries.append({
                "query_id": f"{call_id}#{query_idx:02d}",
                "record_index": chunk_record["record_index"],
                "call_id": call_id,
                "gold_intents": merged["gold_intents"],
                "source_turn_ids": item.get("turn_ids", []),
                "query": query,
                "original_text": item.get("original_text", ""),
                "reason": item.get("reason", ""),
            })

    summary = {
        "chunk_files": [str(path) for path in chunk_paths],
        "label_files": label_paths,
        "input_records": len(input_records),
        "merged_label_records": len(merged_labels),
        "scorable_queries": len(scorable_queries),
        "records_with_no_scorable_query": sum(
            1 for item in merged_labels if not item.get("scorable_customer_turns")
        ),
        "validation_error_count": len(errors),
        "validation_errors": errors[:200],
    }
    return merged_labels, scorable_queries, summary


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    args = parser.parse_args()

    merged_labels, scorable_queries, summary = merge(args.base_dir)

    write_jsonl(args.base_dir / "merged_turn_labels.jsonl", merged_labels)
    write_jsonl(args.base_dir / "scorable_queries.jsonl", scorable_queries)
    (args.base_dir / "label_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
