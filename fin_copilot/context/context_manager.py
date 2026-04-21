"""Unified context manager — orchestrates Layer 1/2/3."""

from __future__ import annotations

from typing import Any, Optional

from fin_copilot.config import Settings
from fin_copilot.context.rolling_summary import RollingSummary
from fin_copilot.context.sliding_window import SlidingWindow
from fin_copilot.context.structured_state import StructuredStateManager
from fin_copilot.models.conversation import ConversationState, CustomerInfo


class ContextManager:
    """Manages per-session conversation state (Phase 1: in-memory store)."""

    def __init__(self, settings: Settings) -> None:
        self.window = SlidingWindow(max_turns=settings.SLIDING_WINDOW_SIZE)
        self.summary = RollingSummary(max_length=settings.SUMMARY_MAX_LENGTH)
        self.state_mgr = StructuredStateManager(
            tool_cache_ttl=settings.TOOL_CACHE_TTL,
        )
        self._sessions: dict[str, ConversationState] = {}

    def get_or_create(self, session_id: str) -> ConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState(
                session_id=session_id,
                customer=CustomerInfo(),
            )
        return self._sessions[session_id]

    def process_turn_start(
        self,
        state: ConversationState,
        user_query: str,
    ) -> dict[str, Any]:
        """Pre-turn processing: extract risk flags and slots from the query.

        Returns newly extracted slots.
        """
        self.state_mgr.update_risk_flags(state, user_query)
        new_slots = self.state_mgr.extract_slots_from_query(state, user_query)
        return new_slots

    def process_turn_end(
        self,
        state: ConversationState,
        user_query: str,
        agent_reply: str,
        *,
        skill_id: Optional[str] = None,
        domain: Optional[str] = None,
        new_slots: Optional[dict[str, Any]] = None,
        tools_called: Optional[list[str]] = None,
    ) -> None:
        """Post-turn processing: update intent, add turn to window, update summary."""
        prev_intent = state.intent.current_skill_id

        # Update intent
        self.state_mgr.update_intent(state, skill_id, domain)

        # Merge any additional slots
        if new_slots:
            self.state_mgr.update_slots(state, new_slots)

        # Add turn to sliding window
        evicted = self.window.add_turn(state, user_query, agent_reply)

        # Update rolling summary with events
        risk_flag = state.risk_flags[-1] if state.risk_flags else None
        self.summary.update(
            state,
            evicted,
            prev_intent=prev_intent,
            new_intent=skill_id,
            new_slots=new_slots,
            tools_called=tools_called,
            risk_flag=risk_flag if risk_flag and risk_flag != prev_intent else None,
        )
