"""Tests for the SQLite demo workspace store and tool integration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from fin_copilot.agents.compliant_generator import CompliantGenerator
from fin_copilot.demo import store as store_module
from fin_copilot.routers import demo as demo_router
import pytest

from fin_copilot.demo.store import DemoStore, DemoStoreError, RESOURCE_META
from fin_copilot.llm.profiles import LLMProfile
from fin_copilot.models.skill import SkillDefinition
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


def test_eval_txt_parser_is_strict_line_based():
    parsed = demo_router._parse_eval_txt(
        "\n".join(
            [
                "客户:你好",
                "客户：我想延期",
                "客服:您好",
                "客服：请提供核身信息",
                "户:转写缺字要丢弃",
                "<div>noise</div>",
                " 客户: 周五还可以吗 ",
            ]
        )
    )

    assert [msg["role"] for msg in parsed["messages"]] == [
        "user",
        "user",
        "assistant",
        "assistant",
        "user",
    ]
    assert parsed["messages"][0]["content"] == "你好"
    assert parsed["messages"][3]["content"] == "请提供核身信息"
    assert parsed["parse_summary"]["user_messages"] == 3
    assert parsed["parse_summary"]["assistant_messages"] == 2
    assert parsed["parse_summary"]["dropped_lines"] == 2


def test_eval_main_skill_uses_golden_style_aggregation():
    turns = [
        {"matched_skill_id": "greeting_opening", "response": {"confidence": 1.0}},
        {"matched_skill_id": "stop_collection", "response": {"confidence": 0.3}},
        {"matched_skill_id": "overdue_negotiation", "response": {"confidence": 0.9}},
        {"matched_skill_id": "stop_collection", "response": {"confidence": 0.3}},
        {"matched_skill_id": "overdue_negotiation", "response": {"confidence": 0.7}},
    ]

    assert demo_router._rank_main_skill(turns) == "overdue_negotiation"
    mapped = demo_router._map_skill_to_intent("overdue_negotiation")
    assert mapped["l2"]


def test_eval_store_deduplicates_txt_filename(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())
    payload = {
        "raw_text": "客户:你好",
        "messages": [
            {"message_id": "m001", "index": 1, "role": "user", "content": "你好", "source_line": 1},
        ],
        "dropped_lines": [],
        "parse_summary": {"raw_lines": 1, "kept_messages": 1, "user_messages": 1, "assistant_messages": 0, "dropped_lines": 0},
    }

    first = store.create_eval_txt_file(filename="case.txt", **payload)
    second = store.create_eval_txt_file(filename="case.txt", **payload)
    third = store.create_eval_txt_file(filename="case.txt", **payload)

    assert first["filename"] == "case.txt"
    assert second["filename"] == "case (2).txt"
    assert third["filename"] == "case (3).txt"


def test_eval_file_summary_exposes_badcase_flag(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())
    file = store.create_eval_txt_file(
        filename="bad.txt",
        raw_text="客户:你好",
        messages=[
            {"message_id": "m001", "index": 1, "role": "user", "content": "你好", "source_line": 1},
        ],
        dropped_lines=[],
        parse_summary={"raw_lines": 1, "kept_messages": 1, "user_messages": 1, "assistant_messages": 0, "dropped_lines": 0},
    )
    file = store.update_eval_txt_badcase(file["txt_id"], badcase=True, note="整通异常")

    summary = demo_router._eval_file_summary(file, [])

    assert summary["badcase"] is True
    assert summary["badcase_note"] == "整通异常"


def test_eval_intent_options_include_all_golden_categories():
    labels = {item["l2"] for item in demo_router._eval_intent_options()}

    assert len(labels) >= 42
    assert {
        "聚合码还款问题",
        "提前清贷",
        "结清证明",
        "非我司产品",
        "放款结果",
        "预约借款",
        "资料信息修改",
        "特殊场景",
        "产品建议1",
        "贷款解约",
        "无效会话",
    }.issubset(labels)
    assert demo_router._map_skill_to_intent("loan_termination")["l2"] == "贷款解约"


def test_eval_store_cascades_txt_delete(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())
    file = store.create_eval_txt_file(
        filename="case.txt",
        raw_text="客户:你好\n客服:您好",
        messages=[
            {"message_id": "m001", "index": 1, "role": "user", "content": "你好", "source_line": 1},
            {"message_id": "m002", "index": 2, "role": "assistant", "content": "您好", "source_line": 2},
        ],
        dropped_lines=[],
        parse_summary={"raw_lines": 2, "kept_messages": 2, "user_messages": 1, "assistant_messages": 1, "dropped_lines": 0},
    )
    marked = store.update_eval_txt_badcase(file["txt_id"], badcase=True, note="整通会话异常")
    assert marked["badcase"] is True
    assert marked["badcase_note"] == "整通会话异常"
    run = store.start_eval_run(
        txt_id=file["txt_id"],
        llm_profile_id="glm-5.1",
        total_turns=1,
        job_id="job-test",
    )
    turn = store.upsert_eval_turn_result(
        run_id=run["run_id"],
        txt_id=file["txt_id"],
        message_index=1,
        user_query="你好",
        context_messages=[],
        status="success",
        model_answer="您好，请问有什么可以帮您？",
        matched_skill_id="greeting_opening",
        response={"confidence": 0.9},
    )
    store.annotate_eval_turn_result(
        turn["turn_result_id"],
        accepted=False,
        reject_reasons=["推荐错误"],
        note="bad",
        badcase=True,
    )
    updated_run = store.get_eval_run_by_id(run["run_id"])
    updated_turn = store.get_eval_turn_result(turn["turn_result_id"])
    assert updated_run is not None
    assert updated_turn is not None
    assert updated_run["rejected_turns"] == 1
    assert updated_run["issue_count"] == 1
    assert updated_run["badcase_count"] == 0
    assert updated_turn["badcase"] is False

    assert store.delete_eval_txt_files([file["txt_id"]]) == 1
    assert store.get_eval_txt_file(file["txt_id"]) is None
    assert store.list_eval_runs(txt_id=file["txt_id"]) == []
    assert store.get_eval_turn_result(turn["turn_result_id"]) is None


def test_eval_jobs_list_recent_with_config(tmp_path: Path):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())

    first = store.create_eval_job(
        "glm-5.1",
        3,
        {"txt_file_ids": ["txt-a"], "concurrency": 2, "timeout_seconds": 30},
    )
    second = store.create_eval_job(
        "qwen3.6-flash",
        5,
        {"txt_file_ids": ["txt-b"], "concurrency": 1, "timeout_seconds": 60},
    )

    jobs = store.list_eval_jobs(limit=10)

    assert jobs[0]["job_id"] == second["job_id"]
    assert jobs[1]["job_id"] == first["job_id"]
    assert jobs[0]["config"]["txt_file_ids"] == ["txt-b"]
    assert jobs[0]["config"]["timeout_seconds"] == 60


def test_eval_generation_uses_true_prior_context(tmp_path: Path, monkeypatch):
    store = DemoStore(tmp_path / "demo.sqlite3", project_root=Path.cwd())
    monkeypatch.setattr(demo_router, "get_demo_store", lambda: store)
    monkeypatch.setattr(demo_router, "set_active_llm_profile", lambda profile: object())
    monkeypatch.setattr(demo_router, "reset_active_llm_profile", lambda token: None)

    class FakeOrchestrator:
        def __init__(self):
            self.ctx = SimpleNamespace(_sessions={})
            self.calls = []

        async def handle_turn(self, session_id: str, user_query: str):
            seeded = self.ctx._sessions[session_id]
            self.calls.append({
                "query": user_query,
                "customer_id": seeded.customer.customer_id,
                "history": [(message.role, message.text) for message in seeded.messages],
                "last_agent_reply": seeded.last_agent_reply,
                "eval_flow_stage": seeded.slots.get("eval_flow_stage"),
            })
            return SimpleNamespace(
                answer="模型回复",
                route="route_b",
                matched_skill_id="quota_consultation",
                matched_skill_name="额度咨询",
                tools_called=["get_quota_service_info"],
                trace_id="tr-test",
                compliance_passed=True,
                model_dump=lambda: {"confidence": 0.95},
            )

    fake_orch = FakeOrchestrator()
    monkeypatch.setattr(demo_router, "get_orchestrator", lambda: fake_orch)
    messages = [
        {"index": 1, "role": "user", "content": "你好"},
        {"index": 2, "role": "assistant", "content": "您好，请问有什么可以帮您？"},
        {"index": 3, "role": "user", "content": "帮我查额度"},
    ]
    file = store.create_eval_txt_file(
        filename="context.txt",
        raw_text="客户:你好\n客服:您好，请问有什么可以帮您？\n客户:帮我查额度",
        messages=messages,
        dropped_lines=[],
        parse_summary={"raw_lines": 3, "kept_messages": 3, "user_messages": 2, "assistant_messages": 1, "dropped_lines": 0},
    )
    run = store.start_eval_run(
        txt_id=file["txt_id"],
        llm_profile_id="glm-5.1",
        total_turns=2,
        job_id="job-test",
    )

    result = asyncio.run(
        demo_router._generate_eval_turn(
            profile=LLMProfile(
                id="glm-5.1",
                api_url="http://model.local/v1",
                api_key="key",
                model="glm-5.1",
                timeout=30.0,
            ),
            file=file,
            run_id=run["run_id"],
            user_msg=file["messages"][2],
            timeout_seconds=5,
        )
    )

    assert result["status"] == "success"
    assert result["model_answer"] == "模型回复"
    assert result["mapped_intent"]["l2"]
    assert fake_orch.calls == [
        {
            "query": "帮我查额度",
            "customer_id": "C100",
            "history": [
                ("customer", "你好"),
                ("agent", "您好，请问有什么可以帮您？"),
            ],
            "last_agent_reply": "您好，请问有什么可以帮您？",
            "eval_flow_stage": "general",
        }
    ]


def test_eval_context_restores_stop_collection_stage():
    context = [
        {"index": 1, "role": "user", "content": "说声就不要继续电话信息来"},
        {"index": 2, "role": "assistant", "content": "亲亲是担心电话打扰是吗"},
    ]
    prior_turns = [
        {"message_index": 1, "matched_skill_id": "stop_collection", "matched_skill_name": "要求停催"},
    ]

    ctx = demo_router._eval_dialogue_context(context, prior_turns, "对的")

    assert ctx["stage"] == "stop_collection.confirming_need"
    assert ctx["prior_skill"] == "stop_collection"
    assert "stop_days" not in ctx["slots"]
    assert "stop_collection_processed" not in ctx["slots"]
    assert ctx["slots"]["eval_no_business_operation_claim"] is True
    assert ctx["slots"]["target"] == "self"
    assert "承接上一句真实坐席动作" in ctx["narrative_summary"]
    assert "禁止宣称已处理" in ctx["narrative_summary"]


def test_eval_business_slots_hide_identity_values():
    profile = {
        "customer_id": "C100",
        "customer_name": "张三",
        "phone": "13812345678",
        "id_number": "110101199003151234",
        "id_last4": "1234",
    }
    slots = demo_router._eval_business_slots(
        profile,
        {"overdue_amount": 8500, "overdue_days": 45},
        {"loan_status": "active"},
    )

    assert slots["customer_name"] == "张三"
    assert slots["overdue_days"] == 45
    assert "phone" not in slots
    assert "phone_masked" not in slots
    assert "id_last4" not in slots
    assert "id_number" not in slots


def test_eval_context_marks_identity_display_completed():
    context = [
        {"index": 1, "role": "user", "content": "我款想延期周五还"},
        {"index": 2, "role": "assistant", "content": "为了确保您的信息安全，辛苦您提供一下几项相关信息"},
        {"index": 3, "role": "assistant", "content": "相信您有还款意愿，所以冒昧了解下是什么原因导致无法还款"},
    ]

    ctx = demo_router._eval_dialogue_context(context, [], "公司些事项，所以款周五还")

    assert ctx["stage"] == "overdue_negotiation.collecting_reason"
    assert ctx["slots"]["eval_identity_already_displayed"] is True
    assert ctx["slots"]["eval_skip_identity_generation"] is True
    assert "禁止再次" in ctx["narrative_summary"]


def test_eval_identity_guard_rewrites_id_readback_to_generic_display():
    skill = SkillDefinition(skill_id="overdue_negotiation", name="协商还款")

    guarded = CompliantGenerator._enforce_eval_identity_boundary(
        {"answer": "张三先生，请问您的身份证后四位是1234吗？"},
        skill,
        {
            "eval_identity_flow_mode": "display_only_c100",
            "eval_identity_display_needed": True,
            "customer_name": "张三",
            "repayment_time": "周五",
        },
    )

    assert "1234" not in guarded["answer"]
    assert "证件后四位中的任一项" in guarded["answer"]
    assert "周五" in guarded["answer"]


def test_eval_identity_guard_prevents_repeated_verification():
    skill = SkillDefinition(skill_id="overdue_negotiation", name="协商还款")

    guarded = CompliantGenerator._enforce_eval_identity_boundary(
        {"answer": "为了您的信息安全，方便先提供一下身份证后四位或者注册手机号吗？"},
        skill,
        {
            "eval_identity_flow_mode": "display_only_c100",
            "eval_identity_already_displayed": True,
            "customer_name": "张三",
            "overdue_reason": "公司些事项",
            "repayment_time": "周五",
            "overdue_days": 45,
            "overdue_amount": 8500,
        },
    )

    assert "身份证" not in guarded["answer"]
    assert "手机号" not in guarded["answer"]
    assert "周五" in guarded["answer"]
    assert "45天" in guarded["answer"]
    assert "8500元" in guarded["answer"]


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
