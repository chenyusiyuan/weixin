"""Chain B: LLM Skill Router — matches query to the best skill candidate."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from fin_copilot.llm.client import LLMClient
from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.skill import SkillMatch
from fin_copilot.routing.fewshot_retriever import FewShotRetriever
from fin_copilot.skills.loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillRouter:
    """LLM-based skill routing for Chain B."""

    def __init__(
        self,
        llm_client: LLMClient,
        skill_loader: SkillLoader,
        prompt_path: str,
        fewshot_retriever: FewShotRetriever | None = None,
        fewshot_k: int = 5,
    ) -> None:
        self._llm = llm_client
        self._loader = skill_loader
        self._system_prompt = self._load_prompt(prompt_path)
        self._fewshot = fewshot_retriever
        self._fewshot_k = fewshot_k
        boundary_path = Path(prompt_path).parent / "boundary_rules.yaml"
        self._boundary_clusters = self._load_boundary_rules(boundary_path)

    async def route(
        self,
        query: str,
        domain: str,
        state: ConversationState,
        sliding_window_text: str,
        summary: str,
    ) -> SkillMatch:
        """Route a query to the best matching skill via LLM (single-domain)."""
        candidates = self._loader.get_skills_by_domain(domain)
        return await self.route_over_candidates(
            query, candidates, state, sliding_window_text, summary,
        )

    async def route_multi_domain(
        self,
        query: str,
        domains: list[str],
        state: ConversationState,
        sliding_window_text: str,
        summary: str,
    ) -> SkillMatch:
        """Route using candidates from multiple domains (deduplicated)."""
        seen: set[str] = set()
        candidates = []
        for d in domains:
            for c in self._loader.get_skills_by_domain(d):
                if c.skill_id not in seen:
                    seen.add(c.skill_id)
                    candidates.append(c)
        return await self.route_over_candidates(
            query, candidates, state, sliding_window_text, summary,
        )

    async def route_over_candidates(
        self,
        query: str,
        candidates: list,
        state: ConversationState,
        sliding_window_text: str,
        summary: str,
    ) -> SkillMatch:
        """Route with an externally-supplied candidate list."""
        if not candidates:
            return SkillMatch(skill_id="none", confidence=0.0, reasoning="no candidates provided")

        candidates = self._apply_deterministic_filters(query, candidates)
        if not candidates:
            return SkillMatch(skill_id="none", confidence=0.0, reasoning="all candidates filtered")

        candidate_ids = {c.skill_id for c in candidates}

        # Format candidates for prompt
        candidates_text = self._format_candidates(candidates)

        # Few-shot retrieval: pull Top-K real-business examples restricted to
        # the current candidate set. Falls back to empty block when no corpus.
        fewshot_text = "（无参考案例）"
        if self._fewshot is not None and self._fewshot_k > 0:
            try:
                hits = self._fewshot.retrieve(
                    query, k=self._fewshot_k, allowed_skills=candidate_ids,
                )
                if hits:
                    lines = []
                    for h in hits:
                        lines.append(
                            f"- 客户说「{h['query'][:80]}」→ 判为 `{h['skill_id']}` "
                            f"(相似度 {h['similarity']:.2f})"
                        )
                    fewshot_text = "\n".join(lines)
            except Exception as exc:
                logger.warning("fewshot retrieval failed: %s", exc)

        # Build the prompt — use replace() instead of str.format()
        # because prompt templates contain JSON examples with literal braces
        prompt = self._system_prompt
        replacements = {
            "{candidate_skills}": candidates_text,
            "{sliding_window}": sliding_window_text or "(无历史对话)",
            "{summary}": summary or "(无摘要)",
            "{current_skill_id}": state.intent.current_skill_id or "无",
            "{turn_in_skill}": str(state.intent.turn_in_skill),
            "{collected_slots}": json.dumps(state.slots, ensure_ascii=False) if state.slots else "(无)",
            "{risk_flags}": ", ".join(state.risk_flags) if state.risk_flags else "无",
            "{fewshot_examples}": fewshot_text,
            "{boundary_hints}": self._build_boundary_hints(candidate_ids),
        }
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, value)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]

        raw = await self._llm.chat_completion(
            messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        return self._parse_response(raw, candidate_ids)

    @staticmethod
    def _apply_deterministic_filters(query: str, candidates: list) -> list:
        """Apply lightweight guardrails before handing off to the LLM.

        This prevents obvious semantic collisions like treating an延期/缓还诉求
        as提前清贷 merely because both belong to repayment-related domains.
        """
        defer_repayment_markers = (
            "延期", "延期还款", "过段时间再还", "晚点还", "缓几天还",
            "延后还款", "还不上", "协商还款",
        )
        if any(marker in query for marker in defer_repayment_markers):
            filtered = []
            for candidate in candidates:
                exclude_keywords = tuple(candidate.triggers.exclude_keywords or [])
                if any(marker in exclude_keywords for marker in defer_repayment_markers):
                    continue
                filtered.append(candidate)
            if filtered:
                return filtered
        return candidates

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_prompt(path: str) -> str:
        """Load prompt template, stripping YAML front-matter."""
        content = Path(path).read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return content.strip()

    @staticmethod
    def _load_boundary_rules(path: Path) -> list[dict]:
        """Load boundary cluster rules. Returns [] if file missing."""
        if not path.exists():
            return []
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data.get("clusters", []) if isinstance(data, dict) else []
        except (yaml.YAMLError, OSError) as exc:
            logger.warning("failed to load boundary rules: %s", exc)
            return []

    def _build_boundary_hints(self, candidate_ids: set[str]) -> str:
        """Assemble cluster judgement rules only for clusters whose skills
        appear (at least 2) in the current candidate set. Prevents LLM from
        hallucinating skill_ids mentioned in rules but absent from candidates.
        """
        if not self._boundary_clusters:
            return ""
        blocks: list[str] = []
        for cluster in self._boundary_clusters:
            skills_map = cluster.get("skills", {}) or {}
            present = {sid: desc for sid, desc in skills_map.items() if sid in candidate_ids}
            if len(present) < 2:
                continue  # cluster not engaged, skip
            lines = [f"### {cluster.get('name', '判别簇')}"]
            for sid, desc in present.items():
                lines.append(f"- `{sid}` — {desc}")
            tie = cluster.get("tie_breaker")
            if tie:
                lines.append(f"**判别顺序**：{tie}")
            blocks.append("\n".join(lines))
        if not blocks:
            return ""
        header = (
            "## 高频混淆簇判别规则\n\n"
            "以下规则仅适用于当前候选，请严格从候选场景列表中选 skill_id。\n"
        )
        return header + "\n\n".join(blocks)

    @staticmethod
    def _format_candidates(candidates: list) -> str:
        """Format skill candidates as compact text for the LLM prompt."""
        lines: list[str] = []
        for c in candidates:
            examples = c.triggers.examples[:3]
            examples_str = "；".join(examples) if examples else ""
            keywords_str = "、".join(c.triggers.keywords[:5])
            templates_str = "、".join(c.templates.keys())
            tools_str = "、".join(c.get_required_tools())
            lines.append(
                f"- **{c.skill_id}**（{c.name}）\n"
                f"  关键词: {keywords_str}\n"
                f"  示例: {examples_str}\n"
                f"  模板: {templates_str}\n"
                f"  工具: {tools_str}"
            )
        return "\n".join(lines)

    # Tool names that LLM commonly confuses with skill_ids (logged + rejected).
    _TOOL_NAME_BLACKLIST: frozenset[str] = frozenset({
        "get_customer_profile",
        "get_bill_and_repayment_plan",
        "get_loan_service_info",
        "get_call_history",
        "get_sms_history",
        "get_stop_collection_history",
        "query_ticket",
        "submit_ticket",
    })

    @classmethod
    def _parse_response(cls, raw: str, candidate_ids: set[str]) -> SkillMatch:
        """Parse LLM JSON response into SkillMatch."""
        if not raw:
            return SkillMatch(skill_id="none", confidence=0.0, reasoning="empty LLM response")

        try:
            text = raw.strip()
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]

            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("failed to parse LLM routing response: %s", raw[:200])
            return SkillMatch(skill_id="none", confidence=0.0, reasoning="JSON parse error")

        raw_skill_id = data.get("skill_id", "none")
        unknown_returned: str | None = None
        tool_name_returned: str | None = None

        skill_id = raw_skill_id
        if skill_id != "none" and skill_id not in candidate_ids:
            if skill_id in cls._TOOL_NAME_BLACKLIST:
                tool_name_returned = skill_id
                logger.warning(
                    "LLM returned tool name as skill_id (blacklisted): %s", skill_id,
                )
            else:
                unknown_returned = skill_id
                logger.warning("LLM returned unknown skill_id: %s", skill_id)
            skill_id = "none"

        raw_alts = data.get("alternatives") or []
        alternatives: list[dict[str, Any]] = []
        seen: set[str] = {skill_id} if skill_id != "none" else set()
        for alt in raw_alts:
            if not isinstance(alt, dict):
                continue
            alt_sid = alt.get("skill_id")
            if not alt_sid or alt_sid == "none":
                continue
            if alt_sid in seen or alt_sid not in candidate_ids:
                continue
            seen.add(alt_sid)
            alternatives.append({
                "skill_id": alt_sid,
                "confidence": float(alt.get("confidence", 0.0)),
                "reason": alt.get("reason", ""),
            })

        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.0))

        # Fallback: if top-1 was rejected but alternatives carry a valid candidate,
        # promote the first valid alternative so downstream isn't stuck at "none".
        if skill_id == "none" and alternatives:
            promoted = alternatives.pop(0)
            skill_id = promoted["skill_id"]
            confidence = min(promoted.get("confidence", 0.0) or 0.0, 0.5)
            tag = "tool-name" if tool_name_returned else (unknown_returned or "unknown")
            reasoning = f"[fallback-from:{tag}] {reasoning}".strip()

        return SkillMatch(
            skill_id=skill_id,
            template_variant=data.get("template_variant", "first_contact"),
            confidence=confidence,
            tools_needed=data.get("tools_needed", []),
            extracted_slots=data.get("extracted_slots", {}),
            reasoning=reasoning,
            alternatives=alternatives,
        )
