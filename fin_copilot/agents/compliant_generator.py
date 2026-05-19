"""Agent A: Compliant generator — Jinja2 direct fill or LLM generation."""

from __future__ import annotations

import json
import logging
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

        # Try Jinja2 direct fill
        filled, is_complete = try_fill_template(script, data)

        if is_complete and not supplemental_context and not branch_hints and not data.get("_tools_failed"):
            # Zero LLM — all slots filled, no branch hints to consider
            return {"answer": filled.strip(), "next_step_hint": next_step}

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

        # Format tool results for prompt
        tool_text = json.dumps(tool_results, ensure_ascii=False, indent=2) if tool_results else "(无工具结果)"

        # Format collected slots
        slots_text = json.dumps(state.slots, ensure_ascii=False) if state.slots else "(无)"

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
        return self._parse_response(raw, skill)

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
