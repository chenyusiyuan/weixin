"""Skill-related data models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SkillTriggers(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)


class SkillTemplate(BaseModel):
    script: str = ""
    required_slots: list[str] = Field(default_factory=list)
    next_step: str = ""


class SkillCompliance(BaseModel):
    forbidden_expressions: list[str] = Field(default_factory=list)
    required_disclaimer: str = ""
    must_include_when: list[dict[str, Any]] = Field(default_factory=list)


class SkillDefinition(BaseModel):
    """Represents a single Skill loaded from YAML."""

    skill_id: str
    name: str
    description: str = ""
    domain: str = ""
    intent_hierarchy: dict[str, str] = Field(default_factory=dict)
    route_mode: str = "tool_rag"  # tool_only | tool_rag | direct_reply | rag_only
    risk_level: str = "low"  # low | medium | high

    triggers: SkillTriggers = Field(default_factory=SkillTriggers)
    tools: dict[str, list[str]] = Field(default_factory=dict)  # {required: [...], optional: [...]}
    templates: dict[str, SkillTemplate] = Field(default_factory=dict)  # variant_name -> template
    branch_conditions: list[dict[str, Any]] = Field(default_factory=list)
    compliance: SkillCompliance = Field(default_factory=SkillCompliance)
    escalation: list[dict[str, Any]] = Field(default_factory=list)
    escalation_signals: list[str] = Field(default_factory=list)
    fallback: dict[str, Any] = Field(default_factory=dict)
    slot_sources: dict[str, str] = Field(default_factory=dict)
    priority: int = 0

    def get_required_tools(self) -> list[str]:
        return self.tools.get("required", [])

    def get_optional_tools(self) -> list[str]:
        return self.tools.get("optional", [])

    def get_template(self, variant: str) -> Optional[SkillTemplate]:
        return self.templates.get(variant)

    def get_first_template_key(self) -> str:
        if self.templates:
            return next(iter(self.templates))
        return "first_contact"


class SkillMatch(BaseModel):
    """Result of LLM Skill Routing."""

    skill_id: str = "none"
    template_variant: str = "first_contact"
    confidence: float = 0.0
    tools_needed: list[str] = Field(default_factory=list)
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    alternatives: list[dict[str, Any]] = Field(default_factory=list)

    def top_k_skill_ids(self, k: int = 3) -> list[str]:
        """Return (best, alt_1, alt_2, ...) skill_ids deduped in order."""
        out: list[str] = []
        seen: set[str] = set()
        for sid in [self.skill_id, *[a.get("skill_id") for a in self.alternatives]]:
            if not sid or sid in seen:
                continue
            out.append(sid)
            seen.add(sid)
            if len(out) >= k:
                break
        return out
