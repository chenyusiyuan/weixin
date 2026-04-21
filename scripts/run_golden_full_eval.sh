#!/usr/bin/env bash
set -Eeuo pipefail

# Run the full golden evaluation for the first two offline stages:
#   Exp1: L1 domain classification Top-1 / Top-K
#   Exp2: skill matching Top-1 / Top-3
#
# Usage:
#   bash scripts/run_golden_full_eval.sh
#
# Common overrides:
#   CONCURRENCY=20 bash scripts/run_golden_full_eval.sh
#   CLASSIFIER=rule bash scripts/run_golden_full_eval.sh
#   USE_FEWSHOT=1 FEWSHOT_K=5 bash scripts/run_golden_full_eval.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
CLASSIFIER="${CLASSIFIER:-embed}"
DOMAIN_TOP_K="${DOMAIN_TOP_K:-3}"
SKILL_MULTI_DOMAIN_K="${SKILL_MULTI_DOMAIN_K:-3}"
CONCURRENCY="${CONCURRENCY:-10}"
MIN_CONFIDENCE="${MIN_CONFIDENCE:-0.0}"
LIMIT="${LIMIT:-}"
PROGRESS_EVERY="${PROGRESS_EVERY:-50}"
USE_FEWSHOT="${USE_FEWSHOT:-0}"
FEWSHOT_K="${FEWSHOT_K:-5}"
RUN_EXP1="${RUN_EXP1:-1}"
RUN_EXP2="${RUN_EXP2:-1}"
DRY_RUN="${DRY_RUN:-0}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/tests/reports/golden_full_${TIMESTAMP}}"
RUN_LOG="$OUT_DIR/run.log"
SUMMARY_MD="$OUT_DIR/SUMMARY.md"
SUMMARY_JSON="$OUT_DIR/summary.json"

mkdir -p "$OUT_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$RUN_LOG"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || die "missing required file: $path"
}

line_count() {
  wc -l < "$1" | tr -d '[:space:]'
}

run_step() {
  local name="$1"
  shift
  local log_file="$OUT_DIR/${name}.log"

  log "START $name"
  log "CMD: $*"

  if [[ "$DRY_RUN" == "1" ]]; then
    printf '%q ' "$@" > "$log_file"
    printf '\n' >> "$log_file"
    log "DRY_RUN skipped $name"
    return 0
  fi

  set +e
  "$@" 2>&1 | tee "$log_file"
  local status=${PIPESTATUS[0]}
  set -e

  if [[ "$status" -ne 0 ]]; then
    log "FAILED $name exit=$status log=$log_file"
    exit "$status"
  fi

  log "DONE $name log=$log_file"
}

write_summary() {
  "$PYTHON_BIN" - "$OUT_DIR" "$SUMMARY_MD" "$SUMMARY_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
summary_md = Path(sys.argv[2])
summary_json = Path(sys.argv[3])

exp1_path = out_dir / "exp1_l1_domain.json"
exp2_path = out_dir / "exp2_skill_match.json"
data_counts_path = out_dir / "data_counts.json"

def pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

exp1 = load_json(exp1_path)
exp2 = load_json(exp2_path)
data_counts = load_json(data_counts_path)

metrics = {
    "golden_records": data_counts.get("golden_records"),
    "domain_top1_accuracy": exp1.get("overall_accuracy"),
    "domain_top3_accuracy": exp1.get("topk_recall"),
    "domain_total": exp1.get("total"),
    "skill_top1_accuracy": exp2.get("metrics", {}).get("skill_top1_accuracy"),
    "skill_top3_accuracy": exp2.get("metrics", {}).get("skill_top3_accuracy"),
    "skill_total": exp2.get("metrics", {}).get("total"),
}

summary_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "# Golden Full Evaluation Summary",
    "",
    f"- Golden records: {metrics['golden_records'] if metrics['golden_records'] is not None else 'N/A'}",
    f"- Domain evaluated: {metrics['domain_total'] if metrics['domain_total'] is not None else 'N/A'}",
    f"- Domain Top-1 accuracy: {pct(metrics['domain_top1_accuracy'])}",
    f"- Domain Top-3 accuracy: {pct(metrics['domain_top3_accuracy'])}",
    f"- Skill evaluated: {metrics['skill_total'] if metrics['skill_total'] is not None else 'N/A'}",
    f"- Skill Top-1 accuracy: {pct(metrics['skill_top1_accuracy'])}",
    f"- Skill Top-3 accuracy: {pct(metrics['skill_top3_accuracy'])}",
    "",
    "## Artifacts",
    "",
    f"- Exp1 JSON: `{exp1_path}`",
    f"- Exp1 log: `{out_dir / 'exp1_l1_domain.log'}`",
    f"- Exp2 JSON: `{exp2_path}`",
    f"- Exp2 log: `{out_dir / 'exp2_skill_match.log'}`",
    f"- Summary JSON: `{summary_json}`",
]
summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n".join(lines))
PY
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python not found: $PYTHON_BIN"

