# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**金融客服坐席话术推荐系统 (Financial Customer Service Agent Script Recommendation System)**

A Copilot system that assists human customer service agents with real-time script recommendations, tool-assisted data lookups, and compliance checking. This is NOT a customer-facing chatbot — it's a behind-the-scenes assistant for human agents.

The system is transitioning from a RAG-based architecture (v1, in `v/`) to a **Skill-based architecture** where SOP knowledge is compiled into structured YAML Skill definitions rather than flat vector chunks.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI + Pydantic v2 + asyncio + httpx
- **LLM:** Any OpenAI-compatible API (DeepSeek via `.env`, or Ollama `qwen2.5:7b` at `localhost:11434/v1`)
- **Embedding:** bge-m3 via Ollama (`localhost:11434/api/embed`) — only when Chain C RAG is active
- **Vector DB:** Milvus Lite (only for Chain C fallback RAG)
- **Templating:** Jinja2 (for script slot filling)
- **Skill definitions:** YAML (PyYAML)

## Common Commands

```bash
# Install deps
pip install -r requirements.txt

# Run API server
uvicorn fin_copilot.main:app --host 0.0.0.0 --port 8000

# CLI demo (interactive)
python -m fin_copilot.cli_demo

# Offline evaluation against test.jsonl (98 real conversations)
python tests/eval_offline.py

# Sample API call
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "s1", "user_text": "怎么还款"}'
```

LLM config lives in `.env` (keys: `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`). Project currently defaults to DeepSeek (`api.deepseek.com/v1`, model `deepseek-chat`). Other tunables: `SLIDING_WINDOW_SIZE` (8), `SUMMARY_MAX_LENGTH` (300), `TOOL_CACHE_TTL` (300s), `CONFIDENCE_THRESHOLD` (0.5), `ROUTING_TEMPERATURE` (0.1), `GENERATION_TEMPERATURE` (0.3).

No formal test framework is wired up; `tests/eval_offline.py` is the functional evaluation entry point (prints route distribution, p50/p95 latency, compliance pass rate).

## Design Documents (Authoritative References)

- `codegen_prompts.md` — Step-by-step implementation plan with code specs. **Follow this when writing code.**
- `技术方案设计文档.md` — Detailed technical architecture, state machine design, compliance model, and evaluation criteria.
- `skill-based方案.md` — High-level rationale for why Skill-based replaces RAG-first, plus architecture overview.

## Architecture: Three Chains

All requests flow through one of three chains, auto-routed by confidence:

```
Input → L0 Preprocessing → Rule Engine match?
  ├─ YES → Chain A: Rule Shortcut (<200ms, zero LLM, template + tool data)
  └─ NO  → L1 Domain Classifier → LLM Skill Routing
              ├─ match (confidence ≥ θ) → Chain B: Skill Route (1-3s, 2 LLM calls)
              └─ no match             → Chain C: Long-tail Autonomous (1.5-3s, LLM + RAG assist)
```

- **Chain A:** Zero LLM. Rule match → Tool execution → Jinja2 template fill → Rule compliance. For verified high-frequency scenarios.
- **Chain B:** Main chain. L1 classifier narrows to 4-8 skill candidates → LLM Skill Routing → Agent B confidence audit (rules, <10ms) + Tool execution (parallel) → Agent A compliant generation → Post-rule compliance.
- **Chain C:** Fallback for unknown scenarios. LLM autonomous reasoning + lightweight RAG (Milvus Top-3 as reference, not template). Stricter compliance: read-only tools only, no commitments, mandatory disclaimer.

## Target Directory Structure

```
fin_copilot/                    # Main application package
├── config.py                   # pydantic-settings configuration
├── main.py                     # FastAPI entry point
├── cli_demo.py                 # CLI demo entry
├── models/                     # Pydantic data models
│   ├── conversation.py         # ConversationState (Layer 1/2/3)
│   ├── skill.py                # SkillDefinition, SkillMatch
│   ├── tool_io.py              # ToolResults
│   ├── response.py             # CopilotResponse
│   └── audit.py                # ConfidenceAuditResult
├── context/                    # Three-layer context management
│   ├── sliding_window.py       # Layer 1: recent 6-8 turns
│   ├── rolling_summary.py      # Layer 2: compressed history (≤300 chars)
│   ├── structured_state.py     # Layer 3: slots, tool_cache, risk_flags
│   └── context_manager.py      # Unified context orchestrator
├── routing/                    # Chain routing
│   ├── rule_engine.py          # Chain A: keyword/regex rule shortcut
│   ├── domain_classifier.py    # L1 domain classifier (10 domains)
│   └── skill_router.py         # Chain B: LLM Skill Routing
├── agents/                     # Agent implementations
│   ├── compliant_generator.py  # Agent A: compliance-embedded generation
│   ├── confidence_auditor.py   # Agent B: rule-based confidence audit
│   └── longtail_reasoner.py    # Chain C: autonomous reasoning
├── orchestrator.py             # Main orchestrator (dispatches chains)
├── skills/
│   └── loader.py               # YAML Skill loader (indexes skills/registry.json)
├── compliance/
│   └── rule_checker.py         # Post-generation compliance (regex + rules, <5ms)
├── llm/
│   └── client.py               # Async LLM client (OpenAI-compatible)
├── routers/
│   └── gateway.py              # FastAPI route handlers
└── utils/
    ├── trace.py                # Chain tracing (trace_id propagation)
    └── template_engine.py      # Jinja2 template rendering

tools/                          # Business tool handlers (top-level, NOT under fin_copilot/)
├── registry.py                 # Tool registry + WRITE_TOOLS set
├── executor.py                 # Parallel executor (asyncio.gather)
├── mock_data.py                # VERIFICATION_DB, PHONE_TO_CUSTOMER fixtures
└── *.py                        # get_customer_profile, get_bill_and_repayment_plan, etc.

skills/                         # Skill knowledge layer (config, not code)
├── registry.json               # Skill index by domain
├── definitions/                # One YAML per skill (51 total)
├── prompts/                    # LLM prompt templates (skill_routing.md, compliant_gen.md, etc.)
└── references/compliance/      # Forbidden words, key rules (hot-updatable)

rules/                          # Chain A hardcoded rules (auto-promoted from skills)
└── rule_engine.json

sop/                            # SOP business knowledge assets (READ-ONLY reference)
├── clean/                      # Processed SOP data pipeline
│   ├── 01_raw_extract/         # Raw JSON extracts from xlsx/docx
│   ├── 02_cleaned/             # Cleaned JSON
│   ├── 03_chunks/              # 874 text chunks (legacy RAG, reused in Chain C)
│   └── 04_embedded/            # Embeddings + Milvus DB
└── [domain_folders]/           # Original xlsx/docx SOP documents
```

