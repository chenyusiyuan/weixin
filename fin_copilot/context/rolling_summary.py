"""Layer 2: Rolling summary — rule-based event compression (no LLM).

Produces two tracks per session:
- ``state.summary``        : event log (intent shifts, slot gains, tool calls).
  Kept for debugging / audit; cheap to append.
- ``state.narrative_summary``: 3-5 sentence human-readable recap that the LLM
  actually consumes. Built by sliding a fixed number of "turn events" forward,
  then joined with Chinese semicolons. No LLM involved.
"""

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

    # Max short sentences kept in narrative_summary (sliding window)
    NARRATIVE_MAX_SENTENCES: int = 5
    NARRATIVE_SEP: str = "；"

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
        user_query: Optional[str] = None,
        agent_reply: Optional[str] = None,
    ) -> None:
        """Append event-based summary entries, then compress if needed."""
        if not any([
            prev_intent != new_intent and new_intent,
            new_slots,
            tools_called,
            risk_flag,
            verification_completed,
            exited_messages,
            user_query,
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

        # Update narrative track (independent of event log compression)
        self._update_narrative(
            state,
            user_query=user_query,
            agent_reply=agent_reply,
            new_intent=new_intent,
            new_slots=new_slots,
            tools_called=tools_called,
            risk_flag=risk_flag,
        )

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

    # ------------------------------------------------------------------
    # Narrative track (separate from event log)
    # ------------------------------------------------------------------

    def _update_narrative(
        self,
        state: ConversationState,
        *,
        user_query: Optional[str],
        agent_reply: Optional[str],
        new_intent: Optional[str],
        new_slots: Optional[dict[str, Any]],
        tools_called: Optional[list[str]],
        risk_flag: Optional[str],
    ) -> None:
        """Append a one-sentence recap of this turn, then slide to last N sentences."""
        sentence = self._build_sentence(
            turn=state.total_turns,
            user_query=user_query or "",
            agent_reply=agent_reply or "",
            new_intent=new_intent,
            new_slots=new_slots or {},
            tools_called=tools_called or [],
            risk_flag=risk_flag,
        )
        if not sentence:
            return

        existing = state.narrative_summary.split(self.NARRATIVE_SEP) if state.narrative_summary else []
        existing = [s for s in (x.strip() for x in existing) if s]
        existing.append(sentence)
        if len(existing) > self.NARRATIVE_MAX_SENTENCES:
            existing = existing[-self.NARRATIVE_MAX_SENTENCES:]
        state.narrative_summary = self.NARRATIVE_SEP.join(existing)

    @staticmethod
    def _build_sentence(
        *,
        turn: int,
        user_query: str,
        agent_reply: str,
        new_intent: Optional[str],
        new_slots: dict[str, Any],
        tools_called: list[str],
        risk_flag: Optional[str],
    ) -> str:
        """Render a compact Chinese sentence describing this turn."""
        q_snip = user_query.strip().replace("\n", " ")
        if len(q_snip) > 30:
            q_snip = q_snip[:30] + "…"

        fragments: list[str] = [f"第{turn}轮客户问「{q_snip}」"] if q_snip else [f"第{turn}轮"]
        if new_intent:
            fragments.append(f"归入{new_intent}")
        if tools_called:
            fragments.append(f"查了{','.join(tools_called[:2])}")
        meaningful_slots = {
            k: v for k, v in new_slots.items()
            if v not in (None, "", 0) and k not in ("emotion",)
        }
        if meaningful_slots:
            kv = ",".join(f"{k}={v}" for k, v in list(meaningful_slots.items())[:3])
            fragments.append(f"拿到{kv}")
        if risk_flag:
            fragments.append(f"出现{risk_flag}风险")
        if agent_reply:
            a_snip = agent_reply.strip().replace("\n", " ")
            if len(a_snip) > 24:
                a_snip = a_snip[:24] + "…"
            fragments.append(f"坐席回「{a_snip}」")
        return "，".join(fragments)
