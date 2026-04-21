"""Skill YAML loader with caching and domain-based retrieval."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from fin_copilot.models.skill import (
    SkillCompliance,
    SkillDefinition,
    SkillTemplate,
    SkillTriggers,
)

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads Skill definitions from YAML files indexed by registry.json."""

    def __init__(
        self,
        definitions_dir: str,
        registry_path: str,
        *,
        validate_on_load: bool = False,
        strict: bool = False,
    ) -> None:
        self._definitions_dir = Path(definitions_dir)
        self._registry = self._load_registry(registry_path)
        self._cache: dict[str, SkillDefinition] = {}
        self._domain_index: dict[str, list[str]] = self._build_domain_index()
        if validate_on_load:
            self._run_validator(strict=strict)

    def _run_validator(self, strict: bool) -> None:
        """Invoke scripts/validate_skills.py against the current skills directory.

        Warnings are logged; errors are raised in strict mode.
        """
        try:
            from scripts.validate_skills import (  # type: ignore
                Report,
                build_registry_index,
                load_yaml,
                validate_skill,
            )
        except Exception:
            logger.warning("skill validator unavailable — skipping validate_on_load")
            return

        report = Report()
        reg_index = build_registry_index(self._registry)
        for path in sorted(self._definitions_dir.glob("*.yaml")):
            try:
                raw = load_yaml(path)
            except Exception as exc:
                report.add("E", path.stem, "<parse>", f"YAML parse error: {exc}")
                continue
            report.files_scanned += 1
            validate_skill(path.stem, raw, reg_index, report)

        if report.errors:
            for i in report.errors[:20]:
                logger.error("[skill-validate] %s %s: %s", i.skill_id, i.path, i.message)
            if strict:
                raise RuntimeError(
                    f"skill validation failed: {len(report.errors)} error(s); first shown above"
                )
        if report.warnings:
            logger.warning("[skill-validate] %d warning(s)", len(report.warnings))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        if skill_id in self._cache:
            return self._cache[skill_id]

        path = self._definitions_dir / f"{skill_id}.yaml"
        if not path.exists():
            logger.warning("skill YAML not found: %s", path)
            return None

        try:
            with open(path, encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
            # YAML files use --- delimited front-matter (doc 0) + body (doc 1).
            # Merge all documents into a single dict.
            raw: dict[str, Any] = {}
            for doc in docs:
                if isinstance(doc, dict):
                    raw.update(doc)
            skill = self._parse_skill(raw)
            self._cache[skill_id] = skill
            return skill
        except Exception:
            logger.exception("failed to parse skill %s", skill_id)
            return None

    def get_skills_by_domain(self, domain: str) -> list[SkillDefinition]:
        skill_ids = self._domain_index.get(domain, [])
        result = []
        for sid in skill_ids:
            skill = self.get_skill(sid)
            if skill is not None:
                result.append(skill)
        return result

    def get_all_skill_ids(self) -> list[str]:
        ids: list[str] = []
        for sids in self._domain_index.values():
            ids.extend(sids)
        return ids

    def get_all_domains(self) -> list[str]:
        return list(self._domain_index.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_registry(path: str) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _build_domain_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for domain, info in self._registry.get("domains", {}).items():
            index[domain] = [s["skill_id"] for s in info.get("skills", [])]
        return index

    @staticmethod
    def _parse_skill(raw: dict[str, Any]) -> SkillDefinition:
        # Parse triggers
        triggers_raw = raw.get("triggers", {})
        triggers = SkillTriggers(**triggers_raw) if isinstance(triggers_raw, dict) else SkillTriggers()

        # Parse templates: variant_name -> SkillTemplate
        templates_raw = raw.get("templates", {})
        templates: dict[str, SkillTemplate] = {}
        for variant, tpl_data in templates_raw.items():
            if isinstance(tpl_data, dict):
                templates[variant] = SkillTemplate(**tpl_data)

        # Parse compliance
        compliance_raw = raw.get("compliance", {})
        compliance = SkillCompliance(**compliance_raw) if isinstance(compliance_raw, dict) else SkillCompliance()

        # Parse escalation — normalize to list of dicts
        escalation_raw = raw.get("escalation", [])
        escalation: list[dict[str, Any]] = []
        for item in escalation_raw:
            if isinstance(item, dict):
                escalation.append(item)
            elif isinstance(item, str):
                escalation.append({"trigger": item})

        return SkillDefinition(
            skill_id=raw.get("skill_id", ""),
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            domain=raw.get("domain", ""),
            intent_hierarchy=raw.get("intent_hierarchy", {}),
            route_mode=raw.get("route_mode", "tool_rag"),
            risk_level=raw.get("risk_level", "low"),
            triggers=triggers,
            tools=raw.get("tools", {}),
            templates=templates,
            branch_conditions=raw.get("branch_conditions", []),
            compliance=compliance,
            escalation=escalation,
            escalation_signals=raw.get("escalation_signals", []) or [],
            fallback=raw.get("fallback", {}),
            slot_sources=raw.get("slot_sources", {}) or {},
            priority=int(raw.get("priority", 0) or 0),
        )
