"""Tests for Chain C deterministic tool fallback."""

from __future__ import annotations

import asyncio

from fin_copilot.agents.longtail_reasoner import LongtailReasoner


def test_longtail_uses_tool_data_when_llm_returns_empty():
    class _EmptyLLM:
        async def chat_completion(self, *args, **kwargs):
            return ""

    reasoner = LongtailReasoner(llm_client=_EmptyLLM())
    result = asyncio.run(
        reasoner.reason(
            "我的贷款逾期多长时间了",
            tool_results={
                "get_customer_profile": {"customer_name": "张三"},
                "get_bill_and_repayment_plan": {
                    "overdue_days": 45,
                    "overdue_amount": 8500.0,
                },
            },
        )
    )

    assert "45 天" in result["answer"]
    assert "8500 元" in result["answer"]
    assert "以上信息仅供参考，具体以业务确认为准" in result["answer"]