## Key Design Concepts

### Skill = Decision Closure
A Skill YAML bundles: trigger conditions, required tools, progressive templates (by conversation turn), branch conditions, compliance rules, escalation triggers, and fallback scripts. See `技术方案设计文档.md` §5.2 for the full schema.

### Three-Layer Context (State Machine)
- **Layer 1 (Sliding Window):** Last 6-8 turns of raw dialogue. Consumed by LLM prompts.
- **Layer 2 (Rolling Summary):** Rule-based incremental summary of older turns (≤300 chars). No LLM used — event extraction + template concatenation.
- **Layer 3 (Structured State):** `customer`, `intent` (current_skill_id, turn_in_skill), `slots`, `tool_cache`, `risk_flags`, `compliance_state`. Shared fact source for all modules.

### Agent B (Confidence Audit) is Pure Rules
Agent B is NOT an LLM call. It's a scoring function: starts at 1.0, deducts for low confidence, domain mismatch, missing slots, tool failures, etc. Threshold ≥ 0.5 to pass. Runs in <10ms, parallel with tool execution.

### Compliance: Three Layers
1. **Pre-generation:** Agent A's prompt embeds per-skill forbidden expressions + required disclaimers
2. **Parallel audit:** Agent B rule-based checks before generation starts
3. **Post-generation:** Regex-based forbidden word detection + key business rules (<5ms)

### Tool Execution
- All tool handlers share signature: `async def handler(state: ConversationState) -> dict`
- Tools execute in parallel via `asyncio.gather` with per-tool 3s timeout
- Results cached in Layer 3 `tool_cache` with TTL (default 300s)
- Chain C only permits read-only tools; write operations require Skill declaration

## Data Assets

- `test.jsonl` — 98 real conversation records for offline evaluation
- `raw_data.csv` — ~3000 records for L1 classifier training (columns include `完整对话_原始`, `完整对话_清洗后`, domain labels)
- `sop/clean/03_chunks/all_chunks.json` — 874 SOP chunks with embeddings (reused for Chain C RAG)
- `sop/clean/04_embedded/milvus_weixin.db` — Pre-built Milvus Lite vector index

## Development Guidelines

### When implementing, follow `codegen_prompts.md` task order
Phase 1 tasks are sequential with explicit dependencies. Each task specifies input/output contracts.

### Business domains (10 total)
会员(Member), 额度(Quota), 还款(Repayment), 贷款(Loan), 费用(Fee), 活动(Promotion), 业务办理(Business Service), 账户(Account), 逾期(Overdue), 优享卡(Premium Card)

### LLM prompt token budget
7B model works best within 4K-8K context. Budget: system instructions ~300 + skill candidates ~800-1500 + sliding window ~600-1200 + summary ~150-300 + structured state ~100-200 + tool results ~200-400 + output ~500 = ~2650-4400 tokens total. Trim priority: reduce skill candidates → shrink window → compress summary.

### Chain C safety constraints
- Only read-only tool calls allowed
- No specific amount/rate/reduction commitments
- Must use "建议您..." not "我可以帮你操作"
- Mandatory suffix: "以上信息仅供参考，具体以业务确认为准"
- Output must carry ⚠️ 无SOP覆盖 warning

### Skill YAML editing
Skills are declarative config — no runtime logic. Operational staff can edit them. Changes to `skills/definitions/` and `skills/references/` should not require code changes. Skill files are loaded at startup and indexed via `skills/registry.json`.

### `sop/` is read-only reference data
Never modify files under `sop/`. This is the source-of-truth SOP knowledge that was processed into the current chunk/embedding pipeline.
