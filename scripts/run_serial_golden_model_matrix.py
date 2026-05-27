#!/usr/bin/env python3
"""Serial runner for the multi-turn golden model matrix.

This intentionally does not invoke run_golden_model_matrix.sh.  It mirrors that
script's model/timeout/concurrency matrix, adds a model-level state file, and
refreshes an aggregate Markdown report after every model.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
EVAL_SCRIPT = ROOT / "tests" / "eval" / "merged_multi_turn_skill_recall.py"
CALLS_PATH = ROOT / "golden_test.jsonl"
CHUNK_SUMMARY_PATH = ROOT / "tests" / "merged_turn_filter" / "chunk_summary.json"


@dataclass(frozen=True)
class ModelSpec:
    model: str
    timeout: int
    concurrency: int
    progress_every: int
    note: str = ""


BASE_MODELS: list[ModelSpec] = [
    ModelSpec("kimi-k2.6", timeout=180, concurrency=4, progress_every=25),
    ModelSpec("MiniMax-M2.7", timeout=180, concurrency=3, progress_every=25),
    ModelSpec("qwen3.6-flash", timeout=120, concurrency=8, progress_every=25),
    ModelSpec("deepseek-v4-pro", timeout=240, concurrency=1, progress_every=10),
    ModelSpec("glm-5.1", timeout=180, concurrency=3, progress_every=25),
    ModelSpec("qwen3.6-plus", timeout=180, concurrency=4, progress_every=25),
]

FLASH_BASELINE = ModelSpec(
    "deepseek-v4-flash",
    timeout=120,
    concurrency=8,
    progress_every=25,
    note="extra flash baseline",
)


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_id_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sanitize_model(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def golden_stats() -> dict[str, int]:
    calls = load_jsonl(CALLS_PATH)
    denominator = len(calls)
    if CHUNK_SUMMARY_PATH.exists():
        data = load_json(CHUNK_SUMMARY_PATH, {})
        try:
            denominator = int(data.get("unique_records") or denominator)
        except (TypeError, ValueError):
            pass
    return {
        "calls": len(calls),
        "queries": sum(len(call.get("queries") or []) for call in calls),
        "gold_intents": sum(len(call.get("gold_intents") or []) for call in calls),
        "denominator": denominator,
    }


def summary_matches(summary: dict[str, Any], limit: int | None) -> bool:
    params = summary.get("params") or {}
    if params.get("limit") != limit:
        return False
    expected = golden_stats()
    if limit is None:
        return (
            summary.get("call_records_with_queries") == expected["calls"]
            and summary.get("query_predictions") == expected["queries"]
        )
    return summary.get("call_records_with_queries") == min(limit, expected["calls"])


def model_specs(args: argparse.Namespace) -> list[ModelSpec]:
    specs = list(BASE_MODELS)
    if args.include_flash:
        specs.append(FLASH_BASELINE)
    if args.models:
        wanted = [item.strip() for item in args.models.split(",") if item.strip()]
        by_model = {spec.model: spec for spec in specs}
        missing = [item for item in wanted if item not in by_model]
        if missing:
            raise SystemExit(f"unknown model(s): {', '.join(missing)}")
        specs = [by_model[item] for item in wanted]
    return specs


def effective_concurrency(spec: ModelSpec, max_concurrency: int) -> int:
    return max(1, min(spec.concurrency, max_concurrency))


def build_eval_command(
    *,
    python_bin: str,
    spec: ModelSpec,
    out_dir: Path,
    limit: int | None,
    max_concurrency: int,
) -> list[str]:
    cmd = [
        python_bin,
        "-u",
        str(EVAL_SCRIPT),
        "--route-mode",
        "router",
        "--model",
        spec.model,
        "--llm-timeout",
        str(spec.timeout),
        "--concurrency",
        str(effective_concurrency(spec, max_concurrency)),
        "--progress-every",
        str(spec.progress_every),
        "--no-llm-audit-one-to-many",
        "--out-dir",
        str(out_dir),
    ]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    return cmd


def run_one_model(
    *,
    spec: ModelSpec,
    args: argparse.Namespace,
    out_root: Path,
    state: dict[str, Any],
) -> None:
    model_key = spec.model
    out_dir = out_root / sanitize_model(spec.model)
    log_path = out_root / "logs" / f"{sanitize_model(spec.model)}.log"
    summary_path = out_dir / "summary.json"
    model_state = state.setdefault("models", {}).setdefault(model_key, {})

    existing_summary = load_json(summary_path, None)
    if (
        args.resume
        and isinstance(existing_summary, dict)
        and summary_matches(existing_summary, args.limit)
        and not args.force
    ):
        model_state.update(
            {
                "status": "success",
                "skipped_by_resume": True,
                "ended_at": now_ts(),
                "out_dir": str(out_dir),
                "summary_path": str(summary_path),
                "log_path": str(log_path),
            }
        )
        write_json(out_root / "matrix_state.json", state)
        print(f"[{spec.model}] skip: existing full summary found", flush=True)
        return

    if (
        args.resume
        and model_state.get("status") == "failed"
        and not args.rerun_failed
        and not args.force
    ):
        print(f"[{spec.model}] skip: previous failure recorded", flush=True)
        return

    cmd = build_eval_command(
        python_bin=args.python_bin,
        spec=spec,
        out_dir=out_dir,
        limit=args.limit,
        max_concurrency=args.max_concurrency,
    )
    model_state.update(
        {
            "status": "running",
            "started_at": now_ts(),
            "ended_at": None,
            "model": spec.model,
            "timeout": spec.timeout,
            "concurrency": effective_concurrency(spec, args.max_concurrency),
            "progress_every": spec.progress_every,
            "note": spec.note,
            "out_dir": str(out_dir),
            "summary_path": str(summary_path),
            "log_path": str(log_path),
            "command": cmd,
        }
    )
    write_json(out_root / "matrix_state.json", state)

    out_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    print(f"\n[{spec.model}] start {now_ts()}", flush=True)
    print(" ".join(cmd), flush=True)
    start = time.time()
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n\n=== {now_ts()} START {spec.model} ===\n")
        log.write("COMMAND: " + " ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        rc = proc.wait()
        elapsed = round(time.time() - start, 2)
        log.write(f"=== {now_ts()} END {spec.model} rc={rc} elapsed={elapsed}s ===\n")

    model_state.update(
        {
            "ended_at": now_ts(),
            "elapsed_seconds": elapsed,
            "returncode": rc,
            "status": "success" if rc == 0 and summary_path.exists() else "failed",
            "skipped_by_resume": False,
        }
    )
    if summary_path.exists():
        summary = load_json(summary_path, {})
        model_state["score_percent"] = summary.get("score_percent")
        model_state["router_errors"] = summary.get("router_errors")
        model_state["query_predictions"] = summary.get("query_predictions")
    write_json(out_root / "matrix_state.json", state)
    write_report(out_root)

    if model_state["status"] == "failed":
        print(f"[{spec.model}] failed rc={rc}; see {log_path}", flush=True)
        if args.stop_on_failure:
            raise SystemExit(rc or 1)
    else:
        print(f"[{spec.model}] done in {elapsed}s", flush=True)


def load_call_scores(out_dir: Path) -> list[dict[str, Any]]:
    path = out_dir / "call_scores.jsonl"
    if not path.exists():
        return []
    return load_jsonl(path)


def per_intent_stats(call_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    for row in call_scores:
        for item in row.get("mapped_gold_intents") or []:
            intent = item.get("intent")
            if intent:
                totals[intent] += 1
        for item in row.get("hit_gold_intents") or []:
            intent = item.get("intent")
            if intent:
                hits[intent] += 1
    rows = []
    for intent, total in totals.items():
        hit = hits[intent]
        miss = total - hit
        rows.append(
            {
                "intent": intent,
                "total": total,
                "hit": hit,
                "miss": miss,
                "hit_rate": hit / total if total else 0.0,
            }
        )
    rows.sort(key=lambda item: (-item["miss"], item["hit_rate"], item["intent"]))
    return rows


def model_output_dirs(out_root: Path) -> dict[str, Path]:
    state = load_json(out_root / "matrix_state.json", {})
    dirs: dict[str, Path] = {}
    for model, info in (state.get("models") or {}).items():
        out_dir = info.get("out_dir")
        if out_dir:
            dirs[model] = Path(out_dir)
    for child in out_root.iterdir() if out_root.exists() else []:
        if child.is_dir() and (child / "summary.json").exists():
            dirs.setdefault(child.name, child)
    return dirs


def fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "-"


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def write_report(out_root: Path) -> None:
    state = load_json(out_root / "matrix_state.json", {})
    stats = golden_stats()
    dirs = model_output_dirs(out_root)
    summaries: dict[str, dict[str, Any]] = {}
    call_scores_by_model: dict[str, list[dict[str, Any]]] = {}

    for model, out_dir in dirs.items():
        summary = load_json(out_dir / "summary.json", None)
        if isinstance(summary, dict):
            profile = summary.get("llm_profile") or {}
            model_id = profile.get("id") or model
            summaries[model_id] = summary
            call_scores_by_model[model_id] = load_call_scores(out_dir)

    lines: list[str] = []
    lines.append("# Golden Model Matrix Report")
    lines.append("")
    lines.append(f"- Updated at: {now_ts()}")
    lines.append(f"- Output root: `{out_root}`")
    lines.append(
        f"- Dataset: `{CALLS_PATH.name}` with {stats['calls']} calls, "
        f"{stats['queries']} routed queries, {stats['gold_intents']} gold intent labels; "
        f"denominator={stats['denominator']}."
    )
    lines.append("- Evaluation command: router mode, no one-to-many LLM audit, model-level serial execution.")
    lines.append("- Resume policy: existing completed summaries are skipped; failed models are not retried unless rerun explicitly.")
    lines.append("")

    model_rows = []
    for model, info in (state.get("models") or {}).items():
        summary = summaries.get(model)
        if summary:
            direct = ((summary.get("metric_breakdown") or {}).get("direct_mapped_accuracy") or {})
            model_rows.append(
                [
                    model,
                    info.get("status", "-"),
                    fmt_pct(summary.get("score_percent")),
                    fmt_pct(direct.get("score_percent")),
                    summary.get("full_score_calls", "-"),
                    summary.get("zero_score_calls", "-"),
                    summary.get("router_errors", "-"),
                    summary.get("elapsed_seconds", "-"),
                    f"`{summary.get('output_dir')}`",
                ]
            )
        else:
            model_rows.append(
                [
                    model,
                    info.get("status", "-"),
                    "-",
                    "-",
                    "-",
                    "-",
                    info.get("router_errors", "-"),
                    info.get("elapsed_seconds", "-"),
                    f"`{info.get('out_dir', '-')}`",
                ]
            )
    lines.extend(
        md_table(
            [
                "Model",
                "Status",
                "Score",
                "Direct mapped",
                "Full calls",
                "Zero calls",
                "Router errors",
                "Elapsed seconds",
                "Output",
            ],
            model_rows,
        )
    )
    lines.append("")

    successes = [
        (model, summary)
        for model, summary in summaries.items()
        if isinstance(summary.get("score_percent"), (int, float))
    ]
    successes.sort(key=lambda item: float(item[1].get("score_percent") or 0), reverse=True)
    lines.append("## Overall Analysis")
    lines.append("")
    if successes:
        best_model, best_summary = successes[0]
        worst_model, worst_summary = successes[-1]
        lines.append(
            f"- Best current score: `{best_model}` at {fmt_pct(best_summary.get('score_percent'))}."
        )
        lines.append(
            f"- Lowest current score among completed models: `{worst_model}` at {fmt_pct(worst_summary.get('score_percent'))}."
        )
        error_total = sum(int(summary.get("router_errors") or 0) for _, summary in successes)
        lines.append(f"- Completed models: {len(successes)}; total router errors across completed models: {error_total}.")
    else:
        lines.append("- No completed model summaries yet.")

    aggregate_intents: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "hit": 0, "miss": 0})
    for rows in call_scores_by_model.values():
        for row in per_intent_stats(rows):
            bucket = aggregate_intents[row["intent"]]
            bucket["total"] += int(row["total"])
            bucket["hit"] += int(row["hit"])
            bucket["miss"] += int(row["miss"])
    aggregate_rows = []
    for intent, row in aggregate_intents.items():
        total = row["total"]
        miss = row["miss"]
        hit_rate = row["hit"] / total if total else 0.0
        aggregate_rows.append([intent, total, row["hit"], miss, f"{hit_rate * 100:.2f}%"])
    aggregate_rows.sort(key=lambda row: (-int(row[3]), float(row[4].rstrip("%")), row[0]))
    if aggregate_rows:
        lines.append("")
        lines.append("### Cross-model Hardest Intents")
        lines.append("")
        lines.extend(md_table(["Intent", "Total", "Hit", "Miss", "Hit rate"], aggregate_rows[:15]))
    lines.append("")

    for model, summary in successes:
        out_dir = Path(summary.get("output_dir") or dirs.get(model) or "")
        rows = call_scores_by_model.get(model) or []
        intent_rows = per_intent_stats(rows)
        lines.append(f"## {model}")
        lines.append("")
        metric = summary.get("metric_breakdown") or {}
        direct = metric.get("direct_mapped_accuracy") or {}
        lines.append(
            f"- Score: {fmt_pct(summary.get('score_percent'))} "
            f"({summary.get('total_score')}/{summary.get('denominator')}); "
            f"direct mapped={fmt_pct(direct.get('score_percent'))}."
        )
        lines.append(
            f"- Full-score calls: {summary.get('full_score_calls')}; "
            f"zero-score calls: {summary.get('zero_score_calls')}; "
            f"router errors: {summary.get('router_errors')}; elapsed={summary.get('elapsed_seconds')}s."
        )
        lines.append(f"- Output: `{out_dir}`")
        if intent_rows:
            lines.append("")
            lines.append("### Intent Misses")
            lines.append("")
            top = [
                [
                    row["intent"],
                    row["total"],
                    row["hit"],
                    row["miss"],
                    f"{row['hit_rate'] * 100:.2f}%",
                ]
                for row in intent_rows[:10]
            ]
            lines.extend(md_table(["Intent", "Total", "Hit", "Miss", "Hit rate"], top))
        top_missed = summary.get("top_missed_intents") or []
        if top_missed:
            lines.append("")
            lines.append("### Common Miss Patterns")
            lines.append("")
            miss_rows = []
            for item in top_missed[:8]:
                miss_rows.append(
                    [
                        item.get("intent", ""),
                        item.get("count", ""),
                        "`" + ", ".join(item.get("predicted_topk") or []) + "`",
                    ]
                )
            lines.extend(md_table(["Intent", "Count", "Predicted topK"], miss_rows))
        lines.append("")

    failures = [
        (model, info)
        for model, info in (state.get("models") or {}).items()
        if info.get("status") == "failed"
    ]
    if failures:
        lines.append("## Failed Or Incomplete Models")
        lines.append("")
        failure_rows = [
            [
                model,
                info.get("returncode", "-"),
                info.get("elapsed_seconds", "-"),
                f"`{info.get('log_path', '-')}`",
            ]
            for model, info in failures
        ]
        lines.extend(md_table(["Model", "Return code", "Elapsed seconds", "Log"], failure_rows))
        lines.append("")

    (out_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used to run the eval script.",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "tests" / "reports" / f"golden_model_matrix_serial_{run_id_ts()}",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=3,
        help="Upper bound for per-model eval concurrency.",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated model ids to run. Defaults to the whole matrix.",
    )
    parser.add_argument("--include-flash", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true", help="Rerun even if summary.json exists.")
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help="Rerun models previously marked failed. Default is to skip them.",
    )
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only regenerate SUMMARY.md from an existing out-root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_root = args.out_root.resolve()
    args.out_root.mkdir(parents=True, exist_ok=True)

    state_path = args.out_root / "matrix_state.json"
    state = load_json(state_path, {})
    state.setdefault("created_at", now_ts())
    state["updated_at"] = now_ts()
    state["out_root"] = str(args.out_root)
    state["limit"] = args.limit
    state["max_concurrency"] = args.max_concurrency
    state["python_bin"] = args.python_bin
    state.setdefault("models", {})
    write_json(state_path, state)

    if args.report_only:
        write_report(args.out_root)
        print(args.out_root / "SUMMARY.md")
        return 0

    specs = model_specs(args)
    for spec in specs:
        run_one_model(spec=spec, args=args, out_root=args.out_root, state=state)
        state["updated_at"] = now_ts()
        write_json(state_path, state)

    write_report(args.out_root)
    print(f"\nReport: {args.out_root / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
