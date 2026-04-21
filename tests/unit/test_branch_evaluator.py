"""Tests for fin_copilot.skills.branch_evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.skills.branch_evaluator import evaluate_expr, select_branch_variant  # noqa: E402


def test_simple_comparisons():
    assert evaluate_expr("overdue_days > 30", {"overdue_days": 45}) is True
    assert evaluate_expr("overdue_days > 30", {"overdue_days": 10}) is False
    assert evaluate_expr("overdue_days == 0", {"overdue_days": 0}) is True


def test_range_with_and():
    slots = {"overdue_days": 60}
    assert evaluate_expr("overdue_days > 30 and overdue_days <= 90", slots) is True
    assert evaluate_expr("overdue_days > 30 and overdue_days <= 90", {"overdue_days": 100}) is False


def test_missing_slot_returns_none():
    # Unknown identifier → None (indeterminate), NOT False
    assert evaluate_expr("has_membership is True", {}) is None
    # Short-circuit AND: if left is False we never evaluate the unknown right
    assert evaluate_expr("overdue_days > 30 and missing_flag", {"overdue_days": 5}) is False


def test_boolean_logic():
    assert evaluate_expr("not verified", {"verified": False}) is True
    assert evaluate_expr("a or b", {"a": False, "b": True}) is True
    assert evaluate_expr("a or b", {"a": False, "b": False}) is False


def test_in_operator():
    slots = {"status": "active"}
    assert evaluate_expr("status in ['active', 'pending']", slots) is True
    assert evaluate_expr("status in ['closed']", slots) is False


def test_rejects_function_call():
    # Unsafe — must return None (rejected), not execute
    assert evaluate_expr("len(items)", {"items": [1, 2]}) is None
    assert evaluate_expr("print(1)", {}) is None


def test_rejects_attribute_access():
    assert evaluate_expr("obj.attr", {"obj": object()}) is None


def test_rejects_subscript():
    assert evaluate_expr("items[0] > 1", {"items": [1, 2]}) is None


def test_invalid_syntax_returns_none():
    assert evaluate_expr("overdue_days >", {"overdue_days": 1}) is None
    assert evaluate_expr("", {}) is None
    assert evaluate_expr(None, {}) is None  # type: ignore[arg-type]


def test_select_branch_variant_expr_match():
    branches = [
        {"expr": "overdue_days == 0", "variant": "pre_overdue"},
        {"expr": "overdue_days > 0 and overdue_days <= 30", "variant": "early"},
        {"expr": "overdue_days > 30", "variant": "late"},
    ]
    variant, hints = select_branch_variant(branches, {"overdue_days": 15})
    assert variant == "early"
    assert hints == []


def test_select_branch_variant_falls_through_to_hint():
    branches = [
        {"expr": "overdue_days > 100", "variant": "severe"},
        {"hint": "客户坚持要升级", "variant": "escalate"},
    ]
    variant, hints = select_branch_variant(branches, {"overdue_days": 10})
    assert variant is None
    assert len(hints) == 1
    assert hints[0]["variant"] == "escalate"


def test_select_branch_variant_indeterminate_becomes_hint():
    """An `expr` that references missing slots surfaces as a hint when it also
    has a hint field, or is skipped when it doesn't."""
    branches = [
        {"expr": "has_membership is True", "hint": "客户有会员", "variant": "membership"},
        {"expr": "false_expr_only", "variant": "unreachable"},
    ]
    variant, hints = select_branch_variant(branches, {})
    assert variant is None
    # First branch had hint → surfaced; second had no hint → dropped.
    assert len(hints) == 1
    assert hints[0]["variant"] == "membership"


def test_legacy_condition_only_branch_is_skipped():
    """Branches with only a legacy `condition` field (post-migration should
    not exist, but be defensive) are gracefully skipped."""
    branches = [{"condition": "客户挽留成功", "variant": "retained"}]
    variant, hints = select_branch_variant(branches, {})
    assert variant is None
    assert hints == []
