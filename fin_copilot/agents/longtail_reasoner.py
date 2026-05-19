"""Chain C: Long-tail reasoner — tool-assisted LLM reasoning for uncovered scenarios."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fin_copilot.llm.client import LLMClient
from fin_copilot.models.conversation import ConversationState

logger = logging.getLogger(__name__)

# Tools that are safe to call in Chain C (read-only)
_READ_ONLY_TOOLS = [
    "get_customer_profile",
    "get_bill_and_repayment_plan",
    "get_loan_service_info",
    "get_membership_service_info",
    "get_quota_service_info",
    "get_call_history",
    "get_sms_history",
    "get_stop_collection_history",
    "get_refund_history",
    "query_ticket",
]

# Keywords that suggest which tools to call
_TOOL_HINTS: dict[str, list[str]] = {
    "get_customer_profile": ["账户", "客户", "信息", "资料", "个人"],
    "get_bill_and_repayment_plan": ["账单", "还款", "欠款", "逾期", "扣款", "费用"],
    "get_loan_service_info": ["贷款", "借款", "放款", "合同", "借了"],
    "get_membership_service_info": ["会员", "VIP", "权益"],
    "get_quota_service_info": ["额度", "提额", "可以借多少"],
    "get_call_history": ["进线", "来电", "电话记录", "刚才谁给我打电话", "谁给我打电话"],
    "get_sms_history": ["短信", "信息", "通知", "验证码"],
    "get_stop_collection_history": ["停催", "停止催收", "别打电话"],
    "get_refund_history": ["退费", "退款", "退钱", "到账"],
    "query_ticket": ["工单", "进度", "之前的问题", "上次"],
}


class LongtailReasoner:
    """Chain C: Tool-assisted LLM reasoning for scenarios not covered by Skills.

    Flow:
      1. Infer which read-only tools to call based on query keywords
      2. Execute tools to get real data
      3. Call LLM with tool results + RAG reference (if available)
      4. Apply strict compliance: read-only, no commitments, mandatory disclaimer
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        prompt_path: Optional[str] = None,
    ) -> None:
        self._llm = llm_client
        self._system_prompt = ""
        if prompt_path:
            self._system_prompt = self._load_prompt(prompt_path)

    async def reason(
        self,
        query: str,
        state: Optional[ConversationState] = None,
        tool_results: Optional[dict[str, Any]] = None,
        sliding_window_text: str = "",
        summary: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a cautious, tool-assisted response for uncovered scenarios."""

        # Determine which tools to suggest
        suggested_tools = self._suggest_tools(query)

        # If we have tool results, try LLM reasoning
        if self._llm and tool_results:
            answer = await self._llm_reason(
                query, state, tool_results, suggested_tools,
                sliding_window_text, summary,
            )
            if answer:
                return answer

        # If LLM available but no tool results, still try basic reasoning
        if self._llm and state:
            answer = await self._llm_reason(
                query, state, tool_results or {}, suggested_tools,
                sliding_window_text, summary,
            )
            if answer:
                return answer

        # Fallback: safe response
        return self._safe_fallback(query, suggested_tools)

    def _suggest_tools(self, query: str) -> list[str]:
        """Infer which tools might be relevant based on query keywords."""
        tools: list[str] = []
        for tool_name, hints in _TOOL_HINTS.items():
            if any(h in query for h in hints):
                tools.append(tool_name)
        # Always include customer profile if any tool is needed
        if tools and "get_customer_profile" not in tools:
            tools.insert(0, "get_customer_profile")
        return tools

    async def _llm_reason(
        self,
        query: str,
        state: Optional[ConversationState],
        tool_results: dict[str, Any],
        suggested_tools: list[str],
        sliding_window_text: str,
        summary: str,
    ) -> dict[str, Any] | None:
        """Use LLM to generate a cautious response with tool data."""
        # Build context
        customer_info = ""
        slots_info = ""
        if state:
            if state.customer.verified:
                customer_info = f"客户: {state.customer.name_masked} (已核身)"
            slots_info = json.dumps(state.slots, ensure_ascii=False) if state.slots else ""

        tool_text = ""
        if tool_results:
            tool_text = json.dumps(tool_results, ensure_ascii=False, indent=2)

        if self._system_prompt:
            prompt = self._system_prompt
            replacements = {
                "{sliding_window}": sliding_window_text or "(无历史对话)",
                "{summary}": summary or "(无摘要)",
                "{customer_info}": customer_info or "(未知客户)",
                "{collected_slots}": slots_info or "(无)",
                "{tool_results}": tool_text or "(无工具结果)",
                "{rag_top3_chunks}": "(无SOP参考)",
                "{available_tools}": ", ".join(suggested_tools) if suggested_tools else "(无)",
            }
            for placeholder, value in replacements.items():
                prompt = prompt.replace(placeholder, value)
        else:
            # Inline prompt if no template loaded
            prompt = f"""你是金融客服坐席辅助系统。当前客户的问题不在标准场景库覆盖范围内。
请基于以下工具查询结果，为坐席生成合理的推荐话术。

客户信息: {customer_info}
已收集信息: {slots_info}
工具查询结果:
{tool_text or '(无)'}

安全约束（必须严格遵守）:
1. 不得输出具体金额承诺、利率数字、减免方案
2. 禁止说"我可以帮你操作"，只能说"建议您..."
3. 所有回答必须附加"以上信息仅供参考，具体以业务确认为准"
4. 如有工具查询到的真实数据，基于数据回答；缺失数据不得臆造

输出 JSON: {{"answer": "推荐话术", "next_step_hint": "建议下一步"}}"""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]

        raw = await self._llm.chat_completion(messages, temperature=0.3)
        if not raw:
            return None

        return self._parse_response(raw, suggested_tools)

    @staticmethod
    def _parse_response(raw: str, tools_called: list[str]) -> dict[str, Any]:
        """Parse LLM response, ensure mandatory suffix."""
        required_suffix = "以上信息仅供参考，具体以业务确认为准"

        try:
            text = raw.strip()
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]
            data = json.loads(text)
            answer = data.get("answer", raw)
        except json.JSONDecodeError:
            answer = raw.strip()
            data = {}

        # Ensure mandatory disclaimer
        if required_suffix not in answer:
            answer = answer.rstrip() + "\n" + required_suffix

        return {
            "answer": answer,
            "next_step_hint": data.get("next_step_hint", ""),
            "warning": "⚠️ 该回答无SOP覆盖，请坐席核实后使用",
            "rag_references": [],
            "tools_called": tools_called,
        }

    @staticmethod
    def _safe_fallback(query: str, suggested_tools: list[str]) -> dict[str, Any]:
        """Generate a safe fallback when LLM is unavailable."""
        if suggested_tools:
            tool_desc = {
                "get_customer_profile": "客户档案",
                "get_bill_and_repayment_plan": "账单还款信息",
                "get_loan_service_info": "贷款详情",
                "get_membership_service_info": "会员信息",
                "get_quota_service_info": "额度信息",
                "get_call_history": "进线记录",
                "get_sms_history": "短信记录",
                "get_stop_collection_history": "停催记录",
                "get_refund_history": "退费记录",
                "query_ticket": "工单记录",
            }
            info_needed = "、".join(tool_desc.get(t, t) for t in suggested_tools)
            return {
                "answer": (
                    f"关于您的问题，建议您稍候，我为您查询相关信息（{info_needed}）。"
                ),
                "next_step_hint": f"建议调用: {', '.join(suggested_tools)}",
                "warning": "⚠️ 该回答无SOP覆盖，请坐席核实后使用",
                "rag_references": [],
                "tools_called": [],
            }
        return {
            "answer": (
                "您的问题我需要进一步了解，建议您描述更多细节以便我为您查询，"
                "或输入「转人工」联系人工客服。"
            ),
            "next_step_hint": "引导客户提供更多信息",
            "warning": "⚠️ 该回答无SOP覆盖，请坐席核实后使用",
            "rag_references": [],
            "tools_called": [],
        }

    @staticmethod
    def _load_prompt(path: str) -> str:
        content = Path(path).read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()
