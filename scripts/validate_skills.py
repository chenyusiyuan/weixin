"""Skill YAML validator.

Scans `skills/definitions/*.yaml` against `skills/registry.json` and
`tools/registry.py`, reporting structural and consistency errors.

Usage:
    python scripts/validate_skills.py           # human-readable report
    python scripts/validate_skills.py --strict  # exit 1 on any error
    python scripts/validate_skills.py --json    # machine-readable

Checks (severity):
  [E] ERROR    — schema violation (missing required field, unknown tool, ...)
  [W] WARNING  — consistency gap (placeholder not in required_slots, ...)
  [I] INFO     — style/minor (hint-only branch condition, ...)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills" / "definitions"
REGISTRY_PATH = ROOT / "skills" / "registry.json"

# Tools that exist in tools/registry.py — kept in sync manually with TOOL_REGISTRY_META.
KNOWN_TOOLS: set[str] = {
    "get_customer_profile",
    "get_bill_and_repayment_plan",
    "get_loan_service_info",
    "get_membership_service_info",
    "get_quota_service_info",
    "get_call_history",
    "get_sms_history",
    "get_stop_collection_history",
    "get_refund_history",
    "query_ticket",
    "submit_ticket",
}

VALID_ROUTE_MODES = {"direct_reply", "tool_only", "tool_rag"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_SLOT_SOURCE_PREFIXES = ("tool:", "system:", "llm:", "user_input:", "derived:")

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass
class Issue:
    severity: str  # "E" | "W" | "I"
    skill_id: str
    path: str
    message: str


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    files_scanned: int = 0

    def add(self, severity: str, skill_id: str, path: str, message: str) -> None:
        self.issues.append(Issue(severity, skill_id, path, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "E"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "W"]

    @property
    def infos(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "I"]


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        docs = [d for d in yaml.safe_load_all(f) if isinstance(d, dict)]
    merged: dict[str, Any] = {}
    for d in docs:
        merged.update(d)
    return merged


def extract_placeholders(text: str) -> set[str]:
    if not isinstance(text, str):
        return set()
    return set(PLACEHOLDER_RE.findall(text))


def validate_skill(
    skill_id: str,
    raw: dict[str, Any],
    registry_index: dict[str, dict[str, Any]],
    report: Report,
) -> None:
    # ---- Front-matter ------------------------------------------------------
    for key in ("skill_id", "name", "domain", "route_mode", "risk_level"):
        if not raw.get(key):
            report.add("E", skill_id, key, f"missing required front-matter field `{key}`")

    if raw.get("skill_id") != skill_id:
        report.add(
            "E", skill_id, "skill_id",
            f"skill_id field `{raw.get('skill_id')}` does not match filename `{skill_id}`",
        )

    route_mode = raw.get("route_mode")
    if route_mode and route_mode not in VALID_ROUTE_MODES:
        report.add("E", skill_id, "route_mode", f"invalid route_mode `{route_mode}` (expected one of {sorted(VALID_ROUTE_MODES)})")

    risk_level = raw.get("risk_level")
    if risk_level and risk_level not in VALID_RISK_LEVELS:
        report.add("E", skill_id, "risk_level", f"invalid risk_level `{risk_level}`")

    # ---- Registry cross-check ---------------------------------------------
    reg_entry = registry_index.get(skill_id)
    if reg_entry is None:
        report.add("E", skill_id, "<registry>", "skill not listed in registry.json")
    else:
        if reg_entry["domain"] != raw.get("domain"):
            report.add(
                "E", skill_id, "domain",
                f"domain mismatch: yaml=`{raw.get('domain')}` registry=`{reg_entry['domain']}`",
            )
        if reg_entry.get("route_mode") and reg_entry["route_mode"] != route_mode:
            report.add(
                "W", skill_id, "route_mode",
                f"route_mode mismatch vs registry (yaml=`{route_mode}` registry=`{reg_entry['route_mode']}`)",
            )

    # ---- Tools -------------------------------------------------------------
    tools = raw.get("tools") or {}
    declared_tools: set[str] = set()
    for bucket in ("required", "optional"):
        for t in tools.get(bucket, []) or []:
            declared_tools.add(t)
            if t not in KNOWN_TOOLS:
                report.add("E", skill_id, f"tools.{bucket}", f"unknown tool `{t}`")

    if route_mode == "direct_reply" and tools.get("required"):
        report.add("W", skill_id, "tools.required", "direct_reply route should not declare required tools")

    # ---- Templates & placeholders -----------------------------------------
    templates = raw.get("templates") or {}
    all_placeholders: set[str] = set()
    declared_slots: set[str] = set()
    for variant, tpl in templates.items():
        if not isinstance(tpl, dict):
            continue
        script = tpl.get("script") or ""
        ph = extract_placeholders(script)
        all_placeholders |= ph
        rs = set(tpl.get("required_slots") or [])
        declared_slots |= rs
        missing = ph - rs
        extra = rs - ph
        for slot in sorted(missing):
            report.add(
                "W", skill_id, f"templates.{variant}",
                f"placeholder `{{{slot}}}` in script not declared in required_slots",
            )
        for slot in sorted(extra):
            report.add(
                "I", skill_id, f"templates.{variant}",
                f"required_slots contains `{slot}` but not referenced in script",
            )

    # Fallback placeholders should also be covered
    fb = raw.get("fallback") or {}
    fb_text = fb.get("answer") or ""
    fb_ph = extract_placeholders(fb_text)
    all_placeholders |= fb_ph

    # ---- slot_sources ------------------------------------------------------
    slot_sources = raw.get("slot_sources") or {}
    if not isinstance(slot_sources, dict):
        report.add("E", skill_id, "slot_sources", "slot_sources must be a mapping")
        slot_sources = {}

    for slot in sorted(all_placeholders):
        if slot not in slot_sources:
            report.add("E", skill_id, "slot_sources", f"slot `{slot}` used in templates but missing from slot_sources")

    for slot, src in slot_sources.items():
        if not isinstance(src, str) or not src.startswith(VALID_SLOT_SOURCE_PREFIXES):
            report.add(
                "E", skill_id, f"slot_sources.{slot}",
                f"invalid source `{src}` (must start with one of {VALID_SLOT_SOURCE_PREFIXES})",
            )
            continue
        if src.startswith("tool:"):
            ref = src[len("tool:"):]
            tool_name = ref.split(".", 1)[0]
            if tool_name not in KNOWN_TOOLS:
                report.add("E", skill_id, f"slot_sources.{slot}", f"unknown tool in source `{src}`")
            elif tool_name not in declared_tools:
                report.add(
                    "W", skill_id, f"slot_sources.{slot}",
                    f"source references tool `{tool_name}` not in tools.required/optional",
                )
        if slot not in all_placeholders and slot not in declared_slots:
            report.add("I", skill_id, f"slot_sources.{slot}", "declared but unused")

    # ---- branch_conditions -------------------------------------------------
    branches = raw.get("branch_conditions") or []
    if not isinstance(branches, list):
        report.add("E", skill_id, "branch_conditions", "must be a list")
        branches = []
    variants_seen: set[str] = set()
    for idx, br in enumerate(branches):
        if not isinstance(br, dict):
            report.add("E", skill_id, f"branch_conditions[{idx}]", "entry must be a mapping")
            continue
        has_expr = "expr" in br
        has_hint = "hint" in br
        legacy_condition = "condition" in br
        if not (has_expr or has_hint):
            if legacy_condition:
                report.add(
                    "E", skill_id, f"branch_conditions[{idx}]",
                    "legacy `condition` field — migrate to `expr` (machine-evaluable) and/or `hint` (LLM-readable)",
                )
            else:
                report.add("E", skill_id, f"branch_conditions[{idx}]", "must declare `expr` and/or `hint`")
        if has_expr and not isinstance(br["expr"], str):
            report.add("E", skill_id, f"branch_conditions[{idx}].expr", "must be a string")
        if has_hint and not isinstance(br["hint"], str):
            report.add("E", skill_id, f"branch_conditions[{idx}].hint", "must be a string")
        variant = br.get("variant")
        if not variant:
            report.add("W", skill_id, f"branch_conditions[{idx}]", "missing `variant` label")
        elif variant in variants_seen:
            report.add("W", skill_id, f"branch_conditions[{idx}]", f"duplicate variant `{variant}`")
        else:
            variants_seen.add(variant)
        if has_hint and not has_expr:
            report.add("I", skill_id, f"branch_conditions[{idx}]", "hint-only branch (LLM interpretation)")

    # ---- Compliance --------------------------------------------------------
    compliance = raw.get("compliance") or {}
    if not compliance.get("forbidden_expressions"):
        report.add("W", skill_id, "compliance.forbidden_expressions", "no forbidden expressions declared")
    if not compliance.get("required_disclaimer"):
        report.add("I", skill_id, "compliance.required_disclaimer", "no required disclaimer declared")

    # ---- Escalation & Fallback --------------------------------------------
    if not raw.get("escalation"):
        report.add("I", skill_id, "escalation", "no escalation triggers declared")
    if not fb or not fb.get("answer"):
        report.add("W", skill_id, "fallback.answer", "missing fallback answer")

    # ---- escalation_signals (Chain A pre-match keywords) ------------------
    signals = raw.get("escalation_signals")
    if signals is not None:
        if not isinstance(signals, list):
            report.add("E", skill_id, "escalation_signals", "must be a list of strings")
        else:
            for idx, s in enumerate(signals):
                if not isinstance(s, str) or not s.strip():
                    report.add("E", skill_id, f"escalation_signals[{idx}]", "non-empty string required")

    # ---- priority (disambiguates overlapping skills) ----------------------
    pri = raw.get("priority")
    if pri is not None and not isinstance(pri, int):
        report.add("E", skill_id, "priority", "must be an integer (higher wins)")


def build_registry_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for domain, info in registry.get("domains", {}).items():
        for s in info.get("skills", []):
            sid = s["skill_id"]
            index[sid] = {"domain": domain, "route_mode": s.get("route_mode")}
    return index


def run(strict: bool, as_json: bool) -> int:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    registry_index = build_registry_index(registry)

    report = Report()
    yaml_files = sorted(SKILLS_DIR.glob("*.yaml"))
    yaml_ids = {p.stem for p in yaml_files}

    # Registry-only skills (in registry but missing YAML)
    for sid in registry_index:
        if sid not in yaml_ids:
            report.add("E", sid, "<file>", "registry entry has no YAML definition")

    for path in yaml_files:
        skill_id = path.stem
        try:
            raw = load_yaml(path)
        except yaml.YAMLError as exc:
            report.add("E", skill_id, "<parse>", f"YAML parse error: {exc}")
            continue
        report.files_scanned += 1
        validate_skill(skill_id, raw, registry_index, report)

    if as_json:
        print(json.dumps(
            {
                "files_scanned": report.files_scanned,
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "infos": len(report.infos),
                "issues": [i.__dict__ for i in report.issues],
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(f"Scanned {report.files_scanned} skill files")
        print(f"  errors:   {len(report.errors)}")
        print(f"  warnings: {len(report.warnings)}")
        print(f"  infos:    {len(report.infos)}")
        print()
        by_skill: dict[str, list[Issue]] = {}
        for i in report.issues:
            by_skill.setdefault(i.skill_id, []).append(i)
        for sid in sorted(by_skill):
            print(f"── {sid}")
            for i in by_skill[sid]:
                print(f"  [{i.severity}] {i.path}: {i.message}")
            print()

    if strict and report.errors:
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 on any error")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args()
    sys.exit(run(args.strict, args.json))


if __name__ == "__main__":
    main()
