"""Exp 3 — Chain distribution, latency, and compliance on the golden set.

For each query in ``raw_test.jsonl`` (or the legacy ``test.jsonl`` when
available), run the full orchestrator and record:

    * route distribution (A / A_sticky / B / C)
    * latency P50 / P95 / per-route
    * compliance pass rate
    * per-route skill top-15

Usage::

    # full golden run (2846, concurrent)
    python tests/eval/exp3_chain_distribution.py --source golden --concurrency 10

    # smoke
    python tests/eval/exp3_chain_distribution.py --source golden --limit 50 --concurrency 5

    # legacy
    python tests/eval/exp3_chain_distribution.py --source test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fin_copilot.config import get_settings  # noqa: E402
from fin_copilot.llm.profiles import select_llm_profile  # noqa: E402
from fin_copilot.main import build_orchestrator  # noqa: E402


GOLDEN_PATH = _project_root / "raw_test.jsonl"
LEGACY_PATH = _project_root / "test.jsonl"


def extract_first_customer_msg(dialog: str) -> str:
    for line in dialog.split("\n"):
        line = line.strip()
        if line.startswith("[客户]"):
            return line.replace("[客户]", "", 1).strip()
    return ""


def load_records(source: str) -> list[dict[str, Any]]:
    """Return [{query, gold_skill?, gold_l1?, gold_l2?}, ...]."""
    if source == "golden":
        if not GOLDEN_PATH.exists():
            raise FileNotFoundError(GOLDEN_PATH)
        out = []
        with open(GOLDEN_PATH, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                q = (d.get("query") or "").strip()
                if not q:
                    continue
                out.append({
                    "query": q,
                    "call_id": d.get("call_id", ""),
                    "gold_skill": d.get("gold_skill", ""),
                    "confidence": d.get("confidence", 0.0),
                })
        return out
    if source == "test":
        if not LEGACY_PATH.exists():
            raise FileNotFoundError(LEGACY_PATH)
        out = []
        with open(LEGACY_PATH, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                q = extract_first_customer_msg(rec.get("完整对话_清洗后", ""))
                if not q:
                    continue
                out.append({
                    "query": q,
                    "gold_l1": rec.get("一级分类", ""),
                    "gold_l2": rec.get("二级分类", ""),
                })
        return out
    raise ValueError(f"unknown source {source!r}")


async def run_one(orch, idx: int, rec: dict, *, verified: bool = True) -> dict | None:
    q = rec["query"]
    sid = f"exp3-{idx}"
    # Pre-seed the session so identity verification doesn't short-circuit
    # every business query. Exp3 is a *routing* benchmark, not an auth flow
    # benchmark — each query is assumed to belong to an already-verified user.
    if verified:
        state = orch.ctx.get_or_create(sid)
        state.customer.verified = True
        state.customer.verification_level = "full"
        state.customer.verification_step = "passed"
        state.customer.name_masked = "张*三"
        state.customer.customer_id = "C100"
    t0 = time.monotonic()
    try:
        resp = await orch.handle_turn(sid, q)
    except Exception as exc:  # pragma: no cover
        return {"index": idx, "query": q, "error": str(exc)}
    latency = (time.monotonic() - t0) * 1000
    return {
        "index": idx,
        "query": q,
        "gold_skill": rec.get("gold_skill", ""),
        "gold_l1": rec.get("gold_l1", ""),
        "gold_l2": rec.get("gold_l2", ""),
        "confidence_gold": rec.get("confidence", 0.0),
        "predicted_skill": resp.matched_skill_id,
        "route": resp.route,
        "confidence": resp.confidence,
        "latency_ms": latency,
        "compliance_passed": resp.compliance_passed,
    }


async def run_eval(args) -> int:
    settings = get_settings()
    try:
        llm_profile = select_llm_profile(args.model, settings, timeout=args.llm_timeout)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    records = load_records(args.source)
    if args.limit:
        records = records[: args.limit]
    print(f"[exp3] loaded {len(records)} records from source={args.source}")
    print(
        f"[exp3] LLM profile: {llm_profile.id}  model={llm_profile.model}  "
        f"url={llm_profile.api_url}  timeout={llm_profile.timeout:g}s"
    )
    orch, llm_client = build_orchestrator(settings, llm_profile=llm_profile)

    sem = asyncio.Semaphore(args.concurrency)
    results: list[dict] = []
    progress_every = max(1, len(records) // 20)

    async def worker(i: int, rec: dict) -> None:
        async with sem:
            r = await run_one(orch, i, rec, verified=args.pre_verified)
            if r is not None:
                results.append(r)
                if len(results) % progress_every == 0:
                    print(f"  progress {len(results)}/{len(records)}")

    tasks = [asyncio.create_task(worker(i, rec)) for i, rec in enumerate(records)]
    await asyncio.gather(*tasks)
    await llm_client.close()

    # Order by index for deterministic output
    results.sort(key=lambda r: r["index"])
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"[exp3] wrote per-record JSON → {args.json}")

    print_report(results, args.source)
    return 0


def print_report(results: list[dict], source: str) -> None:
    if not results:
        print("No results to report.")
        return

    total = len(results)
    good = [r for r in results if "error" not in r]
    err_cnt = total - len(good)
    print("=" * 64)
    print("  EXP3 — CHAIN DISTRIBUTION REPORT")
    print(f"  source={source}  evaluated={len(good)}  errors={err_cnt}")
    print("=" * 64)

    # Route distribution
    route_counts = Counter(r["route"] for r in good)
    print("\n--- Route Distribution ---")
    for route, count in route_counts.most_common():
        pct = count / len(good) * 100 if good else 0
        print(f"  {route:<22s} {count:>5d} ({pct:5.1f}%)")

    # Latency stats
    lats = [r["latency_ms"] for r in good]
    if lats:
        lats_sorted = sorted(lats)
        p50 = lats_sorted[len(lats_sorted) // 2]
        p95 = lats_sorted[min(int(len(lats_sorted) * 0.95), len(lats_sorted) - 1)]
        print("\n--- Latency (ms) ---")
        print(f"  Avg:  {statistics.mean(lats):.1f}")
        print(f"  P50:  {p50:.1f}")
        print(f"  P95:  {p95:.1f}")
        print(f"  Min:  {min(lats):.1f}")
        print(f"  Max:  {max(lats):.1f}")
        print("\n--- Per-Route Latency ---")
        for route in route_counts:
            rlats = [r["latency_ms"] for r in good if r["route"] == route]
            rlats_sorted = sorted(rlats)
            p95r = rlats_sorted[min(int(len(rlats_sorted) * 0.95), len(rlats_sorted) - 1)]
            print(f"  {route:<22s} avg={statistics.mean(rlats):>7.1f}  p95={p95r:>7.1f}  n={len(rlats)}")

    # Compliance
    cok = sum(1 for r in good if r["compliance_passed"])
    print("\n--- Compliance ---")
    print(f"  Pass rate: {cok}/{len(good)} ({cok / len(good) * 100:.1f}%)")

    # Skill distribution
    skill_counts = Counter(r["predicted_skill"] or "(none)" for r in good)
    print("\n--- Predicted Skills (Top 20) ---")
    for skill, count in skill_counts.most_common(20):
        print(f"  {skill:<38s} {count:>4d}")

    # gold_skill accuracy (golden source only)
    if source == "golden":
        with_gold = [r for r in good if r.get("gold_skill")]
        hit = sum(1 for r in with_gold if r["predicted_skill"] == r["gold_skill"])
        if with_gold:
            print("\n--- Top-1 vs Gold Skill (golden-only) ---")
            print(f"  {hit}/{len(with_gold)} = {hit / len(with_gold) * 100:.1f}%")

    print("=" * 64)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["golden", "test"], default="golden")
    p.add_argument("--limit", type=int, default=0,
                   help="truncate to first N records (0 = all)")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--model", "--llm-profile", dest="model", default=None,
                   help="LLM profile id or model name from config/llm_profiles.json")
    p.add_argument("--llm-timeout", type=float, default=None,
                   help="override selected profile timeout for this batch run")
    p.add_argument("--json", default="", help="per-record JSON output path")
    p.add_argument("--pre-verified", action="store_true", default=True,
                   help="pre-seed each session as verified (default on)")
    p.add_argument("--no-pre-verified", action="store_false", dest="pre_verified",
                   help="disable pre-verification; exercise identity flow")
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_eval(parse_args())))
