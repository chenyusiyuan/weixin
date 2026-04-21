"""Agent B: Confidence auditor — pure rule-based scoring (<10ms)."""

from __future__ import annotations

from typing import Any, Optional

from fin_copilot.models.audit import ConfidenceAuditResult
from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.skill import SkillDefinition, SkillMatch


class ConfidenceAuditor:
    """Rule-based confidence scoring for Chain B.

    Starts at 1.0 and applies deductions. Threshold >= 0.5 to pass.
    No LLM calls — must complete in <10ms.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    def audit(
        self,
        skill_match: SkillMatch,
        skill: Optional[SkillDefinition],
        state: ConversationState,
        l1_domain: str,
        tool_results: dict[str, Any],
        query: str = "",
    ) -> ConfidenceAuditResult:
        score = 1.0
        reasons: list[str] = []

        if skill is None:
            return ConfidenceAuditResult(
                score=0.0, passed=False,
                reasons=["skill_not_found"],
                fallback_type="safe_reply",
            )

        # 1. Low LLM confidence
        if skill_match.confidence < 0.7:
            score -= 0.3
            reasons.append(f"low_confidence({skill_match.confidence:.2f})")

        # 2. Domain mismatch
        if skill.domain and l1_domain and skill.domain != l1_domain:
            score -= 0.4
            reasons.append(f"domain_mismatch({skill.domain}!={l1_domain})")

        # 3. Missing required slots in the chosen template
        tpl = skill.get_template(skill_match.template_variant)
        if tpl is not None:
            available = set(state.slots.keys())
            # Also count slots from tool results
            for tr in tool_results.values():
                if isinstance(tr, dict):
                    available.update(tr.keys())
            missing = [s for s in tpl.required_slots if s not in available]
            if missing:
                penalty = 0.2 * len(missing)
                score -= penalty
                reasons.append(f"missing_slots({','.join(missing)})")

        # 4. Template variant not in skill
        if skill_match.template_variant not in skill.templates:
            score -= 0.2
            reasons.append(f"variant_mismatch({skill_match.template_variant})")

        # 5. Required tool failed
        for tool_name in skill.get_required_tools():
            if tool_name in tool_results:
                if tool_results[tool_name] is None:
                    score -= 0.5
                    reasons.append(f"tool_failed({tool_name})")
            # If tool wasn't called at all but is required
            elif tool_name not in tool_results:
                score -= 0.5
                reasons.append(f"tool_missing({tool_name})")

        # 6. Keyword overlap check
        if query and skill.triggers.keywords:
            has_overlap = any(kw in query for kw in skill.triggers.keywords)
            if not has_overlap:
                score -= 0.15
                reasons.append("keyword_no_overlap")

        # Clamp
        score = max(0.0, min(1.0, score))
        passed = score >= self.threshold

        fallback_type = ""
        if not passed:
            fallback_type = "handoff" if score < 0.2 else "safe_reply"

        return ConfidenceAuditResult(
            score=score,
            passed=passed,
            reasons=reasons,
            fallback_type=fallback_type,
        )
