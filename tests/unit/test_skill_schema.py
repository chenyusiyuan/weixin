"""Schema tests for skills/*.yaml — runs the validator in strict mode."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_skills import (  # noqa: E402
    Report,
    REGISTRY_PATH,
    SKILLS_DIR,
    build_registry_index,
    load_yaml,
    validate_skill,
)
import json  # noqa: E402


def _collect_report() -> Report:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = json.load(f)
    reg_index = build_registry_index(registry)
    report = Report()

    yaml_files = sorted(SKILLS_DIR.glob("*.yaml"))
    yaml_ids = {p.stem for p in yaml_files}
    for sid in reg_index:
        if sid not in yaml_ids:
            report.add("E", sid, "<file>", "registry entry has no YAML definition")

    for path in yaml_files:
        sid = path.stem
        try:
            raw = load_yaml(path)
        except Exception as exc:
            report.add("E", sid, "<parse>", f"YAML parse error: {exc}")
            continue
        report.files_scanned += 1
        validate_skill(sid, raw, reg_index, report)
    return report


def test_no_schema_errors():
    report = _collect_report()
    assert report.files_scanned > 0, "no YAML files scanned"
    if report.errors:
        msg = "\n".join(
            f"[{i.severity}] {i.skill_id} {i.path}: {i.message}" for i in report.errors
        )
        raise AssertionError(f"{len(report.errors)} schema error(s):\n{msg}")


def test_no_schema_warnings():
    report = _collect_report()
    if report.warnings:
        msg = "\n".join(
            f"[{i.severity}] {i.skill_id} {i.path}: {i.message}" for i in report.warnings
        )
        raise AssertionError(f"{len(report.warnings)} schema warning(s):\n{msg}")


def test_all_registered_skills_load():
    """Ensure SkillLoader can parse every registered skill without exception."""
    from fin_copilot.skills.loader import SkillLoader

    loader = SkillLoader(
        str(SKILLS_DIR),
        str(REGISTRY_PATH),
        validate_on_load=True,
        strict=True,
    )
    ids = loader.get_all_skill_ids()
    assert len(ids) >= 50, f"expected at least 50 skills, got {len(ids)}"
    for sid in ids:
        s = loader.get_skill(sid)
        assert s is not None, f"failed to load {sid}"
        assert s.skill_id == sid
