"""Layer 3: Structured state — intent tracking, slots, tool cache, risk flags."""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from fin_copilot.models.conversation import ConversationState, ToolCacheEntry


# Slots considered "generic" and preserved across intent switches
_GENERIC_SLOTS = frozenset({
    "customer_name", "phone_masked", "id_last4",
    "customer_id", "customer_request", "emotion",
})

# Risk flag detection keywords
_RISK_PATTERNS: dict[str, list[str]] = {
    "emotional": ["生气", "气死", "太过分", "什么破", "垃圾", "你们怎么", "受不了", "忍无可忍"],
    "complaint": ["投诉", "举报", "银保监", "12378", "工信部", "消费者协会", "315"],
    "legal_threat": ["起诉", "法院", "律师", "法律", "报警", "诉讼"],
    "suicide_risk": ["不想活", "活不下去", "自杀", "轻生"],
}

# Emotion detection patterns
_EMOTION_PATTERNS: dict[str, list[str]] = {
    "angry": ["生气", "气死", "太过分", "什么破", "垃圾", "你们怎么回事", "愤怒"],
    "anxious": ["着急", "急", "焦虑", "怎么办", "来不及", "赶紧"],
    "sad": ["难过", "困难", "无奈", "没办法", "走投无路"],
    "neutral": [],
}


class StructuredStateManager:
    """Manages Layer 3: structured state fields in ConversationState."""

    def __init__(self, tool_cache_ttl: int = 300) -> None:
        self.tool_cache_ttl = tool_cache_ttl

    def update_intent(
        self,
        state: ConversationState,
        skill_id: Optional[str],
        domain: Optional[str],
    ) -> None:
        """Update intent state. On intent switch, reset turn and clear scene slots."""
        if skill_id is None:
            return

        if state.intent.current_skill_id == skill_id:
            # Same skill — increment turn
            state.intent.turn_in_skill += 1
        else:
            # Intent switch
            if state.intent.current_skill_id is not None:
                state.intent.intent_shifts.append({
                    "from": state.intent.current_skill_id,
                    "to": skill_id,
                    "at_turn": state.total_turns,
                })
                # Clear scene-specific slots, keep generic
                state.slots = {
                    k: v for k, v in state.slots.items()
                    if k in _GENERIC_SLOTS
                }
            state.intent.current_skill_id = skill_id
            state.intent.turn_in_skill = 1

        if domain:
            state.intent.domain = domain

    def update_slots(self, state: ConversationState, new_slots: dict[str, Any]) -> None:
        """Merge new slots into state, skipping None values."""
        for k, v in new_slots.items():
            if v is not None:
                state.slots[k] = v

    def update_tool_cache(
        self,
        state: ConversationState,
        tool_name: str,
        data: dict[str, Any],
    ) -> None:
        """Write tool result to cache with current timestamp."""
        state.tool_cache[tool_name] = ToolCacheEntry(
            data=data,
            ts=time.monotonic(),
        )

    def get_cached_tool(
        self,
        state: ConversationState,
        tool_name: str,
    ) -> dict[str, Any] | None:
        """Retrieve cached tool result; return None if expired or absent."""
        entry = state.tool_cache.get(tool_name)
        if entry is None:
            return None
        if (time.monotonic() - entry.ts) >= self.tool_cache_ttl:
            # Expired — evict
            del state.tool_cache[tool_name]
            return None
        return entry.data

    def update_risk_flags(self, state: ConversationState, query: str) -> None:
        """Detect risk flags from the customer query via keyword matching."""
        for flag, keywords in _RISK_PATTERNS.items():
            if flag not in state.risk_flags:
                if any(kw in query for kw in keywords):
                    state.risk_flags.append(flag)

    def extract_slots_from_query(
        self,
        state: ConversationState,
        query: str,
    ) -> dict[str, Any]:
        """Rule-based slot extraction from customer query. Returns new slots."""
        extracted: dict[str, Any] = {}

        # Extract emotion
        for emotion, keywords in _EMOTION_PATTERNS.items():
            if keywords and any(kw in query for kw in keywords):
                extracted["emotion"] = emotion
                break
        if "emotion" not in extracted:
            extracted["emotion"] = "neutral"

        # Extract customer_request (core intent phrase)
        request_patterns = [
            (r"我想(.{2,20})", "customer_request"),
            (r"我要(.{2,20})", "customer_request"),
            (r"帮我(.{2,20})", "customer_request"),
            (r"能不能(.{2,20})", "customer_request"),
            (r"可以(.{2,20})吗", "customer_request"),
        ]
        for pattern, slot_name in request_patterns:
            m = re.search(pattern, query)
            if m:
                extracted[slot_name] = m.group(1).strip()
                break

        # Extract amount mentions
        amount_match = re.search(r"(\d+(?:\.\d+)?)\s*元", query)
        if amount_match:
            extracted["mentioned_amount"] = float(amount_match.group(1))

        # Extract day counts
        days_match = re.search(r"(\d+)\s*天", query)
        if days_match:
            extracted["mentioned_days"] = int(days_match.group(1))

        # Merge into state
        self.update_slots(state, extracted)
        return extracted
