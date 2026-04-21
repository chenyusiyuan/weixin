"""Copilot response model — the final output for each turn."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CopilotResponse(BaseModel):
    output_type: str = "bot_reply"  # bot_reply | followup | handoff | fallback
    answer: str = ""
    next_step_hint: str = ""

    matched_skill_id: Optional[str] = None
    matched_skill_name: Optional[str] = None
    confidence: float = 0.0
    route: str = ""  # route_a | route_b | route_c | route_c_fallback

    # Top-K skill candidates for evaluation
    top_candidates: list[str] = Field(default_factory=list)  # [skill_id_1, skill_id_2, skill_id_3]

    warning: Optional[str] = None
    rag_references: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)

    trace_id: str = ""
    compliance_passed: bool = True
    compliance_issues: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0
