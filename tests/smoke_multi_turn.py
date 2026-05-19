"""Smoke test for multi-turn dialogue helpers.

Runs offline (no LLM, no FastAPI). Verifies:
  1. Sticky decision fires on short follow-ups.
  2. Sticky drops when topic-switch tokens appear.
  3. Duplicate-reply guard reports >= threshold similarity.
  4. Reference resolver rewrites pronouns when anchor slots exist.
  5. Rolling narrative summary grows and slides.

Usage:
    python tests/smoke_multi_turn.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fin_copilot.config import get_settings
from fin_copilot.context.context_manager import ContextManager
from fin_copilot.models.conversation import ConversationState, CustomerInfo


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def case_sticky_on_followup(ctx: ContextManager) -> None:
    banner("CASE 1: sticky fires on short continuation")
    state = ConversationState(session_id="t1", customer=CustomerInfo())
    state.intent.current_skill_id = "bill_deduction_query"
    state.intent.domain = "费用"
    state.intent.turn_in_skill = 1
    state.slots = {
        "customer_name": "陈*生",
        "bill_period": "7",
        "bill_amount": "1200",
        "due_date": "2026-04-25",
    }
    for q in ["嗯", "那呢", "然后呢", "怎么办"]:
        d = ctx.should_stick(state, q)
        print(f"  query={q!r:10s} -> stick={d.stick} reason={d.reason}")
        assert d.stick, f"expected stick for {q!r}"


def case_sticky_breaks_on_switch(ctx: ContextManager) -> None:
    banner("CASE 2: sticky breaks on topic switch / other-domain / risk")
    state = ConversationState(session_id="t2", customer=CustomerInfo())
    state.intent.current_skill_id = "bill_deduction_query"
    state.intent.domain = "费用"
    state.intent.turn_in_skill = 1

    for q in ["换个问题", "我想问还款", "起诉你们"]:
        # Inject matching risk flag for the "起诉" case to mimic process_turn_start.
        other_kw = ["还款", "贷款", "额度", "会员"]
        ss = state.model_copy(deep=True)
        if "起诉" in q:
            ss.risk_flags.append("legal_threat")
        d = ctx.should_stick(ss, q, other_domain_keywords=other_kw)
        print(f"  query={q!r:12s} -> stick={d.stick} reason={d.reason}")
        assert not d.stick, f"expected drop for {q!r}"


def case_turn_budget(ctx: ContextManager) -> None:
    banner("CASE 3: turn_in_skill >= max_sticky_turns forces break")
    state = ConversationState(session_id="t3", customer=CustomerInfo())
    state.intent.current_skill_id = "bill_deduction_query"
    state.intent.domain = "费用"
    state.intent.turn_in_skill = 3  # == max_sticky_turns
    d = ctx.should_stick(state, "嗯")
    print(f"  turn_in_skill=3, 'query=嗯' -> stick={d.stick} reason={d.reason}")
    assert not d.stick


def case_duplicate_guard(ctx: ContextManager) -> None:
    banner("CASE 4: duplicate-reply guard")
    a = "您当前账单期次：第7期，账单金额：1200元，还款日：2026-04-25。扣款状态：已成功。"
    b = "您当前账单期次：第7期，账单金额：1200元，还款日：2026-04-25。扣款状态：已成功。"
    c = "好的，还有什么可以帮您的？"
    r_same = ctx.duplicate_ratio(a, b)
    r_diff = ctx.duplicate_ratio(a, c)
    print(f"  ratio(identical)={r_same:.3f}")
    print(f"  ratio(different)={r_diff:.3f}")
    assert r_same >= 0.82
    assert r_diff < 0.82


def case_reference_resolution(ctx: ContextManager) -> None:
    banner("CASE 5: reference resolution rewrites pronouns")
    state = ConversationState(session_id="t5", customer=CustomerInfo())
    state.intent.domain = "费用"
    state.slots = {"bill_amount": "1200"}
    for q, expect_change in [
        ("那它多少钱", True),         # short, has anchor -> rewrite
        ("这个怎么还", True),         # short, has anchor -> rewrite
        ("我要投诉你们的服务态度", False),  # long -> untouched
        ("嗯", False),                # no pronoun -> untouched
    ]:
        out = ctx.resolve_references(state, q)
        changed = out != q
        print(f"  {q!r} -> {out!r}  changed={changed}")
        assert changed == expect_change, f"unexpected change state for {q!r}"


def case_narrative_summary(ctx: ContextManager) -> None:
    banner("CASE 6: rolling narrative summary")
    state = ConversationState(session_id="t6", customer=CustomerInfo())

    turns = [
        ("我想查账单", "您好，为您查询账单", "bill_deduction_query", "费用",
         {"customer_request": "查账单"}, ["get_bill_and_repayment_plan"]),
        ("嗯", "您当前账单金额 1200 元，已扣款成功。", "bill_deduction_query", "费用",
         {"bill_amount": "1200"}, []),
        ("那什么时候出下一期", "下一期账单将在每月1号生成。", "bill_deduction_query", "费用",
         {}, []),
        ("我想问还款怎么还", "您好，还款方式有…", "repayment_method", "还款",
         {"customer_request": "还款"}, []),
    ]
    for q, a, sid, dom, slots, tools in turns:
        ctx.process_turn_start(state, q)
        ctx.process_turn_end(
            state, q, a, skill_id=sid, domain=dom,
            new_slots=slots, tools_called=tools, was_sticky=False,
        )
        print(f"  turn#{state.total_turns} narrative={state.narrative_summary!r}")
    sentences = state.narrative_summary.split("；")
    assert 1 <= len(sentences) <= 5, f"narrative should slide to <=5 sentences, got {len(sentences)}"
    print(f"  final event log={state.summary!r}")


def case_end_to_end_sticky(ctx: ContextManager) -> None:
    """Run the orchestrator on a 3-turn dialog and assert sticky short-circuits
    second turn without touching the LLM. Uses pre-seeded state + cached tool
    results so route_a_sticky can Jinja2-fill directly.
    """
    banner("CASE 7: end-to-end orchestrator sticky shortcut")
    import asyncio

    from fin_copilot.main import build_orchestrator
    from fin_copilot.config import get_settings
    from fin_copilot.models.conversation import ToolCacheEntry

    async def run():
        settings = get_settings()
        orch, llm = build_orchestrator(settings)
        try:
            sid = "sticky-e2e"
            state = orch.ctx.get_or_create(sid)
            # Seed: user already verified + skill set + slots ready
            state.customer.verified = True
            state.customer.verification_level = "full"
            state.customer.verification_step = "passed"
            state.customer.name_masked = "陈*生"
            state.intent.current_skill_id = "bill_deduction_query"
            state.intent.domain = "费用"
            state.intent.turn_in_skill = 1
            state.total_turns = 1
            state.slots = {
                "customer_name": "陈*生",
                "bill_period": "7",
                "bill_amount": "1200",
                "due_date": "2026-04-25",
                "deduction_status": "已扣款成功",
                "deduction_detail": "于2026-04-25完成扣款。",
            }
            state.tool_cache["get_bill_and_repayment_plan"] = ToolCacheEntry(
                data=dict(state.slots), ts=0.0,
            )
            state.last_agent_reply = "此前已为您展示账单信息。"

            # Turn A — short acknowledgement should hit sticky shortcut (no LLM)
            resp1 = await orch.handle_turn(sid, "嗯")
            print(f"  turn A 'query=嗯' -> route={resp1.route} skill={resp1.matched_skill_id} "
                  f"latency={resp1.latency_ms:.1f}ms")
            assert resp1.route == "route_a_sticky", f"expected sticky, got {resp1.route}"

            # Turn B — same ack again (no slot progress) -> closing probe, not duplicate
            resp2 = await orch.handle_turn(sid, "嗯")
            print(f"  turn B 'query=嗯' -> route={resp2.route} answer_head={resp2.answer[:30]!r}")
            assert resp2.route == "route_a_sticky"
            # must NOT be identical to last reply
            ratio = orch.ctx.duplicate_ratio(resp2.answer, resp1.answer)
            print(f"  duplicate ratio vs turn A = {ratio:.3f}")
            assert ratio < 0.82, "sticky should have fallen back to closing probe"

            # Turn C — explicit topic switch -> sticky must release
            resp3 = await orch.handle_turn(sid, "换个问题，我想问还款")
            print(f"  turn C topic-switch -> route={resp3.route}")
            assert resp3.route != "route_a_sticky", "topic switch should break sticky"
        finally:
            await llm.close()

    asyncio.run(run())


def main() -> None:
    settings = get_settings()
    ctx = ContextManager(settings)
    case_sticky_on_followup(ctx)
    case_sticky_breaks_on_switch(ctx)
    case_turn_budget(ctx)
    case_duplicate_guard(ctx)
    case_reference_resolution(ctx)
    case_narrative_summary(ctx)
    case_end_to_end_sticky(ctx)
    print("\n" + "=" * 70)
    print("ALL SMOKE CASES PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
