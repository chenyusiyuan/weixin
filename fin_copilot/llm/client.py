"""Async LLM client — OpenAI-compatible API (Ollama)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Async client for OpenAI-compatible LLM endpoints (e.g. Ollama)."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "ollama",
        model: str = "qwen2.5:7b",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        response_format: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send a chat completion request; return the assistant content string.

        On failure (timeout, connection error, bad JSON), retries once then
        returns an empty string so the caller can fall back gracefully.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        for attempt in range(2):
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == 0:
                    logger.warning("LLM call failed (attempt %d), retrying: %s", attempt + 1, exc)
                    continue
                logger.error("LLM call failed after retry: %s", exc)
                return ""
            except Exception as exc:
                logger.error("LLM call unexpected error: %s", exc)
                return ""
        return ""

    async def close(self) -> None:
        await self._client.aclose()
