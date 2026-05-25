#!/usr/bin/env bash
set -Eeuo pipefail

# DeepSeek Flash / Pro multi-turn golden evaluation command matrix.
# Models are selected through config/llm_profiles.json via --model, not by
# overriding LLM_MODEL in the environment.
#
# Default behavior only prints commands:
#   bash scripts/run_multiturn_model_profiles.sh
#
# Run one profile:
#   bash scripts/run_multiturn_model_profiles.sh run flash_full
#   bash scripts/run_multiturn_model_profiles.sh run pro_probe
#
# Useful overrides:
#   LIMIT=50 bash scripts/run_multiturn_model_profiles.sh run flash_smoke
#   OUT_DIR=tests/reports/my_run bash scripts/run_multiturn_model_profiles.sh run pro_safe
#   PYTHON_BIN=python3 bash scripts/run_multiturn_model_profiles.sh run flash_full

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
EVAL_SCRIPT="tests/eval/merged_multi_turn_skill_recall.py"

MODE="${1:-list}"
PROFILE="${2:-}"

print_cmd() {
  local name="$1"
  shift
  printf '\n[%s]\n' "$name"
  printf '  '
  printf '%q ' "$@"
  printf '\n'
}

run_cmd() {
  local name="$1"
  shift
  print_cmd "$name" "$@"
  if [[ "$MODE" == "run" && "$PROFILE" == "$name" ]]; then
    exec "$@"
  fi
}

profile_flash_probe() {
  run_cmd flash_probe \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-flash \
    --llm-timeout 60 \
    --limit "${LIMIT:-1}" \
    --concurrency 1 \
    --progress-every 1 \
    --no-use-cache \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_flash_smoke() {
  run_cmd flash_smoke \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-flash \
    --llm-timeout 60 \
    --limit "${LIMIT:-20}" \
    --concurrency 4 \
    --progress-every 5 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_flash_full() {
  run_cmd flash_full \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-flash \
    --llm-timeout 60 \
    --concurrency 4 \
    --progress-every 25 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_flash_full_fast() {
  run_cmd flash_full_fast \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-flash \
    --llm-timeout 90 \
    --concurrency 8 \
    --progress-every 25 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_flash_route_only() {
  run_cmd flash_route_only \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-flash \
    --llm-timeout 60 \
    --concurrency 4 \
    --progress-every 25 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_pro_probe() {
  run_cmd pro_probe \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-pro \
    --llm-timeout 180 \
    --limit "${LIMIT:-1}" \
    --concurrency 1 \
    --progress-every 1 \
    --no-use-cache \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_pro_smoke() {
  run_cmd pro_smoke \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-pro \
    --llm-timeout 180 \
    --limit "${LIMIT:-20}" \
    --concurrency 1 \
    --progress-every 1 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_pro_safe() {
  run_cmd pro_safe \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-pro \
    --llm-timeout 180 \
    --concurrency 1 \
    --progress-every 10 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_pro_route_only() {
  run_cmd pro_route_only \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-pro \
    --llm-timeout 180 \
    --concurrency 1 \
    --progress-every 10 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_pro_parallel_risky() {
  run_cmd pro_parallel_risky \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-pro \
    --llm-timeout 240 \
    --concurrency 2 \
    --progress-every 10 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_flash_full_with_audit() {
  run_cmd flash_full_with_audit \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-flash \
    --llm-timeout 90 \
    --concurrency 4 \
    --progress-every 25 \
    --llm-audit-one-to-many \
    --audit-concurrency 2 \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_pro_safe_with_audit() {
  run_cmd pro_safe_with_audit \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode router \
    --model deepseek-v4-pro \
    --llm-timeout 240 \
    --concurrency 1 \
    --progress-every 10 \
    --llm-audit-one-to-many \
    --audit-concurrency 1 \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

profile_skill_cos_baseline() {
  run_cmd skill_cos_baseline \
    "$PYTHON_BIN" "$EVAL_SCRIPT" \
    --route-mode skill-cos \
    --concurrency 8 \
    --progress-every 50 \
    --no-llm-audit-one-to-many \
    ${OUT_DIR:+--out-dir "$OUT_DIR"}
}

list_profiles() {
  cat <<'EOF'
Profiles:
  flash_probe          Flash, 1 call, no cache/audit, quick connectivity probe.
  flash_smoke          Flash, default LIMIT=20, route-only smoke.
  flash_full           Flash, recommended full run: concurrency=4 timeout=60, no audit.
  flash_full_fast      Flash, faster full run: concurrency=8 timeout=90, no audit.
  flash_route_only     Flash full routing without one-to-many LLM audit.
  flash_full_with_audit
                       Flash full run plus optional one-to-many LLM audit.
  pro_probe            Pro, 1 call, no cache/audit, latency probe.
  pro_smoke            Pro, default LIMIT=20, conservative smoke.
  pro_safe             Pro full run: concurrency=1 timeout=180, no audit.
  pro_route_only       Pro full routing without one-to-many LLM audit.
  pro_parallel_risky   Pro with concurrency=2 timeout=240, no audit; may still timeout.
  pro_safe_with_audit  Pro full run plus optional one-to-many LLM audit.
  skill_cos_baseline   No LLM router, embedding cosine baseline.

Usage:
  bash scripts/run_multiturn_model_profiles.sh
  bash scripts/run_multiturn_model_profiles.sh run flash_full
  LIMIT=50 bash scripts/run_multiturn_model_profiles.sh run pro_smoke
  OUT_DIR=tests/reports/custom bash scripts/run_multiturn_model_profiles.sh run flash_probe
EOF
}

all_profiles() {
  profile_flash_probe
  profile_flash_smoke
  profile_flash_full
  profile_flash_full_fast
  profile_flash_route_only
  profile_flash_full_with_audit
  profile_pro_probe
  profile_pro_smoke
  profile_pro_safe
  profile_pro_route_only
  profile_pro_parallel_risky
  profile_pro_safe_with_audit
  profile_skill_cos_baseline
}

if [[ "$MODE" == "help" || "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  list_profiles
  exit 0
fi

if [[ "$MODE" == "list" ]]; then
  list_profiles
  all_profiles
  exit 0
fi

if [[ "$MODE" != "run" || -z "$PROFILE" ]]; then
  echo "ERROR: expected: bash scripts/run_multiturn_model_profiles.sh run <profile>" >&2
  list_profiles >&2
  exit 2
fi

all_profiles
echo "ERROR: unknown profile: $PROFILE" >&2
exit 2
