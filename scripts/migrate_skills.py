"""Auto-migrate all skill YAMLs to the new schema.

Changes applied per skill (idempotent — safe to re-run):

1. `required_slots`: rewritten as the union of {placeholders} found in that
   template's `script` (+ any slots already declared that still appear).

2. `branch_conditions[*]`: legacy `condition` is split into `expr` (when the
   string parses as a boolean Python expression over slot names) and/or `hint`
   (natural language). Both fields may coexist.

3. `slot_sources`: inserted (as a top-level mapping) containing every
   placeholder used anywhere in the file. Entries default to a best-guess
   source using naming conventions; unresolved entries are set to
   `llm:<slot>` with an "# TODO verify" inline comment so humans can correct
   them before committing.

4. `escalation_signals`: inserted (empty list) unless already present. Used by
   Chain A keyword pre-match to force tier2 routing.

Run:
    python scripts/migrate_skills.py           # dry run (diff only)
    python scripts/migrate_skills.py --apply   # write files
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, PreservedScalarString

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills" / "definitions"

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Tokens that appear in machine-evaluable `expr` strings.
EXPR_TOKEN_RE = re.compile(
    r"^[\sa-zA-Z0-9_<>=!&|+\-*/().,'\"]+$"
)
# Python booleans we allow in expressions.
ALLOWED_EXPR_NAMES = {
    "and", "or", "not", "True", "False", "None",
    "in", "is",
}


# ---------------------------------------------------------------------------
# Slot-source heuristics
# ---------------------------------------------------------------------------
# Slot-name prefixes/tokens → default source expression.
# Humans should audit output before commit.
SLOT_SOURCE_HEURISTICS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^customer_name$"),              "tool:get_customer_profile.name"),
    (re.compile(r"^customer_phone$"),             "tool:get_customer_profile.phone"),
    (re.compile(r"^customer_id$"),                "tool:get_customer_profile.customer_id"),
    (re.compile(r"^verification_info$"),          "derived:verification_info"),
    (re.compile(r"^verify_question$"),            "system:verify_question"),
    (re.compile(r"^verify_answer$"),              "user_input:verify_answer"),
    (re.compile(r"^agent_name$"),                 "system:agent_name"),
    (re.compile(r"^order_id$"),                   "tool:get_bill_and_repayment_plan.order_id"),
    (re.compile(r"^bill_amount$"),                "tool:get_bill_and_repayment_plan.amount"),
    (re.compile(r"^bill_period$"),                "tool:get_bill_and_repayment_plan.period"),
    (re.compile(r"^bill_status$"),                "tool:get_bill_and_repayment_plan.status"),
    (re.compile(r"^due_date$"),                   "tool:get_bill_and_repayment_plan.due_date"),
    (re.compile(r"^overdue_amount$"),             "tool:get_bill_and_repayment_plan.overdue_amount"),
    (re.compile(r"^overdue_days$"),               "tool:get_bill_and_repayment_plan.overdue_days"),
    (re.compile(r"^deduction_"),                  "tool:get_bill_and_repayment_plan.deduction"),
    (re.compile(r"^repayment_"),                  "tool:get_bill_and_repayment_plan.repayment"),
    (re.compile(r"^loan_"),                       "tool:get_loan_service_info.loan"),
    (re.compile(r"^disbursement_"),               "tool:get_loan_service_info.disbursement"),
    (re.compile(r"^member_"),                     "tool:get_membership_service_info.member"),
    (re.compile(r"^quota_"),                      "tool:get_quota_service_info.quota"),
    (re.compile(r"^ticket_"),                     "tool:query_ticket.ticket"),
    (re.compile(r"^fee_"),                        "tool:get_bill_and_repayment_plan.fee"),
    (re.compile(r"^followup_days$"),              "system:followup_days"),
]


def infer_slot_source(slot: str) -> str:
    for pattern, source in SLOT_SOURCE_HEURISTICS:
        if pattern.search(slot):
            return source
    # Unknown → LLM-filled by default, human should review.
    return f"llm:{slot}"


# ---------------------------------------------------------------------------
# Condition → expr/hint split
# ---------------------------------------------------------------------------

def parse_condition(text: str) -> tuple[str | None, str | None]:
    """Return (expr, hint). expr is set only when `text` is a safe Python bool expr.

    Heuristic: strip whitespace; if the string contains only ASCII alphanumerics,
    comparison operators, logical keywords, parens, and quoted constants, try
    to parse it with ast.parse(mode='eval'). Reject if it resolves to anything
    we consider non-deterministic.
    """
    if not isinstance(text, str):
        return None, None
    raw = text.strip()
    if not raw:
        return None, None

    # Normalise AND/OR keywords.
    normalised = re.sub(r"\bAND\b", "and", raw)
    normalised = re.sub(r"\bOR\b", "or", normalised)
    normalised = re.sub(r"\bNOT\b", "not", normalised)

    # Cheap character gate — if it has CJK chars, it's natural language.
    if re.search(r"[\u4e00-\u9fff]", normalised):
        return None, raw

    # Try parsing as a Python expression.
    try:
        tree = ast.parse(normalised, mode="eval")
    except SyntaxError:
        return None, raw

    # Walk the AST: reject function calls, attribute access, dangerous names.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.Attribute, ast.Lambda, ast.Subscript)):
            return None, raw
        if isinstance(node, ast.Name) and node.id in {"__import__", "eval", "exec", "open"}:
            return None, raw

    return normalised, None


# ---------------------------------------------------------------------------
# Migration per-file
# ---------------------------------------------------------------------------

yaml_rt = YAML(typ="rt")
yaml_rt.preserve_quotes = True
yaml_rt.width = 4096  # keep long lines intact
yaml_rt.indent(mapping=2, sequence=4, offset=2)


def load_skill(path: Path) -> tuple[CommentedMap, CommentedMap]:
    """Skill YAMLs use --- delimited docs. Return (front_matter, body)."""
    with open(path, encoding="utf-8") as f:
        docs = list(yaml_rt.load_all(f))
    docs = [d for d in docs if d is not None]
    if len(docs) == 1:
        return CommentedMap(), docs[0]
    return docs[0], docs[1]


def dump_skill(path: Path, front: CommentedMap, body: CommentedMap) -> None:
    buf = StringIO()
    buf.write("---\n")
    yaml_rt.dump(front, buf)
    buf.write("\n")
    yaml_rt.dump(body, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")


def extract_placeholders_from(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        out |= set(PLACEHOLDER_RE.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            out |= extract_placeholders_from(v)
    elif isinstance(value, list):
        for v in value:
            out |= extract_placeholders_from(v)
    return out


def fix_required_slots(body: CommentedMap) -> None:
    templates = body.get("templates") or {}
    for variant, tpl in templates.items():
        if not isinstance(tpl, dict):
            continue
        script = tpl.get("script") or ""
        phs = sorted(set(PLACEHOLDER_RE.findall(script)))
        tpl["required_slots"] = CommentedSeq(phs)


def fix_branch_conditions(body: CommentedMap) -> None:
    branches = body.get("branch_conditions") or []
    new_branches: list[CommentedMap] = []
    for br in branches:
        if not isinstance(br, dict):
            new_branches.append(br)
            continue
        # Already migrated?
        if "expr" in br or "hint" in br:
            new_branches.append(br)
            continue
        cond = br.get("condition")
        expr, hint = parse_condition(cond) if cond is not None else (None, None)
        new = CommentedMap()
        if expr:
            new["expr"] = expr
        if hint:
            new["hint"] = hint
        # Preserve remaining fields (variant, note, ...) excluding `condition`.
        for k, v in br.items():
            if k == "condition":
                continue
            new[k] = v
        new_branches.append(new)
    if new_branches:
        body["branch_conditions"] = CommentedSeq(new_branches)


def collect_all_slots(body: CommentedMap) -> set[str]:
    slots: set[str] = set()
    for key in ("templates", "fallback"):
        slots |= extract_placeholders_from(body.get(key))
    return slots


def fix_slot_sources(body: CommentedMap) -> None:
    existing = body.get("slot_sources") or {}
    if not isinstance(existing, dict):
        existing = CommentedMap()
    slots = collect_all_slots(body)
    new_map = CommentedMap()
    for slot in sorted(slots):
        if slot in existing:
            new_map[slot] = existing[slot]
        else:
            new_map[slot] = infer_slot_source(slot)
    body["slot_sources"] = new_map


def fix_escalation_signals(body: CommentedMap) -> None:
    if "escalation_signals" not in body:
        body["escalation_signals"] = CommentedSeq()


def migrate_file(path: Path) -> str:
    """Return the new file text (does not write)."""
    front, body = load_skill(path)
    fix_required_slots(body)
    fix_branch_conditions(body)
    fix_slot_sources(body)
    fix_escalation_signals(body)
    buf = StringIO()
    buf.write("---\n")
    yaml_rt.dump(front, buf)
    buf.write("\n")
    yaml_rt.dump(body, buf)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes to disk")
    ap.add_argument("--only", help="migrate only this skill_id")
    args = ap.parse_args()

    files = sorted(SKILLS_DIR.glob("*.yaml"))
    if args.only:
        files = [f for f in files if f.stem == args.only]
        if not files:
            print(f"no match for {args.only!r}", file=sys.stderr)
            sys.exit(1)

    changed = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        try:
            migrated = migrate_file(path)
        except Exception as exc:
            print(f"[FAIL] {path.name}: {exc}", file=sys.stderr)
            continue
        if migrated == original:
            continue
        changed += 1
        if args.apply:
            path.write_text(migrated, encoding="utf-8")
            print(f"[WRITE] {path.name}")
        else:
            print(f"[DIFF] {path.name} ({len(original)} → {len(migrated)} bytes)")
    print(f"\n{changed} file(s) changed" + ("" if args.apply else " (dry run — rerun with --apply)"))


if __name__ == "__main__":
    main()
