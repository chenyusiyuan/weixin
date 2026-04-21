"""Layer 2: Rolling summary — rule-based event compression (no LLM)."""

from __future__ import annotations

from typing import Any, Optional

from fin_copilot.models.conversation import ConversationState, Message


class RollingSummary:
    """Maintains a compressed summary of older conversation history.

    Only records *events*, not raw text:
    - intent shifts
    - new slots discovered
    - tools called
    - risk flags detected
    - verification completed
    """

    def __init__(self, max_length: int = 300) -> None:
        self.max_length = max_length

    def update(
        self,
        state: ConversationState,
        exited_messages: list[Message],
        *,
        prev_intent: Optional[str] = None,
        new_intent: Optional[str] = None,
        new_slots: Optional[dict[str, Any]] = None,
        tools_called: Optional[list[str]] = None,
        risk_flag: Optional[str] = None,
        verification_completed: bool = False,
    ) -> None:
        """Append event-based summary entries, then compress if needed."""
        if not any([
            prev_intent != new_intent and new_intent,
            new_slots,
            tools_called,
            risk_flag,
            verification_completed,
            exited_messages,
        ]):
            return

        parts: list[str] = []

        # Intent shift
        if prev_intent != new_intent and new_intent:
            parts.append(f"意图切换：{prev_intent or '无'} → {new_intent}")

        # New slots
        if new_slots:
            slot_str = ", ".join(f"{k}={v}" for k, v in new_slots.items() if v)
            if slot_str:
                parts.append(f"新信息：{slot_str}")

        # Tools called
        if tools_called:
            parts.append(f"工具调用：{', '.join(tools_called)}")

        # Risk flags
        if risk_flag:
            parts.append(f"风险标签：{risk_flag}")

        # Verification
        if verification_completed:
            parts.append("已完成身份验证")

        if parts:
            new_entry = "；".join(parts)
            if state.summary:
                state.summary += " | " + new_entry
            else:
                state.summary = new_entry

        # Compress if exceeds limit
        self._compress(state)

    def _compress(self, state: ConversationState) -> None:
        """If summary exceeds max_length, compress the early 1/3."""
        if len(state.summary) <= self.max_length:
            return

        # Split at the 1/3 mark
        cut_point = len(state.summary) // 3
        # Find the nearest separator after cut_point
        sep_pos = state.summary.find(" | ", cut_point)
        if sep_pos == -1:
            sep_pos = cut_point

        early_part = state.summary[:sep_pos]
        recent_part = state.summary[sep_pos:]
        # Strip leading separator from recent part
        recent_part = recent_part.lstrip(" |")

        # Compress early part to a brief prefix
        compressed_early = early_part[:50].rstrip("；| ") + "..."
        state.summary = f"早期：{compressed_early} | {recent_part}"

        # If still too long, truncate from the front
        if len(state.summary) > self.max_length:
            state.summary = state.summary[-self.max_length:]
