"""Skill-level cosine index for routing priors.

This module builds one embedding centroid per Skill from its operational text
(name, description, intent hierarchy, keywords, and examples). At evaluation
time, Exp2 can reuse the same query embedding used by L1 domain matching and
score it against all Skill centroids. The resulting scores are weak priors for
candidate expansion and LLM routing, not a replacement for SkillRouter.
"""

from __future__ import annotations

import logging
import math
from typing import Iterable

import httpx

from fin_copilot.models.skill import SkillDefinition
from fin_copilot.skills.loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillEmbeddingIndex:
    """Cosine scorer over Skill definition centroids."""

    def __init__(
        self,
        skill_loader: SkillLoader,
        api_url: str = "http://localhost:11434/api/embed",
        model: str = "bge-m3",
        timeout: float = 30.0,
    ) -> None:
        self._loader = skill_loader
        self._api_url = api_url
        self._model = model
        self._client = httpx.Client(timeout=timeout)
        self._centroids: dict[str, list[float]] = {}
        self._build_index()

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.post(
            self._api_url,
            json={"model": self._model, "input": texts},
        )
        resp.raise_for_status()
        return resp.json().get("embeddings") or []

    @staticmethod
    def _normalise(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    @staticmethod
    def _skill_text(skill: SkillDefinition) -> str:
        hierarchy = " / ".join(
            v for _, v in sorted(skill.intent_hierarchy.items()) if v
        )
        keywords = "、".join(skill.triggers.keywords or [])
        examples = "；".join(skill.triggers.examples or [])
        template_names = "、".join(skill.templates.keys())
        tools = "、".join(skill.get_required_tools())
        return "\n".join(
            part for part in [
                f"skill_id: {skill.skill_id}",
                f"名称: {skill.name}",
                f"领域: {skill.domain}",
                f"意图层级: {hierarchy}",
                f"描述: {skill.description}",
                f"触发关键词: {keywords}",
                f"正例: {examples}",
                f"模板变体: {template_names}",
                f"所需工具: {tools}",
            ]
            if part and not part.endswith(": ")
        )

    def _build_index(self) -> None:
        skill_ids = self._loader.get_all_skill_ids()
        skills: list[SkillDefinition] = []
        texts: list[str] = []
        for skill_id in skill_ids:
            skill = self._loader.get_skill(skill_id)
            if skill is None:
                continue
            text = self._skill_text(skill)
            if not text.strip():
                continue
            skills.append(skill)
            texts.append(text)

        if not texts:
            logger.warning("no skill texts available for skill embedding index")
            return

        vectors = self._embed_batch(texts)
        if len(vectors) != len(skills):
            logger.warning(
                "skill embedding count mismatch: skills=%d embeddings=%d",
                len(skills), len(vectors),
            )

        for skill, vec in zip(skills, vectors):
            if vec:
                self._centroids[skill.skill_id] = self._normalise(vec)
        logger.info("built skill embedding centroids: %d", len(self._centroids))

    def rank_vector(
        self,
        query_vector: list[float],
        *,
        k: int = 8,
        allowed_skills: Iterable[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return top-k skill ids scored against a pre-computed query vector."""
        if not query_vector or k <= 0:
            return []
        allowed = set(allowed_skills) if allowed_skills is not None else None
        scored: list[tuple[str, float]] = []
        for skill_id, centroid in self._centroids.items():
            if allowed is not None and skill_id not in allowed:
                continue
            scored.append((skill_id, self._cosine(query_vector, centroid)))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
