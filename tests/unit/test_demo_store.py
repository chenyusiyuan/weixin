"""Tests for the SQLite demo workspace store and tool integration."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException

from fin_copilot.demo import store as store_module
from fin_copilot.routers import demo as demo_router
import pytest

from fin_copilot.demo.store import DemoStore, DemoStoreError, RESOURCE_META
from fin_copilot.llm.profiles import LLMProfile
from tools.get_bill_and_repayment_plan import get_bill_and_repayment_plan
from tools.query_ticket import query_ticket
from tools.submit_ticket import submit_ticket


def _state(customer_id: str) -> dict:
    return {"customer": {"customer_id": customer_id}, "slots": {}, "intent": {}}


def test_demo_store_seeds_all_resources(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())

    summary = store.resource_summary()
    counts = {item["name"]: item["count"] for item in summary["resources"]}

    assert set(counts) == set(RESOURCE_META)
    assert counts["customers"] == 3
    assert counts["tickets"] == 8
    assert summary["db_path"].endswith("demo.sqlite3")
    assert store.get_record("customers", "C100")["payload"]["phone_masked"] == "13812345678"
    assert store.get_record("customers", "C100")["immutable"] is True


def test_demo_store_crud_and_sessions(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())

    bill = store.get_customer_payload("bills", "C100")
    assert bill and bill["overdue_days"] == 45

    bill["overdue_days"] = 66
    with pytest.raises(DemoStoreError):
        store.upsert_record("bills", "C100", bill)
    with pytest.raises(DemoStoreError):
        store.delete_record("customers", "C100")

    customer = {
        "customer_id": "C200",
        "customer_name": "赵六",
        "phone": "13700003333",
        "id_last4": "3333",
    }
    created = store.upsert_record("customers", "C200", customer)
    assert created["immutable"] is False
    assert created["payload"]["phone_masked"] == "13700003333"
    assert store.delete_record("customers", "C200") is True

    session = store.create_session(title="测试会话", llm_profile_id="default")
    store.add_message(session["session_id"], "customer", "我要查账单")
    store.update_session(session["session_id"], customer_id="C100", llm_profile_id="alt")
    messages = store.list_messages(session["session_id"])

    assert store.get_session(session["session_id"])["customer_id"] == "C100"
    assert store.get_session(session["session_id"])["llm_profile_id"] == "alt"
    assert store.get_session(session["session_id"])["customer_message_count"] == 1
    assert store.has_customer_messages(session["session_id"]) is True
    assert messages[0]["text"] == "我要查账单"


def test_demo_session_model_lock_ignores_system_messages(tmp_path: Path, monkeypatch):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())
    monkeypatch.setattr(demo_router, "get_demo_store", lambda: store)
    monkeypatch.setattr(
        demo_router,
        "_llm_profile_or_404",
        lambda profile_id: LLMProfile(
            id=profile_id,
            api_url="http://model.local/v1",
            api_key="key",
            model=profile_id,
            timeout=30.0,
        ),
    )

    session = store.create_session(title="模型锁测试", llm_profile_id="a")
    store.add_message(session["session_id"], "system", "已注入核身客户 C100")

    async def _set_profile(profile_id: str):
        req = demo_router.LLMProfileRequest(llm_profile_id=profile_id)
        return await demo_router.update_session_llm_profile(session["session_id"], req)

    updated = asyncio.run(_set_profile("b"))
    assert updated["session"]["llm_profile_id"] == "b"
    assert updated["session"]["customer_message_count"] == 0

    store.add_message(session["session_id"], "customer", "我的贷款逾期多长时间了")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_set_profile("c"))
    assert exc.value.status_code == 409


def test_tools_read_and_write_demo_store(tmp_path: Path, monkeypatch):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())
    monkeypatch.setattr(store_module, "_default_store", store)

    bill = {"bill_amount": 10.0, "overdue_days": 88, "repayment_status": "overdue"}
    store.upsert_record("customers", "C200", {
        "customer_id": "C200",
        "customer_name": "赵六",
        "phone": "13700003333",
        "id_last4": "3333",
    })
    store.upsert_record("bills", "C200", bill)

    async def _run():
        before = await get_bill_and_repayment_plan(_state("C200"))
        submitted = await submit_ticket(
            {
                "customer": {"customer_id": "C100"},
                "slots": {"ticket_type": "演示工单", "ticket_summary": "后台联动测试"},
                "intent": {},
            }
        )
        tickets = await query_ticket(_state("C100"))
        return before, submitted, tickets

    before, submitted, tickets = asyncio.run(_run())
    assert before["overdue_days"] == 88
    assert submitted["status"] == "submitted"
    assert any(t["summary"] == "后台联动测试" for t in tickets["tickets"])
    new_ticket_id = submitted["ticket_id"]
    assert store.delete_record("tickets", new_ticket_id) is True
    with pytest.raises(DemoStoreError):
        store.delete_record("tickets", "TK20260409001")
