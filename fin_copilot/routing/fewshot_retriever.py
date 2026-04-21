"""Few-shot retrieval over the 288-record corpus built from cleaned-data xlsx.

Used by SkillRouter to inject Top-K similar (query, skill_id) examples into
the LLM prompt before classification. This grounds the LLM's decision in
real business language rather than the short `examples` from skill YAMLs.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CORPUS_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "references" / "fewshot_corpus.json"


class FewShotRetriever:
    """Cosine-similarity retrieval over embedded (query, skill_id) corpus."""

    def __init__(
        self,
        corpus_path: str | Path = CORPUS_PATH,
        embed_url: str = "http://localhost:11434/api/embed",
        embed_model: str = "bge-m3",
        timeout: float = 30.0,
    ) -> None:
        self._embed_url = embed_url
        self._embed_model = embed_model
        self._client = httpx.Client(timeout=timeout)
        self._corpus = self._load(corpus_path)

    @staticmethod
    def _load(path: str | Path) -> list[dict]:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("fewshot corpus not found: %s", path)
            return []
        # pre-normalise embeddings
        for r in data:
            vec = r.get("embedding") or []
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            r["embedding"] = [x / norm for x in vec]
        logger.info("loaded fewshot corpus: %d records", len(data))
        return data

    def _embed(self, text: str) -> list[float]:
        resp = self._client.post(
            self._embed_url,
            json={"model": self._embed_model, "input": text},
        )
        resp.raise_for_status()
        vec = (resp.json().get("embeddings") or [[]])[0]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def retrieve(
        self,
        query: str,
        k: int = 5,
        allowed_skills: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return Top-K (most similar) records, optionally filtered by skill_id."""
        if not self._corpus or not query.strip():
            return []
        q_vec = self._embed(query)
        scored: list[tuple[float, dict]] = []
        for rec in self._corpus:
            if allowed_skills is not None and rec["skill_id"] not in allowed_skills:
                continue
            sim = sum(a * b for a, b in zip(q_vec, rec["embedding"]))
            scored.append((sim, rec))
        scored.sort(key=lambda x: -x[0])
        return [
            {"skill_id": rec["skill_id"], "query": rec["query"], "similarity": sim}
            for sim, rec in scored[:k]
        ]
