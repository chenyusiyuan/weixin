"""Layer 1: Sliding window — keeps the most recent N turns of conversation."""

from __future__ import annotations

from fin_copilot.models.conversation import ConversationState, Message


class SlidingWindow:
    """Manages a fixed-size window of recent conversation turns."""

    def __init__(self, max_turns: int = 8) -> None:
        self.max_turns = max_turns

    def add_turn(
        self,
        state: ConversationState,
        customer_msg: str,
        agent_msg: str,
    ) -> list[Message]:
        """Append a customer+agent turn pair; return any evicted messages."""
        state.total_turns += 1
        turn_num = state.total_turns

        state.messages.append(Message(role="customer", text=customer_msg, turn=turn_num))
        state.messages.append(Message(role="agent", text=agent_msg, turn=turn_num))

        evicted: list[Message] = []
        # Count unique turns in window
        turns_in_window = set(m.turn for m in state.messages)
        while len(turns_in_window) > self.max_turns:
            oldest_turn = min(turns_in_window)
            # Evict all messages from the oldest turn
            remaining: list[Message] = []
            for m in state.messages:
                if m.turn == oldest_turn:
                    evicted.append(m)
                else:
                    remaining.append(m)
            state.messages = remaining
            turns_in_window.discard(oldest_turn)

        return evicted

    def get_recent(
        self,
        state: ConversationState,
        n_turns: int | None = None,
    ) -> list[Message]:
        """Return the last n turns of messages (or all if n is None)."""
        if n_turns is None:
            return list(state.messages)

        turns = sorted(set(m.turn for m in state.messages))
        target_turns = set(turns[-n_turns:]) if n_turns <= len(turns) else set(turns)
        return [m for m in state.messages if m.turn in target_turns]

    def format_for_prompt(
        self,
        state: ConversationState,
        n_turns: int | None = None,
    ) -> str:
        """Format messages as ``[客户] ... \\n[坐席] ...`` for LLM prompts."""
        messages = self.get_recent(state, n_turns)
        lines: list[str] = []
        for m in messages:
            role_label = "[客户]" if m.role == "customer" else "[坐席]"
            lines.append(f"{role_label} {m.text}")
        return "\n".join(lines)
