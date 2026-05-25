"""Identity verification data sourced from the mutable demo store."""

from __future__ import annotations

from fin_copilot.demo.store import get_demo_store


def get_verification_db() -> dict[str, dict[str, str]]:
    return get_demo_store().verification_db()

