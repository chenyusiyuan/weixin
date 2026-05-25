"""Tests for selectable LLM profiles."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from fin_copilot.llm.client import LLMClient
from fin_copilot.llm.profiles import (
    LLMProfile,
    load_llm_profiles,
    reset_active_llm_profile,
    select_llm_profile,
    set_active_llm_profile,
)


class _Settings:
    LLM_API_URL = "http://default.local/v1"
    LLM_API_KEY = "default-key"
    LLM_MODEL = "default-model"
    LLM_PROFILES_PATH = "config/llm_profiles.json"
    LLM_TIMEOUT = 30.0

    def __init__(self, root: Path | None = None) -> None:
        self.root = root

    def resolve_path(self, relative: str) -> Path:
        return (self.root or Path.cwd()) / relative


def test_load_llm_profiles_from_local_file(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "llm_profiles.json").write_text(
        json.dumps(
            {
                "default_profile_id": "alt",
                "profiles": [
                    {
                        "id": "alt",
                        "api_url": "http://alt.local/v1",
                        "api_key": "alt-key",
                        "model": "alt-model",
                        "timeout": 12,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    profiles, default_id = load_llm_profiles(_Settings(tmp_path))
    by_id = {profile.id: profile for profile in profiles}

    assert default_id == "alt"
    assert by_id["alt"].api_key == "alt-key"
    assert by_id["alt"].timeout == 12
    assert by_id["alt"].is_default is True


def test_load_llm_profiles_falls_back_to_legacy_env(tmp_path: Path):
    profiles, default_id = load_llm_profiles(_Settings(tmp_path))

    assert default_id == "default"
    assert profiles[0].model == "default-model"


def test_load_llm_profiles_refreshes_env_api_key(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "llm_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "alt",
                        "api_url": "http://alt.local/v1",
                        "model": "alt-model",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    env_path = tmp_path / ".env"
    env_path.write_text("LLM_API_KEY=first-key\n", encoding="utf-8")
    profiles, _default_id = load_llm_profiles(_Settings(tmp_path))
    assert profiles[0].api_key == "first-key"

    env_path.write_text("LLM_API_KEY=second-key\n", encoding="utf-8")
    profiles, _default_id = load_llm_profiles(_Settings(tmp_path))
    assert profiles[0].api_key == "second-key"


def test_select_llm_profile_by_id_or_model_with_timeout_override(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "llm_profiles.json").write_text(
        json.dumps(
            {
                "default_profile_id": "fast",
                "profiles": [
                    {
                        "id": "fast",
                        "api_url": "http://fast.local/v1",
                        "api_key": "fast-key",
                        "model": "fast-model",
                        "timeout": 12,
                    },
                    {
                        "id": "slow",
                        "api_url": "http://slow.local/v1",
                        "api_key": "slow-key",
                        "model": "slow-model",
                        "timeout": 30,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    selected_by_id = select_llm_profile("slow", _Settings(tmp_path), timeout=90)
    selected_by_model = select_llm_profile("fast-model", _Settings(tmp_path))
    default = select_llm_profile(None, _Settings(tmp_path))

    assert selected_by_id.id == "slow"
    assert selected_by_id.model == "slow-model"
    assert selected_by_id.timeout == 90
    assert selected_by_model.id == "fast"
    assert default.id == "fast"


def test_select_llm_profile_unknown_model_fails_fast(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "llm_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "known",
                        "api_url": "http://known.local/v1",
                        "model": "known-model",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        select_llm_profile("missing", _Settings(tmp_path))
    except ValueError as exc:
        assert "unknown LLM profile/model" in str(exc)
        assert "known(known-model)" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("select_llm_profile should reject unknown models")


def test_llm_client_uses_active_profile():
    default = LLMProfile(
        id="default",
        api_url="http://default.local/v1",
        api_key="default-key",
        model="default-model",
        timeout=30.0,
    )
    alt = LLMProfile(
        id="alt",
        api_url="http://alt.local/v1",
        api_key="alt-key",
        model="alt-model",
        timeout=30.0,
    )
    client = LLMClient(
        base_url=default.api_url,
        api_key=default.api_key,
        model=default.model,
        profiles=[default, alt],
        default_profile_id="default",
    )

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class _FakeClient:
        def __init__(self):
            self.payloads = []

        async def post(self, _path, json):
            self.payloads.append(json)
            return _Response()

        async def aclose(self):
            return None

    fake_default = _FakeClient()
    fake_alt = _FakeClient()
    client._clients = {"default": fake_default, "alt": fake_alt}

    async def _run():
        token = set_active_llm_profile(alt)
        try:
            return await client.chat_completion([{"role": "user", "content": "hi"}])
        finally:
            reset_active_llm_profile(token)

    assert asyncio.run(_run()) == "ok"
    assert fake_default.payloads == []
    assert fake_alt.payloads[0]["model"] == "alt-model"


def test_llm_client_rebuilds_stale_profile_client(monkeypatch):
    old = LLMProfile(
        id="alt",
        api_url="http://alt.local/v1",
        api_key="old-key",
        model="alt-model",
        timeout=30.0,
    )
    new = LLMProfile(
        id="alt",
        api_url="http://alt.local/v1",
        api_key="new-key",
        model="alt-model",
        timeout=30.0,
    )

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class _FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.payloads = []
            self.closed = False

        async def post(self, _path, json):
            self.payloads.append(json)
            return _Response()

        async def aclose(self):
            self.closed = True

    built_clients = []

    def _build(profile):
        client = _FakeClient(profile.api_key)
        built_clients.append(client)
        return client

    monkeypatch.setattr(LLMClient, "_build_client", staticmethod(_build))
    client = LLMClient(
        base_url=old.api_url,
        api_key=old.api_key,
        model=old.model,
        profiles=[old],
        default_profile_id="alt",
    )

    async def _run():
        token = set_active_llm_profile(new)
        try:
            return await client.chat_completion([{"role": "user", "content": "hi"}])
        finally:
            reset_active_llm_profile(token)

    assert asyncio.run(_run()) == "ok"
    assert built_clients[0].api_key == "old-key"
    assert built_clients[0].closed is True
    assert built_clients[-1].api_key == "new-key"
    assert built_clients[-1].payloads[0]["model"] == "alt-model"


def test_llm_client_records_http_error_status():
    profile = LLMProfile(
        id="alt",
        api_url="http://alt.local/v1",
        api_key="bad-key",
        model="alt-model",
        timeout=30.0,
    )
    client = LLMClient(
        base_url=profile.api_url,
        api_key=profile.api_key,
        model=profile.model,
        profiles=[profile],
        default_profile_id="alt",
    )

    class _FakeClient:
        async def post(self, _path, json):
            request = httpx.Request("POST", "http://alt.local/v1/chat/completions")
            return httpx.Response(401, request=request)

        async def aclose(self):
            return None

    client._clients = {"alt": _FakeClient()}

    assert asyncio.run(client.chat_completion([{"role": "user", "content": "hi"}])) == ""
    last_call = client.last_call_status("alt")
    assert last_call["status"] == "error"
    assert last_call["status_code"] == 401
