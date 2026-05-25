# CLAUDE.md

This file gives current handoff guidance for Claude Code or another coding agent working in this repository.

## Project Overview

This is a financial customer-service copilot for human agents. It recommends compliant scripts, routes customer turns to structured business skills, queries mock business tools, and keeps multi-turn state. It is not a customer-facing chatbot.

The current implementation is Skill-based:

```text
Customer turn
  -> FastAPI gateway
  -> Orchestrator
  -> L0 preprocessing / identity / context
  -> Chain A rule shortcut, or Chain B hybrid recall + LLM skill router
  -> Skill tools / branch templates / compliant generation
  -> Chain C long-tail fallback when no valid skill is available
  -> Compliance check and context write-back
```

## Current Source Of Truth

Read these first:

- `README.md` for the current project map and common commands.
- `docs/当前评测链路索引.md` for active datasets, eval entrypoints, and report policy.
- `tests/EVAL_RUNBOOK.md` for offline evaluation commands.
- `docs/项目说明文档.md` for the longer architecture explanation.

## Runtime Structure

```text
fin_copilot/
├── main.py                         # FastAPI app and component assembly
├── orchestrator.py                 # main Chain A/B/C orchestration
├── config.py                       # paths, LLM fallback envs, routing knobs
├── routers/                        # /api/chat and demo endpoints
├── context/                        # sliding window, rolling summary, structured state
├── routing/                        # rule engine, domain classifier, hybrid skill recall, router
├── skills/loader.py                # loads root skills/registry.json and skills/definitions
├── agents/                         # compliant generation, confidence audit, long-tail fallback
├── knowledge/value_added.py         # structured activity/value-added-service retrieval
├── llm/                            # OpenAI-compatible client and profile selection
└── models/                         # conversation, skill, response, audit, tool IO models

skills/
├── registry.json                   # 54 skills across 11 domains
├── definitions/*.yaml              # one declarative skill per file
├── prompts/                        # router, generation, long-tail prompts
└── references/compliance/          # compliance rule assets

rules/rule_engine.json              # Chain A shortcut rules, currently 9
tools/                              # 11 registered mock business tools
tests/eval/                         # offline evaluation scripts
scripts/                            # data build, audit, eval helper scripts
```

## Common Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API and demo:

```bash
uvicorn fin_copilot.main:app --host 0.0.0.0 --port 8000
```

Open the demo after the server starts:

```text
http://localhost:8000/demo
```

Validate skills and focused tests:

```bash
python3 scripts/validate_skills.py
python3 -m pytest tests/unit/test_skill_schema.py tests/unit/test_value_added_knowledge.py
```

Run the current multi-turn golden smoke:

```bash
python3 tests/eval/merged_multi_turn_skill_recall.py \
  --route-mode skill-cos \
  --limit 20

python3 tests/eval/merged_multi_turn_skill_recall.py \
  --route-mode router \
  --model deepseek-v4-flash \
  --llm-timeout 120 \
  --limit 20
```

List or run multi-model golden commands:

```bash
bash run_golden_model_matrix.sh
LIMIT=20 bash run_golden_model_matrix.sh run deepseek-v4-flash
```

Run the older single-query wrapper:

```bash
MODEL=deepseek-v4-flash LLM_TIMEOUT=120 bash scripts/run_golden_full_eval.sh
```

## Data And Eval Scope

- `golden_test.jsonl`: current real-call multi-turn golden set, call-level `gold_intents + queries`.
- `raw_test.jsonl`: legacy single-query golden set.
- `原始300条数据.jsonl`: current multi-turn source file, formerly referred to as `merged.jsonl`.
- `scripts/references/merged_intent_skill_mapping.json`: current gold-intent to acceptable skill mapping.
- `tests/reports/*`: local generated artifacts, ignored by git by default. Regenerate them from scripts when handing off through git.

Do not use `test.jsonl` as the default current dataset; it is a legacy mode in a few scripts only.

## Development Notes

- `sop/` contains source business knowledge. Avoid editing original SOP files unless the task explicitly asks for SOP asset work.
- Skill changes should update `skills/definitions/*.yaml` and, when adding/removing skills, `skills/registry.json`.
- Keep metric layers separate: domain coverage, skill candidate coverage, and final LLM router Top1/Top3 are different numbers.
- Prefer `deepseek-v4-flash` for practical main-pass multi-turn evals; Pro profiles are available but slower and more timeout-prone.
- LLM profile selection lives in `config/llm_profiles.json`; legacy `.env` keys remain fallback compatibility only.
