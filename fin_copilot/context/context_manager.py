"""Unified context manager — orchestrates Layer 1/2/3 plus dialogue-state helpers."""

from __future__ import annotations

import time
from typing import Any, Optional

from fin_copilot.config import Settings
from fin_copilot.context.dialogue_state import DialogueStateManager, StickyDecision
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
        self.dialogue = DialogueStateManager(
            max_sticky_turns=settings.STICKY_MAX_TURNS,
            followup_max_len=settings.STICKY_FOLLOWUP_MAX_LEN,
            duplicate_threshold=settings.DUPLICATE_REPLY_THRESHOLD,
        )
        self._sessions: dict[str, ConversationState] = {}
        self._session_ttl = settings.SESSION_TTL_SECONDS
        self._session_last_access: dict[str, float] = {}
        self._access_counter: int = 0

    def get_or_create(self, session_id: str) -> ConversationState:
        self._session_last_access[session_id] = time.monotonic()
        self._access_counter += 1
        if self._access_counter % 100 == 0:
            self._sweep_expired()
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState(
                session_id=session_id,
                customer=CustomerInfo(),
            )
        return self._sessions[session_id]

    def _sweep_expired(self) -> None:
        """Remove sessions that have not been accessed within the TTL."""
        now = time.monotonic()
        expired = [
            sid for sid, last in self._session_last_access.items()
            if (now - last) >= self._session_ttl
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._session_last_access.pop(sid, None)

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

    # ------------------------------------------------------------------
    # Multi-turn helpers — delegated to DialogueStateManager
    # ------------------------------------------------------------------

    def resolve_references(self, state: ConversationState, query: str) -> str:
        return self.dialogue.resolve_references(query, state)

    def should_stick(
        self,
        state: ConversationState,
        query: str,
        other_domain_keywords: list[str] | None = None,
        current_skill_has_escalation: bool = False,
    ) -> StickyDecision:
        return self.dialogue.should_stick(
            state, query,
            domain_keywords_for_other=other_domain_keywords,
            current_skill_has_escalation=current_skill_has_escalation,
        )

    def has_slot_progress(
        self,
        state: ConversationState,
        tool_results: dict[str, Any] | None = None,
        tools_called: list[str] | None = None,
    ) -> bool:
        return self.dialogue.has_slot_progress(state, tool_results, tools_called)

    def duplicate_ratio(self, new_reply: str, previous_reply: str) -> float:
        return self.dialogue.is_duplicate_reply(new_reply, previous_reply)

    # ------------------------------------------------------------------
    # Post-turn
    # ------------------------------------------------------------------

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
        was_sticky: bool = False,
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

        # Update rolling summary (event log + narrative track)
        risk_flag = state.risk_flags[-1] if state.risk_flags else None
        self.summary.update(
            state,
            evicted,
            prev_intent=prev_intent,
            new_intent=skill_id,
            new_slots=new_slots,
            tools_called=tools_called,
            risk_flag=risk_flag if risk_flag and risk_flag != prev_intent else None,
            user_query=user_query,
            agent_reply=agent_reply,
        )

        # Dialogue-state bookkeeping (fingerprint, last reply, sticky turn)
        self.dialogue.record_turn(state, agent_reply, was_sticky=was_sticky)
