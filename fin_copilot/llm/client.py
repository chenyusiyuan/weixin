"""Async LLM client — OpenAI-compatible API (Ollama)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from fin_copilot.llm.profiles import LLMProfile, get_active_llm_profile

logger = logging.getLogger(__name__)


class LLMClient:
    """Async client for OpenAI-compatible LLM endpoints (e.g. Ollama)."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "ollama",
        model: str = "qwen2.5:7b",
        timeout: float = 30.0,
        profiles: list[LLMProfile] | None = None,
        default_profile_id: str = "default",
    ) -> None:
        default_profile = LLMProfile(
            id=default_profile_id or "default",
            api_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            is_default=True,
        )
        self._profiles = {
            profile.id: profile
            for profile in (profiles or [default_profile])
        }
        if default_profile.id not in self._profiles:
            self._profiles[default_profile.id] = default_profile
        self._default_profile_id = default_profile.id
        self.model = model
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._client_signatures: dict[str, tuple[str, str, float]] = {}
        self._last_calls: dict[str, dict[str, Any]] = {}
        for profile in self._profiles.values():
            self._clients[profile.id] = self._build_client(profile)
            self._client_signatures[profile.id] = self._profile_signature(profile)

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
        profile = self._current_profile()
        payload: dict[str, Any] = {
            "model": profile.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        client = await self._client_for_profile(profile)
        for attempt in range(2):
            try:
                resp = await client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                self._record_call(
                    profile,
                    status="ok",
                    status_code=getattr(resp, "status_code", None),
                )
                return data["choices"][0]["message"]["content"]
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == 0:
                    logger.warning("LLM call failed (attempt %d), retrying: %s", attempt + 1, exc)
                    continue
                self._record_call(profile, status="error", error=self._error_text(exc))
                logger.error("LLM call failed after retry: %s", exc)
                return ""
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                self._record_call(
                    profile,
                    status="error",
                    status_code=status_code,
                    error=self._error_text(exc),
                )
                logger.error("LLM call HTTP error: %s", exc)
                return ""
            except Exception as exc:
                self._record_call(profile, status="error", error=self._error_text(exc))
                logger.error("LLM call unexpected error: %s", exc)
                return ""
        return ""

    async def close(self) -> None:
        for client in self._clients.values():
            await client.aclose()

    @staticmethod
    def _build_client(profile: LLMProfile) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=profile.api_url,
            headers={"Authorization": f"Bearer {profile.api_key}"},
            timeout=profile.timeout,
        )

    def _current_profile(self) -> LLMProfile:
        active = get_active_llm_profile()
        if active is not None:
            return active
        return self._profiles[self._default_profile_id]

    async def _client_for_profile(self, profile: LLMProfile) -> httpx.AsyncClient:
        client = self._clients.get(profile.id)
        signature = self._profile_signature(profile)
        known_profile = self._profiles.get(profile.id)
        known_signature = (
            self._profile_signature(known_profile) if known_profile is not None else None
        )
        client_signature = self._client_signatures.get(profile.id) or known_signature
        if client is not None and client_signature == signature:
            self._client_signatures[profile.id] = signature
            self._profiles[profile.id] = profile
            return client

        if client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                logger.warning("failed to close stale LLM client for %s: %s", profile.id, exc)
        client = self._build_client(profile)
        self._clients[profile.id] = client
        self._client_signatures[profile.id] = signature
        self._profiles[profile.id] = profile
        return client

    def last_call_status(self, profile_id: str) -> dict[str, Any]:
        return dict(self._last_calls.get(profile_id) or {
            "status": "not_called",
            "error": "",
            "status_code": None,
            "updated_at": "",
        })

    @staticmethod
    def _profile_signature(profile: LLMProfile) -> tuple[str, str, float]:
        return (profile.api_url, profile.api_key, float(profile.timeout))

    def _record_call(
        self,
        profile: LLMProfile,
        *,
        status: str,
        status_code: int | None = None,
        error: str = "",
    ) -> None:
        self._last_calls[profile.id] = {
            "status": status,
            "error": error,
            "status_code": status_code,
            "updated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }

    @staticmethod
    def _error_text(exc: Exception) -> str:
        text = str(exc).strip()
        if not text:
            text = exc.__class__.__name__
        return text[:500]
