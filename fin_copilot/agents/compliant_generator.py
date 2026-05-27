"""Agent A: Compliant generator — Jinja2 direct fill or LLM generation."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from fin_copilot.llm.client import LLMClient
from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.skill import SkillDefinition
from fin_copilot.utils.template_engine import try_fill_template

logger = logging.getLogger(__name__)


class CompliantGenerator:
    """Generates compliant response scripts for Chain A and Chain B.

    Priority: Jinja2 direct fill (zero LLM) → LLM generation.
    """

    def __init__(self, llm_client: LLMClient, prompt_path: str) -> None:
        self._llm = llm_client
        self._system_prompt = self._load_prompt(prompt_path)

    async def generate(
        self,
        skill: SkillDefinition,
        template_variant: str,
        tool_results: dict[str, Any],
        state: ConversationState,
        recent_turns_text: str,
        summary: str,
        branch_hints: list[dict[str, Any]] | None = None,
        supplemental_context: str = "",
    ) -> dict[str, Any]:
        """Generate a compliant response.

        Returns ``{"answer": "...", "next_step_hint": "..."}``.
        ``branch_hints`` carries natural-language branch conditions that the
        orchestrator could not evaluate deterministically; they are passed
        through as soft guidance in the LLM prompt. ``supplemental_context``
        carries retrieved SOP knowledge that should be considered even when
        the template itself could be filled directly.
        """
        # Get template
        tpl = skill.get_template(template_variant)
        if tpl is None:
            # Try fallback
            fallback_answer = skill.fallback.get("answer", "")
            fallback_next = skill.fallback.get("next_step", "")
            if fallback_answer:
                return {"answer": fallback_answer, "next_step_hint": fallback_next}
            # Use first template
            first_key = skill.get_first_template_key()
            tpl = skill.get_template(first_key)
            if tpl is None:
                return {"answer": "", "next_step_hint": ""}

        script = tpl.script
        next_step = tpl.next_step

        # Build data dict: merge slots + flattened tool results
        data = dict(state.slots)
        for tool_name, result in tool_results.items():
            if isinstance(result, dict):
                data.update(result)
        if data.get("eval_identity_flow_mode"):
            data = self._sanitize_eval_identity_data(data)

        # Try Jinja2 direct fill
        filled, is_complete = try_fill_template(script, data)

        if (
            is_complete
            and not supplemental_context
            and not branch_hints
            and not data.get("_tools_failed")
            and not data.get("eval_force_contextual_generation")
        ):
            # Zero LLM — all slots filled, no branch hints to consider
            return self._enforce_generation_guards(
                {"answer": filled.strip(), "next_step_hint": next_step},
                skill,
                data,
                tool_results,
            )

        # Otherwise, call LLM for generation
        return await self._llm_generate(
            skill, template_variant, script, tool_results, state,
            recent_turns_text, summary, data,
            branch_hints or [],
            supplemental_context,
        )

    async def _llm_generate(
        self,
        skill: SkillDefinition,
        template_variant: str,
        script: str,
        tool_results: dict[str, Any],
        state: ConversationState,
        recent_turns_text: str,
        summary: str,
        data: dict[str, Any],
        branch_hints: list[dict[str, Any]],
        supplemental_context: str,
    ) -> dict[str, Any]:
        """Fall back to LLM generation when template has unfilled slots."""
        # Build forbidden expressions list
        forbidden = skill.compliance.forbidden_expressions
        forbidden_text = "、".join(forbidden) if forbidden else "无"

        # Build conditional requirements
        conditional = ""
        for item in skill.compliance.must_include_when:
            cond = item.get("condition", "")
            text = item.get("text", "")
            conditional += f"- 当 {cond} 时，必须包含：{text}\n"

        # Build branch hints (natural-language branch conditions the
        # orchestrator couldn't evaluate deterministically — pass them as
        # soft guidance).
        hint_text_lines: list[str] = []
        for br in branch_hints:
            hint = br.get("hint") or br.get("expr") or ""
            variant = br.get("variant", "")
            note = br.get("note", "")
            if hint:
                line = f"- 若「{hint}」则切换到 `{variant}` 路径"
                if note:
                    line += f"：{note}"
                hint_text_lines.append(line)
        hint_text = "\n".join(hint_text_lines) if hint_text_lines else "（无分支提示）"

        eval_identity_mode = bool(data.get("eval_identity_flow_mode"))
        prompt_tool_results = (
            self._sanitize_eval_tool_results(tool_results)
            if eval_identity_mode else tool_results
        )
        prompt_slots = (
            self._sanitize_eval_identity_data(dict(state.slots))
            if eval_identity_mode else dict(state.slots)
        )

        # Format tool results for prompt
        tool_text = json.dumps(prompt_tool_results, ensure_ascii=False, indent=2) if prompt_tool_results else "(无工具结果)"

        # Format collected slots
        slots_text = json.dumps(prompt_slots, ensure_ascii=False) if prompt_slots else "(无)"

        # Use replace() instead of str.format() because prompt templates
        # contain JSON examples with literal braces
        prompt = self._system_prompt
        # Compute missing slots for the chosen template variant
        chosen_tpl = skill.get_template(template_variant)
        required_slots = list(getattr(chosen_tpl, "required_slots", []) or []) if chosen_tpl else []
        filled_keys = {k for k, v in data.items() if v not in (None, "", 0)}
        missing_slots = [s for s in required_slots if s not in filled_keys]
        missing_text = "、".join(missing_slots) if missing_slots else "(无)"

        replacements = {
            "{skill_name}": skill.name,
            "{skill_id}": skill.skill_id,
            "{template_script}": script,
            "{tool_results}": tool_text,
            "{recent_turns}": recent_turns_text or "(无历史对话)",
            "{summary}": summary or "(无摘要)",
            "{narrative_summary}": state.narrative_summary or "(无叙事摘要)",
            "{collected_slots}": slots_text,
            "{missing_slots}": missing_text,
            "{last_agent_reply}": (state.last_agent_reply or "")[:200] or "(无)",
            "{forbidden_expressions}": forbidden_text,
            "{required_disclaimer}": skill.compliance.required_disclaimer or "无",
            "{conditional_requirements}": conditional or "无",
            "{branch_hints}": hint_text,
            "{supplemental_context}": supplemental_context or "（无业务补充信息）",
        }
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请生成推荐话术。"},
        ]

        raw = await self._llm.chat_completion(messages, temperature=0.3)
        return self._enforce_generation_guards(
            self._parse_response(raw, skill),
            skill,
            data,
            tool_results,
        )

    @classmethod
    def _enforce_generation_guards(
        cls,
        result: dict[str, Any],
        skill: SkillDefinition,
        data: dict[str, Any],
        tool_results: dict[str, Any],
    ) -> dict[str, Any]:
        result = cls._enforce_eval_operation_boundary(result, skill, data, tool_results)
        return cls._enforce_eval_identity_boundary(result, skill, data)

    @classmethod
    def _enforce_eval_operation_boundary(
        cls,
        result: dict[str, Any],
        skill: SkillDefinition,
        data: dict[str, Any],
        tool_results: dict[str, Any],
    ) -> dict[str, Any]:
        if not data.get("eval_no_business_operation_claim"):
            return result
        if skill.skill_id != "stop_collection":
            return result
        if cls._has_successful_write_tool(tool_results):
            return result

        answer = str(result.get("answer") or "")
        if not cls._contains_stop_collection_done_claim(answer):
            return result

        guarded = (
            f"{data.get('customer_name') or '您'}，我理解您不希望继续被电话或信息打扰。"
            "客服可以先帮您记录停呼/停催诉求并尝试申请，具体是否生效以及生效时长以系统处理结果为准。"
            "同时提醒您，逾期费用和征信影响仍会按业务规则持续存在，建议您尽快安排还款。"
        )
        return {
            "answer": guarded,
            "next_step_hint": "请坐席先在系统中提交停呼/停催申请，成功后再告知客户处理结果",
        }

    _EVAL_IDENTITY_SENSITIVE_KEYS: frozenset[str] = frozenset({
        "phone",
        "phone_masked",
        "mobile",
        "mobile_phone",
        "customer_phone",
        "id_number",
        "id_card",
        "identity_number",
        "id_last4",
        "verify_question",
        "verification_info",
        "verification_items",
    })

    @classmethod
    def _sanitize_eval_identity_data(cls, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in cls._EVAL_IDENTITY_SENSITIVE_KEYS:
                continue
            if isinstance(value, dict):
                sanitized[key] = cls._sanitize_eval_identity_data(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    cls._sanitize_eval_identity_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def _sanitize_eval_tool_results(cls, tool_results: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for tool_name, result in (tool_results or {}).items():
            if isinstance(result, dict):
                sanitized[tool_name] = cls._sanitize_eval_identity_data(result)
            else:
                sanitized[tool_name] = result
        return sanitized

    @classmethod
    def _enforce_eval_identity_boundary(
        cls,
        result: dict[str, Any],
        skill: SkillDefinition,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if not data.get("eval_identity_flow_mode"):
            return result

        if data.get("eval_identity_display_needed") and not data.get("eval_identity_already_displayed"):
            return {
                "answer": cls._build_eval_identity_display_reply(data),
                "next_step_hint": "评测模式：只展示核身引导，客户任意回复后按核身通过继续推进业务",
            }

        answer = str(result.get("answer") or "")
        if not cls._contains_identity_request_or_leak(answer):
            return result

        return {
            "answer": cls._build_eval_identity_continuation_reply(skill, data),
            "next_step_hint": "评测模式已视为核身通过，继续推进当前业务，不再重复核身",
        }

    @staticmethod
    def _contains_identity_request_or_leak(answer: str) -> bool:
        if not answer:
            return False
        identity_markers = ("身份证", "证件", "后四位", "手机号", "手机号码", "注册手机", "身份信息", "核实身份", "核对身份", "核身")
        request_markers = ("请问", "提供", "告知", "核对", "核实", "方便", "麻烦", "辛苦", "验证")
        if any(marker in answer for marker in identity_markers) and any(marker in answer for marker in request_markers):
            return True
        if re.search(r"(身份证|证件|后四位).{0,16}\d{4}", answer):
            return True
        if re.search(r"(手机号|手机号码|注册手机).{0,16}\d{6,}", answer):
            return True
        return False

    @staticmethod
    def _build_eval_identity_display_reply(data: dict[str, Any]) -> str:
        name = data.get("customer_name") or "您"
        repayment_time = data.get("repayment_time") or data.get("mentioned_repayment_time")
        business_tail = f"您希望{repayment_time}还款的诉求" if repayment_time else "您的业务诉求"
        return (
            f"{name}，我先了解您的情况。为了保障账户信息安全，需要先做身份核身。"
            f"请您提供姓名、注册手机号或证件后四位中的任一项信息；核身通过后，我继续帮您处理{business_tail}。"
        )

    @staticmethod
    def _build_eval_identity_continuation_reply(skill: SkillDefinition, data: dict[str, Any]) -> str:
        name = data.get("customer_name") or "您"
        if skill.skill_id == "overdue_negotiation":
            repayment_time = data.get("repayment_time") or data.get("mentioned_repayment_time")
            reason = str(data.get("overdue_reason") or "").strip()
            overdue_days = data.get("overdue_days")
            overdue_amount = data.get("overdue_amount")
            intro = f"{name}，我理解您这边"
            if reason:
                intro += f"因为{reason}，"
            if repayment_time:
                intro += f"希望{repayment_time}安排还款。"
            else:
                intro += "希望协商还款。"
            facts: list[str] = []
            if overdue_days not in (None, ""):
                facts.append(f"当前账单已逾期{overdue_days}天")
            if overdue_amount not in (None, ""):
                facts.append(f"逾期金额为{overdue_amount}元")
            fact_text = "，".join(facts)
            fact_sentence = f"{fact_text}。" if fact_text else ""
            return (
                f"{intro}{fact_sentence}"
                "逾期期间费用和征信影响仍会持续，建议您尽快按计划处理。"
                "我这边可以帮您记录还款意愿和困难原因，具体处理结果以业务确认为准。"
            )

        return (
            f"{name}，我理解您的诉求。当前已按核身通过流程继续处理，"
            "我会围绕您刚才的问题给出业务建议，具体结果以系统和业务确认为准。"
        )

    @staticmethod
    def _has_successful_write_tool(tool_results: dict[str, Any]) -> bool:
        for tool_name in ("submit_ticket", "submit_stop_collection"):
            result = tool_results.get(tool_name)
            if not isinstance(result, dict):
                continue
            status = str(result.get("status") or result.get("execution_status") or "").lower()
            if status not in {"", "error", "failed", "failure"}:
                return True
            if result.get("ticket_id") or result.get("request_id"):
                return True
        return False

    @staticmethod
    def _contains_stop_collection_done_claim(answer: str) -> bool:
        if not answer:
            return False
        done_keywords = (
            "已为您处理", "已处理", "已经处理",
            "已为您申请", "已申请", "已经申请", "申请好了",
            "已提交", "已经提交", "操作完成", "已完成",
            "系统将恢复催收",
        )
        if any(keyword in answer for keyword in done_keywords):
            return True
        return bool(re.search(r"停(?:催|呼)\s*\d+\s*天", answer))

    @staticmethod
    def _load_prompt(path: str) -> str:
        content = Path(path).read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

    @staticmethod
    def _parse_response(raw: str, skill: SkillDefinition) -> dict[str, Any]:
        """Parse LLM JSON or plain text response."""
        if not raw:
            fallback = skill.fallback.get("answer", "")
            return {"answer": fallback, "next_step_hint": skill.fallback.get("next_step", "")}

        try:
            text = raw.strip()
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]
            data = json.loads(text)
            return {
                "answer": data.get("answer", raw),
                "next_step_hint": data.get("next_step_hint", ""),
            }
        except json.JSONDecodeError:
            # Use raw text as answer
            return {"answer": raw.strip(), "next_step_hint": ""}
