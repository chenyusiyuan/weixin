"""Confidence audit result model (Agent B output)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfidenceAuditResult(BaseModel):
    score: float = 1.0
    passed: bool = True
    reasons: list[str] = Field(default_factory=list)
    fallback_type: str = ""  # "" | "safe_reply" | "handoff"
