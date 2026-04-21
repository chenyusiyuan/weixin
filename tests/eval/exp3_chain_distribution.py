"""Offline evaluation against test.jsonl.

For each conversation:
  1. Extract the first customer utterance from 完整对话_清洗后
  2. Run through orchestrator.handle_turn()
  3. Record: skill_id, route, latency, compliance

Output report:
  - Route distribution
  - Average / P50 / P95 latency
  - Compliance pass rate
  - Skill match details (when LLM is available)
"""

from __future__ import annotations

import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fin_copilot.config import get_settings
from fin_copilot.main import build_orchestrator


def extract_first_customer_msg(dialog: str) -> str:
    """Extract the first [客户] line from the cleaned dialog."""
    for line in dialog.split("\n"):
        line = line.strip()
        if line.startswith("[客户]"):
            msg = line.replace("[客户]", "").strip()
            if msg:
                return msg
    return ""


def extract_all_customer_msgs(dialog: str, max_turns: int = 3) -> list[str]:
    """Extract up to max_turns customer messages."""
    msgs: list[str] = []
    for line in dialog.split("\n"):
        line = line.strip()
        if line.startswith("[客户]"):
            msg = line.replace("[客户]", "").strip()
            if msg:
                msgs.append(msg)
                if len(msgs) >= max_turns:
                    break
    return msgs


async def run_eval() -> None:
    test_path = Path(_project_root) / "test.jsonl"
    if not test_path.exists():
        print(f"ERROR: {test_path} not found")
        return

    with open(test_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(records)} test records")
    print("=" * 60)

    settings = get_settings()
    orch, llm_client = build_orchestrator(settings)

    results: list[dict] = []

    for i, record in enumerate(records):
        dialog = record.get("完整对话_清洗后", "")
        first_msg = extract_first_customer_msg(dialog)
        if not first_msg:
            continue

        session_id = f"eval-{i}"
        start = time.monotonic()
        try:
            response = await orch.handle_turn(session_id, first_msg)
        except Exception as exc:
            print(f"  [{i}] ERROR: {exc}")
            continue
        latency = (time.monotonic() - start) * 1000

        results.append({
            "index": i,
            "query": first_msg,
            "predicted_skill": response.matched_skill_id,
            "route": response.route,
            "confidence": response.confidence,
            "latency_ms": latency,
            "compliance_passed": response.compliance_passed,
            "ground_truth_label": record.get("服务标签", ""),
            "ground_truth_l1": record.get("一级分类", ""),
            "ground_truth_l2": record.get("二级分类", ""),
            "ground_truth_summary": record.get("小结名称", ""),
        })

    await llm_client.close()
    print_report(results)


def print_report(results: list[dict]) -> None:
    if not results:
        print("No results to report.")
        return

    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"  OFFLINE EVALUATION REPORT")
    print(f"  Total evaluated: {total}")
    print(f"{'=' * 60}")

    # Route distribution
    route_counts = Counter(r["route"] for r in results)
    print(f"\n--- Route Distribution ---")
    for route, count in route_counts.most_common():
        pct = count / total * 100
        print(f"  {route:<20s} {count:>3d} ({pct:.1f}%)")

    # Latency stats
    latencies = [r["latency_ms"] for r in results]
    latencies_sorted = sorted(latencies)
    avg_lat = statistics.mean(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]
    print(f"\n--- Latency (ms) ---")
    print(f"  Avg:  {avg_lat:.1f}")
    print(f"  P50:  {p50:.1f}")
    print(f"  P95:  {p95:.1f}")
    print(f"  Min:  {min(latencies):.1f}")
    print(f"  Max:  {max(latencies):.1f}")

    # Route-specific latency
    for route in route_counts:
        route_lats = [r["latency_ms"] for r in results if r["route"] == route]
        if route_lats:
            print(f"  {route}: avg={statistics.mean(route_lats):.1f} p95={sorted(route_lats)[int(len(route_lats)*0.95)]:.1f}")

    # Compliance pass rate
    compliance_ok = sum(1 for r in results if r["compliance_passed"])
    print(f"\n--- Compliance ---")
    print(f"  Pass rate: {compliance_ok}/{total} ({compliance_ok/total*100:.1f}%)")

    # Skill match details
    skill_counts = Counter(r["predicted_skill"] for r in results)
    print(f"\n--- Predicted Skills (Top 15) ---")
    for skill, count in skill_counts.most_common(15):
        print(f"  {skill or '(none)':<35s} {count:>3d}")

    # Route A matches
    route_a = [r for r in results if r["route"] == "route_a"]
    if route_a:
        print(f"\n--- Route A Matches ({len(route_a)}) ---")
        for r in route_a[:10]:
            print(f"  [{r['index']}] \"{r['query'][:30]}\" -> {r['predicted_skill']}")

    # Ground truth coverage
    print(f"\n--- Ground Truth L1 Distribution ---")
    l1_counts = Counter(r["ground_truth_l1"] for r in results)
    for l1, count in l1_counts.most_common():
        print(f"  {l1:<20s} {count:>3d}")

    print(f"\n{'=' * 60}")
    print(f"  NOTE: Route B accuracy requires LLM (Ollama) running.")
    print(f"  Start Ollama and rerun for full evaluation.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(run_eval())
