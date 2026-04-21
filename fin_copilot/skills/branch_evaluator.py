"""Safe boolean evaluator for Skill branch_conditions `expr` field.

The `expr` DSL allows only:
  - comparisons: == != < <= > >= in is
  - logical: and / or / not
  - parens, identifiers, numeric/string/bool/None literals
  - NO function calls, attribute access, subscripts, lambdas

Identifiers are resolved against the provided slots mapping. When an
identifier is missing, `evaluate_expr` returns ``None`` (meaning "unknown",
not False) so the orchestrator can distinguish "branch didn't match" from
"branch couldn't be evaluated yet".
"""

from __future__ import annotations

import ast
import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not,
    ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Name, ast.Load,
    ast.Constant,
    ast.List, ast.Tuple, ast.Set,
)


class _UnsafeExpr(Exception):
    pass


class _MissingName(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _check_safe(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise _UnsafeExpr(f"disallowed AST node: {type(node).__name__}")


def _eval(node: ast.AST, slots: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, slots)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in slots:
            return slots[node.id]
        raise _MissingName(node.id)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for v in node.values:
                result = result and _eval(v, slots)
                if not result:
                    return False
            return bool(result)
        # Or
        result = False
        for v in node.values:
            result = result or _eval(v, slots)
            if result:
                return True
        return bool(result)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, slots)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, slots)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, slots)
            if isinstance(op, ast.Eq) and not (left == right):
                return False
            if isinstance(op, ast.NotEq) and not (left != right):
                return False
            if isinstance(op, ast.Lt) and not (left < right):
                return False
            if isinstance(op, ast.LtE) and not (left <= right):
                return False
            if isinstance(op, ast.Gt) and not (left > right):
                return False
            if isinstance(op, ast.GtE) and not (left >= right):
                return False
            if isinstance(op, ast.In) and not (left in right):
                return False
            if isinstance(op, ast.NotIn) and not (left not in right):
                return False
            if isinstance(op, ast.Is) and not (left is right):
                return False
            if isinstance(op, ast.IsNot) and not (left is not right):
                return False
            left = right
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_eval(e, slots) for e in node.elts]
    raise _UnsafeExpr(f"unsupported node: {type(node).__name__}")


def evaluate_expr(expr: str, slots: Mapping[str, Any]) -> bool | None:
    """Return bool(expr) against slots, or None if expr references a missing name.

    Raises nothing for invalid input — logs and returns None.
    """
    if not expr or not isinstance(expr, str):
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        _check_safe(tree)
        return bool(_eval(tree, slots))
    except _MissingName as exc:
        logger.debug("branch expr missing slot `%s`: %r", exc.name, expr)
        return None
    except _UnsafeExpr as exc:
        logger.warning("unsafe branch expr rejected (%s): %r", exc, expr)
        return None
    except SyntaxError:
        logger.warning("branch expr syntax error: %r", expr)
        return None


def select_branch_variant(
    branches: list[dict[str, Any]],
    slots: Mapping[str, Any],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Walk branch_conditions; return (matched_variant, remaining_hint_branches).

    The first branch whose `expr` evaluates to True wins. Branches that are
    hint-only (or whose expr can't be evaluated) are collected into the
    returned list so Agent A can receive them as natural-language context.
    """
    hints: list[dict[str, Any]] = []
    for br in branches or []:
        if not isinstance(br, dict):
            continue
        expr = br.get("expr")
        if expr:
            val = evaluate_expr(expr, slots)
            if val is True:
                return br.get("variant"), hints
            if val is False:
                continue
            # val is None → indeterminate, surface to LLM as hint
        if br.get("hint"):
            hints.append(br)
    return None, hints
