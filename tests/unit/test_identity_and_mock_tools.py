"""Tests for mock customer fixtures and identity helper behavior."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.orchestrator import Orchestrator  # noqa: E402
from fin_copilot.config import Settings  # noqa: E402
from fin_copilot.main import build_orchestrator  # noqa: E402
from fin_copilot.models.skill import SkillMatch  # noqa: E402
from tools.executor import execute_tools  # noqa: E402


def test_extract_id_last4_accepts_short_and_full_id():
    assert Orchestrator._extract_id_last4("1234") == "1234"
    assert Orchestrator._extract_id_last4("身份证后四位是1234") == "1234"
    assert Orchestrator._extract_id_last4("身份证号是110101199003151234") == "1234"


def test_one_shot_verification_payload_matches_mock_persona():
    assert (
        Orchestrator._match_verification_payload(
            "我是李四，手机号13900001111，身份证后四位5678"
        )
        == "C101"
    )
    assert (
        Orchestrator._match_verification_payload(
            "我是王五，手机号18600002222，身份证号510101198201019012"
        )
        == "C102"
    )
    assert Orchestrator._match_verification_payload("我是张三，手机号13900001111，后四位1234") is None


def test_new_mock_tools_return_customer_specific_records():
    async def _run():
        result = await execute_tools(
            [
                "get_customer_profile",
                "get_call_history",
                "get_sms_history",
                "get_stop_collection_history",
                "get_refund_history",
            ],
            {"customer": {"customer_id": "C102"}, "slots": {}, "intent": {}},
        )
        return result

    result = asyncio.run(_run())
    assert result["execution_status"] == "success"
    assert result["tool_results"]["get_customer_profile"]["customer_name"] == "王五"
    assert result["tool_results"]["get_call_history"]["total_count"] == 2
    assert result["tool_results"]["get_sms_history"]["total_count"] == 2
    assert result["tool_results"]["get_refund_history"]["refund_history"][0]["refund_id"] == "RF20260402001"


def test_identity_pass_consumes_cached_rule_route_without_rerouting():
    async def _run():
        settings = Settings(
            ENABLE_HYBRID_SKILL_RECALL=False,
            ENABLE_VALUE_ADDED_KNOWLEDGE=False,
        )
        orch, llm = build_orchestrator(settings)
        try:
            session_id = "unit-pending-route"
            first = await orch.handle_turn(session_id, "我要注销账户")
            state = orch.ctx.get_or_create(session_id)
            assert first.output_type == "followup"
            assert state.customer.pending_route["kind"] == "route_a"
            assert state.customer.pending_route["skill_id"] == "account_cancellation"

            second = await orch.handle_turn(
                session_id,
                "我叫张三，手机号13812345678，身份证后四位1234",
            )
            assert second.route == "route_a"
            assert second.matched_skill_id == "account_cancellation"
            assert "身份核实通过" in second.answer
            assert "张三" in second.answer
            assert "注销" in second.answer
            assert state.customer.pending_route == {}
            assert state.customer.pending_query == ""
            assert state.intent.current_skill_id == "account_cancellation"
        finally:
            await llm.close()

    asyncio.run(_run())


def test_thanks_with_punctuation_routes_to_closing():
    async def _run():
        settings = Settings(
            ENABLE_HYBRID_SKILL_RECALL=False,
            ENABLE_VALUE_ADDED_KNOWLEDGE=False,
        )
        orch, llm = build_orchestrator(settings)
        try:
            resp = await orch.handle_turn("unit-thanks-closing", "好的，感谢")
            assert resp.route == "route_a"
            assert "感谢您的来电" in resp.answer
            assert "想咨询账单" not in resp.answer
        finally:
            await llm.close()

    asyncio.run(_run())


def test_identity_pass_consumes_cached_route_b_match_without_rerouting():
    async def _run():
        settings = Settings(
            ENABLE_HYBRID_SKILL_RECALL=False,
            ENABLE_VALUE_ADDED_KNOWLEDGE=False,
        )
        orch, llm = build_orchestrator(settings)
        route_calls = 0

        async def fake_route_chain_b(query, state, window_text, summary):
            nonlocal route_calls
            route_calls += 1
            if route_calls > 1:
                raise AssertionError("route_chain_b should not run after verification")
            return (
                SkillMatch(
                    skill_id="account_cancellation",
                    template_variant="first_contact",
                    confidence=0.91,
                    tools_needed=["get_customer_profile"],
                ),
                "账户",
            )

        orch._route_chain_b = fake_route_chain_b

        async def fake_generate(*args, **kwargs):
            return {
                "answer": "张三，您好，账户注销前建议您再考虑一下。",
                "next_step_hint": "等待客户确认是否继续注销",
            }

        orch.generator.generate = fake_generate

        try:
            session_id = "unit-pending-route-b"
            first = await orch.handle_turn(session_id, "我想关闭我的账号")
            state = orch.ctx.get_or_create(session_id)
            assert first.output_type == "followup"
            assert route_calls == 1
            assert state.customer.pending_route["kind"] == "route_b"
            assert state.customer.pending_route["skill_match"]["skill_id"] == "account_cancellation"

            second = await orch.handle_turn(
                session_id,
                "我叫张三，手机号13812345678，身份证后四位1234",
            )
            assert route_calls == 1
            assert second.route == "route_b"
            assert second.matched_skill_id == "account_cancellation"
            assert "身份核实通过" in second.answer
            assert "张三" in second.answer
            assert state.customer.pending_route == {}
        finally:
            await llm.close()

    asyncio.run(_run())
