# Skill Schema Reference (post-migration)

Authoritative spec for `skills/definitions/*.yaml`. Enforced by
`scripts/validate_skills.py` and `tests/test_skill_schema.py`.

## Top-level fields

| field                | type           | required | notes                                                                 |
|----------------------|----------------|----------|-----------------------------------------------------------------------|
| `skill_id`           | string         | ✔        | must equal filename stem                                              |
| `name`               | string         | ✔        |                                                                       |
| `description`        | string         |          |                                                                       |
| `domain`             | string         | ✔        | must match `skills/registry.json` entry                               |
| `intent_hierarchy`   | map            |          | `l1`/`l2`/`l3` free-form                                              |
| `route_mode`         | enum           | ✔        | `direct_reply` / `tool_only` / `tool_rag`                             |
| `risk_level`         | enum           | ✔        | `low` / `medium` / `high`                                             |
| `priority`           | int            |          | higher wins when L1 returns overlapping skills (default 0)            |
| `triggers`           | map            | ✔        | `keywords`, `examples`, `exclude_keywords`                            |
| `tools`              | map            | ✔        | `{required: [...], optional: [...]}`                                  |
| `templates`          | map            | ✔        | variant → `{script, required_slots, next_step}`                       |
| `branch_conditions`  | list           |          | see §Branch Conditions DSL                                            |
| `compliance`         | map            | ✔        | `forbidden_expressions`, `required_disclaimer`, `must_include_when`   |
| `escalation`         | list of `{trigger}` |     | natural-language escalation triggers                                   |
| `escalation_signals` | list of string |          | Chain A pre-match keywords (e.g. 律师/消协/上级) — force tier2 routing |
| `fallback`           | map            | ✔        | `{answer, next_step}` — safe default answer                           |
| `slot_sources`       | map            | ✔        | see §Slot Sources                                                     |

---

## Branch Conditions DSL

Each entry under `branch_conditions` now uses **`expr`** and/or **`hint`**:

```yaml
branch_conditions:
  - expr: overdue_days > 30 and overdue_days <= 90
    variant: mid_overdue
    note: 逾期31-90天，可申请二次分期

  - hint: 客户坚持只和贷后人员谈，客服协商无果
    variant: escalate_to_collector
    note: 提交工单升级

  - expr: has_membership is True
    hint: 客户还持有会员，可以用权益抵扣
    variant: membership_offset
    note: 评估会员抵扣
```

- **`expr`** (optional) — Python-evaluable boolean over Layer 3 state slots. Must use only:
  - comparison operators (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `is`)
  - logical ops (`and`, `or`, `not`)
  - parentheses and literal constants
  - identifiers resolved against `ConversationState.slots` at runtime
  - **No function calls, attribute access, or subscripts.** Validator rejects these.
- **`hint`** (optional) — natural-language condition for the LLM to interpret. Used when the condition cannot be reduced to a boolean over slots (e.g. "挽留成功").
- **At least one of `expr` or `hint` must be present.** Both may coexist: `expr` gates deterministic branches; `hint` augments it with natural-language context for Agent A's prompt.
- Legacy `condition:` field is **rejected** — run `scripts/migrate_skills.py --apply` to migrate.

Evaluation order in the orchestrator:
1. Evaluate all `expr` in declaration order against current slots; first truthy wins → fixed variant.
2. If no `expr` matches, pass all remaining `hint` entries (with their `variant` label) into Agent A's prompt and let the LLM choose.

---

## Slot Sources

`slot_sources` is a flat map from every placeholder in `templates.*.script`
(and `fallback.answer`) to its origin.

```yaml
slot_sources:
  customer_name:       tool:get_customer_profile.name
  overdue_amount:      tool:get_bill_and_repayment_plan.overdue_amount
  overdue_days:        tool:get_bill_and_repayment_plan.overdue_days
  agent_name:          system:agent_name
  verify_question:     system:verify_question
  verify_answer:       user_input:verify_answer
  resolution_proposal: llm:resolution_proposal
  verification_info:   derived:verification_info
```

Valid source prefixes:

| prefix        | meaning                                                          | filled by                                      |
|---------------|------------------------------------------------------------------|------------------------------------------------|
| `tool:X.Y`    | field `Y` of tool `X`'s result                                   | `ToolExecutor` after parallel tool calls       |
| `system:X`    | system-configured (agent profile, service window)                | `config` or session handshake                  |
| `user_input:X`| taken from the live customer utterance                           | `ContextManager` slot extractor                |
| `llm:X`       | synthesised by Agent A during generation                         | LLM call itself                                |
| `derived:X`   | computed from other slots (e.g. formatted verification)          | custom resolver registered in the orchestrator |

The validator checks:
1. Every placeholder `{x}` in a script has a `slot_sources[x]` entry.
2. Every `tool:` source references a tool listed in the skill's `tools.required` or `tools.optional`.
3. The prefix is one of the five above.

---

## Escalation signals & priority

- `escalation_signals` (keywords) — Chain A pre-matches the customer utterance against this list. A hit on any entry **bypasses** the L1 classifier and routes directly to the corresponding tier2 / complaint skill. Keep the list short and specific (律师 / 消协 / 投诉到底 / 内诉 / 找上级 …) — do not include generic words that already appear in `triggers.keywords`.
- `priority` (integer) — resolves ambiguity when two skills look equally applicable. Convention:
  - `30` — hard scenario lock (e.g. `special_account_cancellation`)
  - `20` — tier2 / escalation variant (e.g. `fee_refund_tier2`, `deactivated_customer_service`)
  - `10` — tier1 / default variant
  - `0` — normal skills (default)

---

## Migration tooling

- `scripts/validate_skills.py` — report schema conformance (`--strict` for CI, `--json` for tooling).
- `scripts/migrate_skills.py` — one-shot migration: `required_slots` backfill, `condition` → `expr`/`hint`, stub `slot_sources` + `escalation_signals`. Safe to re-run.
- `scripts/sync_tools_from_slot_sources.py` — adds missing tools to `tools.optional` based on `slot_sources` references.
- `scripts/seed_escalation_signals.py` — seeds `escalation_signals` + `priority` on tier2 / overlapping skills.
- `tests/test_skill_schema.py` — pytest runner that fails on any validator error or warning.
