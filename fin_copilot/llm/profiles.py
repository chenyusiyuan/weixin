"""LLM profile loading and per-request selection."""

from __future__ import annotations

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class LLMProfile:
    id: str
    api_url: str
    api_key: str
    model: str
    timeout: float
    is_default: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "api_url": self.api_url,
            "model": self.model,
            "timeout": self.timeout,
            "is_default": self.is_default,
            "configured": bool(self.api_url and self.model),
        }


_active_profile: ContextVar[LLMProfile | None] = ContextVar(
    "active_llm_profile",
    default=None,
)


def set_active_llm_profile(profile: LLMProfile | None) -> Token[LLMProfile | None]:
    return _active_profile.set(profile)


def reset_active_llm_profile(token: Token[LLMProfile | None]) -> None:
    _active_profile.reset(token)


def get_active_llm_profile() -> LLMProfile | None:
    return _active_profile.get()


def load_llm_profiles(settings: Any) -> tuple[list[LLMProfile], str]:
    data = _read_profiles_file(settings)
    entries = _profile_entries(data)
    if not entries:
        entries = [_legacy_entry(settings)]

    profiles = [
        profile
        for entry in entries
        if (profile := _profile_from_entry(entry, settings)) is not None
    ]
    if not profiles:
        legacy_profile = _profile_from_entry(_legacy_entry(settings), settings)
        profiles = [legacy_profile] if legacy_profile is not None else []

    requested_default = str(data.get("default_profile_id") or profiles[0].id)
    profile_ids = {profile.id for profile in profiles}
    default_id = requested_default if requested_default in profile_ids else profiles[0].id
    profiles = [_replace_default(profile, profile.id == default_id) for profile in profiles]
    return profiles, default_id


def get_llm_profile(profile_id: str | None, settings: Any) -> LLMProfile:
    profiles, default_id = load_llm_profiles(settings)
    by_id = {profile.id: profile for profile in profiles}
    if profile_id and profile_id in by_id:
        return by_id[profile_id]
    return by_id[default_id]


def select_llm_profile(
    model_or_profile_id: str | None,
    settings: Any,
    *,
    timeout: float | None = None,
) -> LLMProfile:
    """Select a configured profile by profile id or model name.

    CLI tools intentionally call this strict selector so an unknown model name
    fails fast instead of silently falling back to the default profile.
    """
    profiles, default_id = load_llm_profiles(settings)
    if not profiles:
        raise ValueError("no LLM profiles configured")

    selector = (model_or_profile_id or "").strip()
    selected: LLMProfile | None = None
    if selector:
        selected = next((profile for profile in profiles if profile.id == selector), None)
        if selected is None:
            model_matches = [profile for profile in profiles if profile.model == selector]
            if len(model_matches) == 1:
                selected = model_matches[0]
            elif len(model_matches) > 1:
                matched_ids = ", ".join(profile.id for profile in model_matches)
                raise ValueError(
                    f"model {selector!r} matches multiple profiles: {matched_ids}; "
                    "pass a profile id"
                )
        if selected is None:
            available = ", ".join(
                f"{profile.id}({profile.model})"
                for profile in profiles
            )
            raise ValueError(
                f"unknown LLM profile/model {selector!r}; available: {available}"
            )
    else:
        by_id = {profile.id: profile for profile in profiles}
        selected = by_id[default_id]

    if timeout is None:
        return selected
    if timeout <= 0:
        raise ValueError(f"LLM timeout must be > 0, got {timeout!r}")
    return _replace_timeout(selected, timeout)


def public_llm_profiles(settings: Any) -> dict[str, Any]:
    profiles, default_id = load_llm_profiles(settings)
    return {
        "default_profile_id": default_id,
        "profiles": [profile.public_dict() for profile in profiles],
    }


def _read_profiles_file(settings: Any) -> dict[str, Any]:
    path = settings.resolve_path(getattr(settings, "LLM_PROFILES_PATH", "config/llm_profiles.json"))
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _profile_entries(data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    raw_profiles = data.get("profiles")
    if isinstance(raw_profiles, list):
        return [item for item in raw_profiles if isinstance(item, dict)]
    if isinstance(raw_profiles, dict):
        return [
            {"id": key, **value}
            for key, value in raw_profiles.items()
            if isinstance(value, dict)
        ]
    return []


def _legacy_entry(settings: Any) -> dict[str, Any]:
    return {
        "id": "default",
        "api_url": str(getattr(settings, "LLM_API_URL")),
        "api_key": str(_fresh_env_value(settings, "LLM_API_KEY") or getattr(settings, "LLM_API_KEY")),
        "model": str(getattr(settings, "LLM_MODEL")),
        "timeout": float(getattr(settings, "LLM_TIMEOUT")),
    }


def _profile_from_entry(entry: dict[str, Any], settings: Any) -> LLMProfile | None:
    profile_id = str(entry.get("id") or "").strip()
    model = str(entry.get("model") or "").strip()
    if not profile_id or not model:
        return None

    timeout = entry.get("timeout", getattr(settings, "LLM_TIMEOUT"))

    return LLMProfile(
        id=profile_id,
        api_url=str(entry.get("api_url") or getattr(settings, "LLM_API_URL")),
        api_key=str(
            entry.get("api_key")
            or _fresh_env_value(settings, "LLM_API_KEY")
            or getattr(settings, "LLM_API_KEY")
        ),
        model=model,
        timeout=float(timeout),
    )


def _fresh_env_value(settings: Any, key: str) -> str | None:
    """Read a single key from the current .env file without using cached Settings."""
    try:
        env_path = settings.resolve_path(".env")
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        raw_name, raw_value = line.split("=", 1)
        name = raw_name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        if name != key:
            continue
        value = raw_value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        return value
    return None


def _replace_default(profile: LLMProfile, is_default: bool) -> LLMProfile:
    return LLMProfile(
        id=profile.id,
        api_url=profile.api_url,
        api_key=profile.api_key,
        model=profile.model,
        timeout=profile.timeout,
        is_default=is_default,
    )


def _replace_timeout(profile: LLMProfile, timeout: float) -> LLMProfile:
    return LLMProfile(
        id=profile.id,
        api_url=profile.api_url,
        api_key=profile.api_key,
        model=profile.model,
        timeout=float(timeout),
        is_default=profile.is_default,
    )
