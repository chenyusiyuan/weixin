"""Embedding-based L1 domain classifier using bge-m3 via Ollama.

Replaces rule-based DomainClassifier for scenarios where keyword matching
falls short (e.g. customer says "贷款逾期" which hits both `贷款` and
`还款` keywords but should map to `逾期`).

How it works:
  1. Load anchor examples per domain from scripts/references/domain_anchors.json.
  2. Embed each anchor with bge-m3; take the per-domain mean vector
     (centroid).
  3. At inference time: embed the query, compute cosine similarity against
     every centroid, return the argmax domain.

This classifier is stand-alone and does NOT touch the existing
DomainClassifier. Drop-in compatible via `.classify(query, state)`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from fin_copilot.models.conversation import ConversationState

logger = logging.getLogger(__name__)

ANCHORS_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "references" / "domain_anchors.json"


class EmbeddingDomainClassifier:
    """bge-m3 centroid-based L1 domain classifier."""

    def __init__(
        self,
        api_url: str = "http://localhost:11434/api/embed",
        model: str = "bge-m3",
        anchors_path: str | Path = ANCHORS_PATH,
        timeout: float = 30.0,
    ) -> None:
        self._api_url = api_url
        self._model = model
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._centroids: dict[str, list[float]] = {}
        self._load_and_build(anchors_path)

    def _embed_one(self, text: str) -> list[float]:
        resp = self._client.post(
            self._api_url,
            json={"model": self._model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings") or []
        if not embeddings:
            raise RuntimeError(f"empty embedding for {text!r}: {data}")
        return embeddings[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama's /api/embed accepts a list as input
        resp = self._client.post(
            self._api_url,
            json={"model": self._model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embeddings") or []

    def _load_and_build(self, anchors_path: str | Path) -> None:
        with open(anchors_path, encoding="utf-8") as f:
            cfg = json.load(f)
        anchors: dict[str, list[str]] = cfg["anchors"]
        for domain, examples in anchors.items():
            if not examples:
                continue
            vectors = self._embed_batch(examples)
            if not vectors:
                logger.warning("no embeddings returned for domain %s", domain)
                continue
            # Compute mean
            dim = len(vectors[0])
            centroid = [0.0] * dim
            for vec in vectors:
                for i, v in enumerate(vec):
                    centroid[i] += v
            n = len(vectors)
            centroid = [x / n for x in centroid]
            # L2-normalise
            norm = sum(x * x for x in centroid) ** 0.5 or 1.0
            centroid = [x / norm for x in centroid]
            self._centroids[domain] = centroid
        logger.info("built %d domain centroids", len(self._centroids))

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        # Assumes both unit-normalised
        return sum(x * y for x, y in zip(a, b))

    @staticmethod
    def _normalise(vec: list[float]) -> list[float]:
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    def classify(
        self,
        query: str,
        state: ConversationState | None = None,
    ) -> str:
        """Return the best-matching domain for `query`."""
        return self.classify_topk(query, state, k=1)[0][0]

    def embed_query(self, query: str) -> list[float]:
        """Return a unit-normalised embedding for ``query``."""
        return self._normalise(self._embed_one(query))

    def classify_topk(
        self,
        query: str,
        state: ConversationState | None = None,
        k: int = 3,
    ) -> list[tuple[str, float]]:
        """Return the top-k domains with their cosine similarity scores."""
        if not query.strip():
            # Fallback to prior domain
            fallback = "还款"
            if state is not None and state.intent.domain:
                fallback = state.intent.domain
            return [(fallback, 0.0)]
        return self.classify_topk_from_vector(
            self.embed_query(query),
            state,
            k=k,
        )

    def classify_topk_from_vector(
        self,
        query_vector: list[float],
        state: ConversationState | None = None,
        k: int = 3,
    ) -> list[tuple[str, float]]:
        """Return top-k domains for a pre-computed unit-normalised query vector."""
        if not query_vector:
            fallback = "还款"
            if state is not None and state.intent.domain:
                fallback = state.intent.domain
            return [(fallback, 0.0)]
        scored = [(d, self._cosine(query_vector, c)) for d, c in self._centroids.items()]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
