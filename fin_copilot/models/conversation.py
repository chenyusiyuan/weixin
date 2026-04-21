"""Core conversation state models — three-layer context architecture."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # "customer" | "agent"
    text: str
    turn: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class CustomerInfo(BaseModel):
    customer_id: str = "C001"
    name_masked: str = ""
    phone_masked: str = ""
    id_last4: str = ""
    verified: bool = False
    verification_level: str = "none"  # "none" | "basic" | "full"
    # 核身 (identity verification) tracking
    verification_step: str = "not_started"  # not_started | asking_name | asking_phone | asking_id | passed | failed
    collected_name: str = ""
    collected_phone: str = ""
    collected_id_last4: str = ""
    verification_attempts: int = 0
    pending_query: str = ""  # original business query to answer after verification
    candidate_customer_ids: list[str] = Field(default_factory=list)  # narrowed candidates during verification


class IntentState(BaseModel):
    current_skill_id: Optional[str] = None
    domain: Optional[str] = None
    turn_in_skill: int = 0
    intent_shifts: list[dict[str, Any]] = Field(default_factory=list)


class ToolCacheEntry(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = 0.0  # monotonic timestamp


class ComplianceState(BaseModel):
    disclaimer_given: bool = False
    forbidden_triggered: list[str] = Field(default_factory=list)


class ConversationState(BaseModel):
    session_id: str
    # Layer 1: sliding window
    messages: list[Message] = Field(default_factory=list)
    # Layer 2: rolling summary
    summary: str = ""
    # Layer 3: structured state
    customer: CustomerInfo = Field(default_factory=CustomerInfo)
    intent: IntentState = Field(default_factory=IntentState)
    slots: dict[str, Any] = Field(default_factory=dict)
    tool_cache: dict[str, ToolCacheEntry] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    compliance_state: ComplianceState = Field(default_factory=ComplianceState)
    # Counters
    total_turns: int = 0

    def to_tool_state(self) -> dict[str, Any]:
        """Serialize to the dict format expected by existing tool handlers.

        Tool handlers access ``state["customer"]["customer_id"]`` and
        ``state["slots"]``, so we mirror that shape here.
        """
        return {
            "customer": {
                "customer_id": self.customer.customer_id,
                "name_masked": self.customer.name_masked,
                "phone_masked": self.customer.phone_masked,
                "verified": self.customer.verified,
                "verification_level": self.customer.verification_level,
            },
            "slots": dict(self.slots),
            "intent": self.intent.model_dump(),
        }