require_file "tests/golden_test.jsonl"
require_file "tests/eval/exp1_l1_domain.py"
require_file "tests/eval/exp2_skill_match.py"

GOLDEN_COUNT="$(line_count tests/golden_test.jsonl)"

cat > "$OUT_DIR/data_counts.json" <<JSON
{
  "golden_records": $GOLDEN_COUNT
}
JSON

log "Output dir: $OUT_DIR"
log "Golden records: $GOLDEN_COUNT"
log "Config: CLASSIFIER=$CLASSIFIER DOMAIN_TOP_K=$DOMAIN_TOP_K SKILL_MULTI_DOMAIN_K=$SKILL_MULTI_DOMAIN_K CONCURRENCY=$CONCURRENCY MIN_CONFIDENCE=$MIN_CONFIDENCE LIMIT=${LIMIT:-none} PROGRESS_EVERY=$PROGRESS_EVERY USE_FEWSHOT=$USE_FEWSHOT"

if [[ "$RUN_EXP1" == "1" ]]; then
  exp1_cmd=(
    "$PYTHON_BIN" -u "tests/eval/exp1_l1_domain.py" \
    --source golden \
    --classifier "$CLASSIFIER" \
    --top-k "$DOMAIN_TOP_K" \
    --min-confidence "$MIN_CONFIDENCE" \
    --progress-every "$PROGRESS_EVERY" \
    --json "$OUT_DIR/exp1_l1_domain.json"
  )
  if [[ -n "$LIMIT" ]]; then
    exp1_cmd+=(--limit "$LIMIT")
  fi
  run_step "exp1_l1_domain" "${exp1_cmd[@]}"
else
  log "SKIP exp1_l1_domain because RUN_EXP1=$RUN_EXP1"
fi

if [[ "$RUN_EXP2" == "1" ]]; then
  exp2_cmd=(
    "$PYTHON_BIN" -u "tests/eval/exp2_skill_match.py"
    --source golden
    --classifier "$CLASSIFIER"
    --multi-domain-k "$SKILL_MULTI_DOMAIN_K"
    --concurrency "$CONCURRENCY"
    --min-confidence "$MIN_CONFIDENCE"
    --json "$OUT_DIR/exp2_skill_match.json"
  )
  if [[ -n "$LIMIT" ]]; then
    exp2_cmd+=(--limit "$LIMIT")
  fi
  if [[ "$USE_FEWSHOT" == "1" ]]; then
    exp2_cmd+=(--fewshot --fewshot-k "$FEWSHOT_K")
  fi
  run_step "exp2_skill_match" "${exp2_cmd[@]}"
else
  log "SKIP exp2_skill_match because RUN_EXP2=$RUN_EXP2"
fi

log "Writing summary"
write_summary | tee -a "$RUN_LOG"
log "Summary: $SUMMARY_MD"
