"""Prepare original multi-turn call chunks for LLM customer-turn labeling.

The source file is mostly JSONL, but a few rows contain minor JSON issues:
full-width commas in arrays, trailing backslashes, and concatenated objects.
This script repairs those cases conservatively, normalizes gold intents, parses
dialogue turns, and writes chunk files for parallel review.

Run:
    python3 scripts/prepare_merged_turn_labeling_chunks.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "原始300条数据.jsonl"
DEFAULT_OUT_DIR = ROOT / "tests" / "merged_turn_filter" / "chunks"


def repair_json_text(text: str) -> str:
    """Fix the small set of observed JSONL transcription issues."""
    fixed = text.strip()
    # Chinese comma used as a JSON array separator: ["a"，"b"].
    fixed = re.sub(r'(?<=")\s*，\s*(?=")', ", ", fixed)
    # Some rows end with a stray backslash after the closing JSON object.
    fixed = re.sub(r"(?<=})\\+$", "", fixed)
    return fixed


def parse_json_objects(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = repair_json_text(raw_line)
        idx = 0
        parsed_on_line = 0
        while idx < len(text):
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end = decoder.raw_decode(text, idx)
            except json.JSONDecodeError as exc:
                errors.append({
                    "line_no": line_no,
                    "offset": idx,
                    "error": str(exc),
                    "snippet": text[idx:idx + 160],
                })
                break
            if isinstance(obj, dict):
                obj["_source_line_no"] = line_no
                obj["_object_index_on_line"] = parsed_on_line
                records.append(obj)
            parsed_on_line += 1
            idx = end

    return records, errors


def normalize_intents(raw: Any) -> list[str]:
    out: list[str] = []

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, float) and value != value:
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return
            if text.startswith("["):
                try:
                    add(json.loads(repair_json_text(text)))
                    return
                except json.JSONDecodeError:
                    pass
            out.append(text)
            return
        out.append(str(value).strip())

    add(raw)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def choose_dialogue(record: dict[str, Any]) -> tuple[str, str]:
    cleaned = str(record.get("完整对话_清洗后") or "").strip()
    service_tag = record.get("服务标签")
    original = str(record.get("完整对话_原始") or "").strip()
    if cleaned:
        return cleaned, "完整对话_清洗后"
    if isinstance(service_tag, str) and "[客户]" in service_tag and "[坐席]" in service_tag:
        return service_tag.strip(), "服务标签"
    return original, "完整对话_原始"


def parse_turns(dialogue: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    current_role: str | None = None
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_role, current_text
        if current_role is None:
            return
        text = " ".join(t.strip() for t in current_text if t.strip()).strip()
        if text:
            turns.append({
                "turn_id": len(turns) + 1,
                "role": current_role,
                "text": text,
            })
        current_role = None
        current_text = []

    for raw in dialogue.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^\[(客户|坐席)\]\s*(.*)$", line)
        if match:
            flush()
            current_role = "customer" if match.group(1) == "客户" else "agent"
            current_text = [match.group(2).strip()]
        elif current_role is not None:
            current_text.append(line)
    flush()
    return turns


def dedupe_by_call_id(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    duplicate_count = 0
    for record in records:
        call_id = str(record.get("call_id") or "").strip()
        if not call_id:
            call_id = f"missing-call-id:{len(order) + 1}"
            record["call_id"] = call_id
        if call_id not in by_id:
            order.append(call_id)
        else:
            duplicate_count += 1
        # Keep the later object; observed duplicates are corrected repeats.
        by_id[call_id] = record
    return [by_id[call_id] for call_id in order], duplicate_count


def build_prepared_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for idx, record in enumerate(records, 1):
        dialogue, dialogue_source = choose_dialogue(record)
        turns = parse_turns(dialogue)
        prepared.append({
            "record_index": idx,
            "call_id": record.get("call_id"),
            "gold_intents": normalize_intents(record.get("意图")),
            "source_labels": {
                "小结名称": record.get("小结名称"),
                "一级分类": record.get("一级分类"),
                "二级分类": record.get("二级分类"),
                "服务标签": record.get("服务标签")
                if not (isinstance(record.get("服务标签"), str) and "[客户]" in record.get("服务标签", ""))
                else "",
            },
            "dialogue_source": dialogue_source,
            "turns": turns,
            "customer_turn_count": sum(1 for turn in turns if turn["role"] == "customer"),
            "source_line_no": record.get("_source_line_no"),
        })
    return prepared


def write_chunks(records: list[dict[str, Any]], out_dir: Path, chunk_count: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("chunk_*.jsonl"):
        old.unlink()

    chunk_size = max(1, (len(records) + chunk_count - 1) // chunk_count)
    paths: list[Path] = []
    for chunk_idx, start in enumerate(range(0, len(records), chunk_size), 1):
        path = out_dir / f"chunk_{chunk_idx:02d}.jsonl"
        paths.append(path)
        with path.open("w", encoding="utf-8") as f:
            for record in records[start:start + chunk_size]:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--chunks", type=int, default=6)
    args = parser.parse_args()

    raw_records, errors = parse_json_objects(args.input)
    deduped, duplicate_count = dedupe_by_call_id(raw_records)
    prepared = build_prepared_records(deduped)
    paths = write_chunks(prepared, args.out_dir, args.chunks)

    summary = {
        "input": str(args.input),
        "raw_objects": len(raw_records),
        "unique_records": len(deduped),
        "duplicate_call_ids_removed": duplicate_count,
        "parse_errors": errors,
        "chunk_count": len(paths),
        "chunk_paths": [str(path) for path in paths],
        "records_without_gold_intents": sum(1 for r in prepared if not r["gold_intents"]),
        "records_without_customer_turns": sum(1 for r in prepared if r["customer_turn_count"] == 0),
    }
    summary_path = args.out_dir.parent / "chunk_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
