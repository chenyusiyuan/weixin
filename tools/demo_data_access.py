"""Helpers for reading mutable demo data from the SQLite store."""

from __future__ import annotations

from typing import Any

from fin_copilot.demo.store import DemoStoreError, get_demo_store
from tools.mock_data import DEFAULT_CUSTOMER_ID


def customer_id_from_state(state: dict) -> str:
    return state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID


def get_customer_payload(resource: str, customer_id: str) -> dict[str, Any]:
    try:
        payload = get_demo_store().get_customer_payload(resource, customer_id)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return {"customer_id": customer_id, "error": f"demo_store_unavailable: {exc}"}
    if payload is None:
        return {"customer_id": customer_id, "error": f"demo_record_not_found: {resource}"}
    return dict(payload)


def list_customer_payloads(resource: str, customer_id: str, result_key: str) -> dict[str, Any]:
    try:
        records = get_demo_store().list_customer_payloads(resource, customer_id)
    except DemoStoreError as exc:
        return {"customer_id": customer_id, result_key: [], "total_count": 0, "error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return {
            "customer_id": customer_id,
            result_key: [],
            "total_count": 0,
            "error": f"demo_store_unavailable: {exc}",
        }
    return {
        "customer_id": customer_id,
        result_key: records,
        "total_count": len(records),
    }

