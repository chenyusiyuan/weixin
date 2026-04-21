"""Chain A: Rule engine — zero-LLM keyword-based rule matching."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.skill import SkillDefinition
from fin_copilot.skills.loader import SkillLoader

logger = logging.getLogger(__name__)


class RuleMatchResult(BaseModel):
    rule_id: str = ""
    skill_id: str = ""
    skill: Optional[SkillDefinition] = None
    template_variant: str = "first_contact"
    tools_needed: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class RuleEngine:
    """Keyword-based rule matching for Chain A (zero LLM, <200ms)."""

    def __init__(self, rule_path: str, skill_loader: SkillLoader) -> None:
        self._rules = self._load_rules(rule_path)
        self._skill_loader = skill_loader

    @staticmethod
    def _load_rules(path: str) -> list[dict[str, Any]]:
        p = Path(path)
        if not p.exists():
            logger.warning("rule engine file not found: %s", path)
            return []
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rules", [])

    def match(
        self,
        query: str,
        state: ConversationState,
    ) -> RuleMatchResult | None:
        """Try to match query against Chain A rules.

        Returns RuleMatchResult with confidence=1.0 on hit, or None.
        """
        for rule in self._rules:
            if self._check_rule(query, rule):
                skill_id = rule.get("skill_id", "")
                skill = self._skill_loader.get_skill(skill_id)
                if skill is None:
                    logger.warning("rule %s references unknown skill %s",
                                   rule.get("rule_id"), skill_id)
                    continue

                # Determine template variant
                variant = rule.get("template_variant") or self._determine_variant(skill, state)
                tools_needed = skill.get_required_tools()

                return RuleMatchResult(
                    rule_id=rule.get("rule_id", ""),
                    skill_id=skill_id,
                    skill=skill,
                    template_variant=variant,
                    tools_needed=tools_needed,
                    confidence=1.0,
                )
        return None

    @staticmethod
    def _check_rule(query: str, rule: dict[str, Any]) -> bool:
        """Check if query matches a rule: ANY keyword hit + NO exclude hit."""
        keywords = rule.get("keywords", [])
        exclude_keywords = rule.get("exclude_keywords", [])

        # Must match at least one keyword
        if not any(kw in query for kw in keywords):
            return False

        # Must not match any exclude keyword
        if any(kw in query for kw in exclude_keywords):
            return False

        return True

    @staticmethod
    def _determine_variant(
        skill: SkillDefinition,
        state: ConversationState,
    ) -> str:
        """Choose template variant based on turn_in_skill."""
        template_keys = list(skill.templates.keys())
        if not template_keys:
            return "first_contact"

        turn = state.intent.turn_in_skill
        if turn <= 1 or state.intent.current_skill_id != skill.skill_id:
            return template_keys[0]
        elif turn == 2 and len(template_keys) >= 2:
            return template_keys[1]
        elif len(template_keys) >= 3:
            return template_keys[-1]
        else:
            return template_keys[-1]
