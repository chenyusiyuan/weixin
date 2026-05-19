"""Dialogue-state helpers: intent stickiness, reverse signals, reference resolution.

All zero-LLM. Lives between L0 preprocessing and routing; consulted by the
orchestrator to decide whether to short-circuit to the previous skill's
follow-up template, or to force a re-route.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from fin_copilot.models.conversation import ConversationState

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Keyword tables
# ----------------------------------------------------------------------

# Short affirmations / continuation prompts that carry no new business content
_FOLLOWUP_TOKENS: tuple[str, ...] = (
    "嗯", "哦", "噢", "好的", "好", "可以", "行", "对", "对的", "没错",
    "明白", "知道了", "收到", "然后呢", "然后", "接着呢", "继续",
    "还有呢", "还有吗", "所以呢", "那呢", "那怎么办", "那怎么处理",
    "是吗", "真的吗", "这样啊", "okay", "ok",
)

# Explicit topic-switch intents — once hit, drop the sticky lock
_TOPIC_SWITCH_TOKENS: tuple[str, ...] = (
    "换个问题", "换一个", "再问一个", "另外", "另一个", "还有个",
    "还有一个", "我还想问", "我想问", "再问一下", "别的问题",
    "不问这个", "先不说这个", "先不管这个", "跳过这个",
    "算了", "先不说了", "回到刚才", "对了", "顺便问一下",
)

# Negation prefixes combined with previous domain -> switch away
_NEGATION_PREFIXES: tuple[str, ...] = ("不", "不是", "别", "不用", "不要")

# Risk flag names that force re-routing regardless of stickiness
_HARD_RESET_RISK_FLAGS: frozenset[str] = frozenset({
    "complaint", "legal_threat", "suicide_risk",
})

# Generic slots preserved across intent transitions (mirrors structured_state)
_ANCHOR_SLOT_KEYS: tuple[str, ...] = (
    "customer_name", "phone_masked", "id_last4", "customer_id",
    "bill_amount", "bill_period", "due_date", "mentioned_amount",
    "mentioned_days",
)

# Demonstrative pronouns that commonly need resolution in short follow-ups
_REFERENCE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("它", "anchor"),
    ("这个", "anchor"),
    ("那个", "anchor"),
    ("上面说的", "anchor"),
    ("刚才那个", "anchor"),
    ("刚说的", "anchor"),
    ("之前那个", "anchor"),
)


# ----------------------------------------------------------------------
# Decision dataclass
# ----------------------------------------------------------------------

class StickyDecision:
    """Carries the outcome of should_stick() without pulling pydantic in."""

    __slots__ = ("stick", "reason", "template_variant", "drop_tools")

    def __init__(
        self,
        stick: bool,
        reason: str,
        template_variant: str = "follow_up",
        drop_tools: bool = True,
    ) -> None:
        self.stick = stick
        self.reason = reason
        self.template_variant = template_variant
        self.drop_tools = drop_tools


# ----------------------------------------------------------------------
# Manager
# ----------------------------------------------------------------------

class DialogueStateManager:
    """Zero-LLM multi-turn helpers shared by the orchestrator."""

    def __init__(
        self,
        *,
        max_sticky_turns: int = 3,
        followup_max_len: int = 12,
        duplicate_threshold: float = 0.82,
    ) -> None:
        self.max_sticky_turns = max_sticky_turns
        self.followup_max_len = followup_max_len
        self.duplicate_threshold = duplicate_threshold

    # ------------------------------------------------------------------
    # Sticky decision
    # ------------------------------------------------------------------

    def should_stick(
        self,
        state: ConversationState,
        query: str,
        *,
        domain_keywords_for_other: list[str] | None = None,
        current_skill_has_escalation: bool = False,
    ) -> StickyDecision:
        """Decide whether to reuse the previous skill's follow_up template."""
        if not state.intent.current_skill_id:
            return StickyDecision(False, "no_prior_skill")

        # Hard reset when high-risk flags just surfaced
        # Exception: if the current skill already has escalation branches for
        # this risk type, keep sticky so the branch can handle it.
        if any(f in _HARD_RESET_RISK_FLAGS for f in state.risk_flags):
            if not current_skill_has_escalation:
                return StickyDecision(False, "risk_flag_reset")

        # Turn-in-skill budget — prevent rubber-banding
        if state.intent.turn_in_skill >= self.max_sticky_turns:
            return StickyDecision(False, "turn_budget_exceeded")

        # Already stuck this turn? skip (defensive)
        if state.last_sticky_turn == state.total_turns + 1:
            return StickyDecision(False, "already_sticky")

        if self._hits_topic_switch(query):
            return StickyDecision(False, "topic_switch_signal")

        if domain_keywords_for_other and self._hits_other_domain(
            query, domain_keywords_for_other,
        ):
            return StickyDecision(False, "other_domain_keywords")

        if self._hits_negation_on_prev_topic(query, state):
            return StickyDecision(False, "negation_on_prev_topic")

        if self._is_followup_signal(query):
            return StickyDecision(True, "followup_signal", "follow_up")

        # Short answer to a previous agent question — e.g. "下个月吧" in response
        # to "请问您大概什么时候能够还款呢？"
        if self._is_short_answer_to_question(query, state):
            return StickyDecision(True, "short_answer_to_question", "follow_up")

        return StickyDecision(False, "no_signal")

    # ------------------------------------------------------------------
    # Slot delta — "has anything actually changed this turn?"
    # ------------------------------------------------------------------

    @staticmethod
    def slot_fingerprint(slots: dict[str, Any]) -> str:
        """Stable hash of the anchor slots, for cheap delta detection."""
        picked = {k: slots[k] for k in sorted(slots) if k in _ANCHOR_SLOT_KEYS}
        payload = json.dumps(picked, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]

    def has_slot_progress(
        self,
        state: ConversationState,
        tool_results: dict[str, Any] | None = None,
        tools_called: list[str] | None = None,
    ) -> bool:
        """Return True when anchor-slot fingerprint actually changed this turn."""
        current = self.slot_fingerprint(state.slots)
        changed = current != state.last_slot_fingerprint
        if changed:
            logger.debug(
                "slot_progress: fingerprint changed %s -> %s",
                state.last_slot_fingerprint, current,
            )
        return changed

    # ------------------------------------------------------------------
    # Duplicate-reply guard
    # ------------------------------------------------------------------

    def is_duplicate_reply(self, new_reply: str, previous_reply: str) -> float:
        """Return similarity ratio; caller compares to threshold."""
        if not new_reply or not previous_reply:
            return 0.0
        a, b = new_reply.strip(), previous_reply.strip()
        if not a or not b:
            return 0.0
        if abs(len(a) - len(b)) / max(len(a), len(b)) > 0.5:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    # ------------------------------------------------------------------
    # Reference resolution — best-effort anchor lookup
    # ------------------------------------------------------------------

    def resolve_references(self, query: str, state: ConversationState) -> str:
        """Replace short pronouns with anchor slots when safe.

        Conservative: only rewrites when (a) query length <= 12 chars AND
        (b) we actually have an anchor slot to plug in.
        """
        if not query or len(query) > self.followup_max_len:
            return query
        anchor = self._select_anchor(state)
        if not anchor:
            return query
        rewritten = query
        for pattern, _ in _REFERENCE_PATTERNS:
            if pattern in rewritten:
                rewritten = rewritten.replace(pattern, anchor, 1)
                break
        return rewritten

    @staticmethod
    def _select_anchor(state: ConversationState) -> str:
        """Pick the best anchor phrase from slots/intent/domain."""
        # Prefer concrete business anchors over identity
        for key in ("bill_period", "bill_amount", "due_date",
                    "mentioned_amount", "customer_request"):
            v = state.slots.get(key)
            if v not in (None, "", 0):
                if key == "bill_amount":
                    return f"{v}元账单"
                if key == "bill_period":
                    return f"第{v}期账单"
                if key == "due_date":
                    return f"还款日{v}"
                if key == "mentioned_amount":
                    return f"{v}元"
                return str(v)
        # Fall back to intent domain as a rough anchor
        if state.intent.domain:
            return f"{state.intent.domain}问题"
        return ""

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _is_followup_signal(self, query: str) -> bool:
        q = query.strip().rstrip("。.！!？?~，,")
        if not q:
            return False
        if len(q) > self.followup_max_len:
            return False
        # Exact match only
        if q in _FOLLOWUP_TOKENS:
            return True
        return False

    def _is_short_answer_to_question(self, query: str, state: ConversationState) -> bool:
        """Detect short replies to the agent's previous question.

        When the agent ended the last turn with a question (e.g. "什么时候还款？")
        and the user gives a brief answer (e.g. "下个月吧"), the turn should stay
        in the current skill rather than re-routing.
        """
        q = query.strip()
        if not q or len(q) > self.followup_max_len:
            return False
        prev = (state.last_agent_reply or "").strip()
        if not prev:
            return False
        # Check if the agent's last reply ended with a question mark
        if not prev.endswith(("？", "?", "呢？", "呢?")):
            return False
        return True

    @staticmethod
    def _hits_topic_switch(query: str) -> bool:
        return any(tok in query for tok in _TOPIC_SWITCH_TOKENS)

    @staticmethod
    def _hits_other_domain(query: str, other_keywords: list[str]) -> bool:
        return any(kw in query for kw in other_keywords)

    @staticmethod
    def _hits_negation_on_prev_topic(query: str, state: ConversationState) -> bool:
        domain = state.intent.domain or ""
        if not domain:
            return False
        if not any(query.startswith(p) for p in _NEGATION_PREFIXES):
            return False
        # "不查账单了"、"不是还款"
        return domain in query or any(
            kw in query for kw in ("账单", "还款", "额度", "贷款", "会员", "费用")
            if kw == domain or kw in domain
        )

    # ------------------------------------------------------------------
    # Post-turn bookkeeping
    # ------------------------------------------------------------------

    def record_turn(
        self,
        state: ConversationState,
        agent_reply: str,
        *,
        was_sticky: bool,
    ) -> None:
        state.last_agent_reply = agent_reply or ""
        state.last_slot_fingerprint = self.slot_fingerprint(state.slots)
        if was_sticky:
            state.last_sticky_turn = state.total_turns
