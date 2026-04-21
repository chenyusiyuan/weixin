"""Tests for mock customer fixtures and identity helper behavior."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.orchestrator import Orchestrator  # noqa: E402
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
