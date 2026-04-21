"""Post-generation compliance checker — 6-layer rule-based checking."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.skill import SkillDefinition

logger = logging.getLogger(__name__)


class ComplianceResult(BaseModel):
    passed: bool = True
    corrected_answer: str = ""
    issues: list[dict[str, Any]] = Field(default_factory=list)
    need_handoff: bool = False


class RuleComplianceChecker:
    """Six-layer post-generation compliance checker.

    Layers:
      1. Global forbidden words (with exclude_patterns)
      2. Skill-level forbidden expressions
      3. Ultra vires check (减免/免息 requires disclaimer)
      4. Long-tail severity (ban operation promises, force suffix)
      5. PII leak detection (ID, phone, bank card)
      6. Required disclaimer auto-append
    """

    def __init__(
        self,
        forbidden_words_path: str,
        key_rules_path: str,
        longtail_constraints_path: str,
    ) -> None:
        self._forbidden_words = self._load_json(forbidden_words_path)
        self._key_rules = self._load_json(key_rules_path)
        self._longtail_constraints = self._load_json(longtail_constraints_path)

    @staticmethod
    def _load_json(path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            logger.warning("compliance file not found: %s", path)
            return {}
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def check(
        self,
        answer: str,
        state: ConversationState,
        skill: Optional[SkillDefinition] = None,
        is_longtail: bool = False,
    ) -> ComplianceResult:
        issues: list[dict[str, Any]] = []
        corrected = answer
        need_handoff = False

        # Layer 1: Global forbidden words
        corrected, layer1_issues = self._check_forbidden_words(corrected)
        issues.extend(layer1_issues)

        # Layer 2: Skill-level forbidden expressions
        if skill is not None:
            corrected, layer2_issues = self._check_skill_forbidden(corrected, skill)
            issues.extend(layer2_issues)

        # Layer 3: Ultra vires check
        corrected, layer3_issues = self._check_ultra_vires(corrected)
        issues.extend(layer3_issues)

        # Layer 4: Long-tail severity
        if is_longtail:
            corrected, layer4_issues = self._check_longtail(corrected)
            issues.extend(layer4_issues)

        # Layer 5: PII leak detection
        layer5_issues = self._check_pii(corrected)
        issues.extend(layer5_issues)
        if layer5_issues:
            need_handoff = True

        # Layer 6: Required disclaimer auto-append
        if skill is not None:
            corrected = self._ensure_disclaimer(corrected, skill)

        passed = not any(i.get("severity") == "critical" for i in issues)

        return ComplianceResult(
            passed=passed,
            corrected_answer=corrected,
            issues=issues,
            need_handoff=need_handoff,
        )

    # ------------------------------------------------------------------
    # Layer 1: Global forbidden words
    # ------------------------------------------------------------------

    def _check_forbidden_words(
        self, answer: str
    ) -> tuple[str, list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []
        fw_list = self._forbidden_words.get("forbidden_words", [])

        for entry in fw_list:
            word = entry.get("word", "")
            if not word:
                continue
            exclude_patterns = entry.get("exclude_patterns", [])

            if word in answer:
                # Check exclusions
                excluded = False
                for exc in exclude_patterns:
                    if exc in answer:
                        excluded = True
                        break
                if not excluded:
                    issues.append({
                        "type": "forbidden_word",
                        "word": word,
                        "category": entry.get("category", ""),
                        "severity": "critical",
                        "note": entry.get("note", ""),
                    })

        return answer, issues

    # ------------------------------------------------------------------
    # Layer 2: Skill-level forbidden expressions
    # ------------------------------------------------------------------

    def _check_skill_forbidden(
        self, answer: str, skill: SkillDefinition
    ) -> tuple[str, list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []
        for expr in skill.compliance.forbidden_expressions:
            if expr in answer:
                issues.append({
                    "type": "skill_forbidden",
                    "word": expr,
                    "severity": "critical",
                    "skill_id": skill.skill_id,
                })
        return answer, issues

    # ------------------------------------------------------------------
    # Layer 3: Ultra vires check
    # ------------------------------------------------------------------

    def _check_ultra_vires(
        self, answer: str
    ) -> tuple[str, list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []
        # Check if answer mentions 减免/免息/免除 without disclaimer
        ultra_vires_keywords = ["减免", "免息", "免除费用", "退还"]
        has_ultra_vires = any(kw in answer for kw in ultra_vires_keywords)

        if has_ultra_vires:
            has_disclaimer = "具体以" in answer and "为准" in answer
            if not has_disclaimer:
                issues.append({
                    "type": "ultra_vires",
                    "severity": "high",
                    "detail": "涉及减免/免息但缺少免责声明",
                })
                answer += "\n（具体方案以实际审批结果为准）"

        return answer, issues

    # ------------------------------------------------------------------
    # Layer 4: Long-tail severity
    # ------------------------------------------------------------------

    def _check_longtail(
        self, answer: str
    ) -> tuple[str, list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []

        # Ban operation promises
        operation_phrases = [
            "我可以帮你操作", "我帮你操作", "我给你操作",
            "我来帮你办", "我直接给你", "我帮你处理",
        ]
        for phrase in operation_phrases:
            if phrase in answer:
                issues.append({
                    "type": "longtail_operation_promise",
                    "word": phrase,
                    "severity": "critical",
                })

        # Force disclaimer suffix
        required_suffix = "以上信息仅供参考，具体以业务确认为准"
        if required_suffix not in answer:
            answer = answer.rstrip() + "\n" + required_suffix

        return answer, issues

    # ------------------------------------------------------------------
    # Layer 5: PII leak detection
    # ------------------------------------------------------------------

    def _check_pii(self, answer: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        pii_patterns = self._forbidden_words.get("pii_patterns", [])

        for pii in pii_patterns:
            regex = pii.get("regex", "")
            if not regex:
                continue
            if re.search(regex, answer):
                issues.append({
                    "type": "pii_leak",
                    "pattern_name": pii.get("name", ""),
                    "severity": "critical",
                    "note": pii.get("note", ""),
                })

        return issues

    # ------------------------------------------------------------------
    # Layer 6: Required disclaimer auto-append
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_disclaimer(answer: str, skill: SkillDefinition) -> str:
        disclaimer = skill.compliance.required_disclaimer
        if disclaimer and disclaimer not in answer:
            answer = answer.rstrip() + "\n" + disclaimer
        return answer
