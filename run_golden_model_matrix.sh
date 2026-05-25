#!/usr/bin/env bash
set -Eeuo pipefail

# Multi-turn golden evaluation matrix for config/llm_profiles.json.
#
# Default lists the exact commands without running them:
#   bash run_golden_model_matrix.sh
#
# Run one model:
#   bash run_golden_model_matrix.sh run deepseek-v4-flash
#
# Run every model sequentially:
#   bash run_golden_model_matrix.sh run-all
#
# Common overrides:
#   LIMIT=20 bash run_golden_model_matrix.sh run qwen3.6-flash
#   OUT_ROOT=tests/reports/my_model_matrix bash run_golden_model_matrix.sh run-all
#   PYTHON_BIN=python3 bash run_golden_model_matrix.sh run deepseek-v4-pro

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
EVAL_SCRIPT="${EVAL_SCRIPT:-tests/eval/merged_multi_turn_skill_recall.py}"
MODE="${1:-list}"
TARGET_MODEL="${2:-}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_ROOT="${OUT_ROOT:-tests/reports/golden_model_matrix_${TIMESTAMP}}"
FOUND=0

sanitize_model() {
  printf '%s' "$1" | tr '/:' '__'
}

print_cmd() {
  printf '  '
  printf '%q ' "$@"
  printf '\n'
}

model_cmd() {
  local model="$1"
  local timeout="$2"
  local concurrency="$3"
  local progress_every="$4"
  local out_dir="$OUT_ROOT/$(sanitize_model "$model")"
  local cmd=(
    "$PYTHON_BIN" -u "$EVAL_SCRIPT"
    --route-mode router
    --model "$model"
    --llm-timeout "$timeout"
    --concurrency "$concurrency"
    --progress-every "$progress_every"
    --no-llm-audit-one-to-many
    --out-dir "$out_dir"
  )
  if [[ -n "${LIMIT:-}" ]]; then
    cmd+=(--limit "$LIMIT")
  fi

  if [[ "$MODE" == "list" ]]; then
    printf '\n[%s] timeout=%ss concurrency=%s\n' "$model" "$timeout" "$concurrency"
    print_cmd "${cmd[@]}"
    return 0
  fi

  if [[ "$MODE" == "run" && "$TARGET_MODEL" == "$model" ]]; then
    FOUND=1
    printf '\n[%s]\n' "$model"
    print_cmd "${cmd[@]}"
    exec "${cmd[@]}"
  fi

  if [[ "$MODE" == "run-all" ]]; then
    FOUND=1
    printf '\n[%s]\n' "$model"
    print_cmd "${cmd[@]}"
    "${cmd[@]}"
  fi
}

list_models() {
  # One explicit command line per model profile. The timeout/concurrency values
  # are tuned for batch stability rather than the fastest possible wall-clock.
  model_cmd ollama-qwen3.5-9b 180 1 10
  model_cmd kimi-k2.6 180 4 25
  model_cmd MiniMax-M2.7 180 3 25
  model_cmd qwen3.6-flash 120 8 25
  model_cmd deepseek-v4-pro 240 1 10
  model_cmd deepseek-v4-flash 120 8 25
  model_cmd glm-5.1 180 3 25
  model_cmd qwen3.6-plus 180 4 25
  model_cmd coder-claude4.7-opus 360 1 10
  model_cmd claude-sonnet-4-6 240 2 10
  model_cmd claude-sonnet-4-6-thinking 420 1 10
  model_cmd gpt-5.5 360 1 10
}

if [[ "$MODE" == "help" || "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  sed -n '3,17p' "$0"
  exit 0
fi

if [[ "$MODE" != "list" && "$MODE" != "run" && "$MODE" != "run-all" ]]; then
  echo "ERROR: expected mode: list | run <model> | run-all" >&2
  exit 2
fi

if [[ "$MODE" == "run" && -z "$TARGET_MODEL" ]]; then
  echo "ERROR: expected: bash run_golden_model_matrix.sh run <model>" >&2
  exit 2
fi

list_models

if [[ "$MODE" == "run" && "$FOUND" == "0" ]]; then
  echo "ERROR: unknown model: $TARGET_MODEL" >&2
  exit 2
fi
