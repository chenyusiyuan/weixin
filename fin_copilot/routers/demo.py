"""Demo API and static workspace support."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fin_copilot.config import get_settings
from fin_copilot.demo.store import RESOURCE_META, DemoStoreError, get_demo_store
from fin_copilot.llm.profiles import (
    LLMProfile,
    load_llm_profiles,
    public_llm_profiles,
    reset_active_llm_profile,
    set_active_llm_profile,
)
from fin_copilot.models.conversation import ConversationState, CustomerInfo, Message, ToolCacheEntry
from fin_copilot.routers.gateway import get_llm_client, get_orchestrator
from tools.registry import TOOL_REGISTRY_META

router = APIRouter(prefix="/api/demo", tags=["demo"])

EVAL_IDENTITY_FLOW = {
    "mode": "display_only_success",
    "label": "核身展示成功流程",
    "validation": "disabled",
    "mock_customer_id": "C100",
}

_eval_job_tasks: dict[str, asyncio.Task] = {}


class CreateSessionRequest(BaseModel):
    title: str = "新对话"
    llm_profile_id: str = ""


class InjectCustomerRequest(BaseModel):
    customer_id: str


class DemoChatRequest(BaseModel):
    session_id: str
    user_text: str
    llm_profile_id: str = ""


class LLMProfileRequest(BaseModel):
    llm_profile_id: str


class DataRecordRequest(BaseModel):
    owner_id: str = ""
    record_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeRequest(BaseModel):
    customer_id: str = ""
    slots: dict[str, Any] = Field(default_factory=dict)
    intent: dict[str, Any] = Field(default_factory=dict)


class EvalImportFile(BaseModel):
    filename: str = "未命名.txt"
    content: str


class EvalImportRequest(BaseModel):
    files: list[EvalImportFile]


class EvalDeleteRequest(BaseModel):
    txt_file_ids: list[str]


class EvalGenerateRequest(BaseModel):
    txt_file_ids: list[str]
    llm_profile_id: str
    concurrency: int = Field(default=3, ge=1, le=12)
    timeout_seconds: float = Field(default=60, ge=5, le=300)
    retry_failed_only: bool = False


class EvalAnnotationRequest(BaseModel):
    accepted: bool | None = None
    reject_reasons: list[str] = Field(default_factory=list)
    note: str = ""
    badcase: bool = False


class EvalTxtBadcaseRequest(BaseModel):
    badcase: bool = False
    note: str = ""


class EvalRunIntentReviewRequest(BaseModel):
    intent_error: bool = False
    corrected_intent_l2: str = ""
    note: str = ""


@router.get("/health")
async def health(
    probe: bool = Query(default=False),
    llm_profile_id: str = Query(default=""),
) -> dict[str, Any]:
    settings = get_settings()
    llm_profile = _llm_profile_or_default(llm_profile_id)
    store = get_demo_store()
    skill_dir = settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)
    registry_path = settings.resolve_path(settings.SKILL_REGISTRY_PATH)
    rule_path = settings.resolve_path(settings.RULE_ENGINE_PATH)

    status: dict[str, Any] = {
        "database": {"status": "ok", **store.resource_summary()},
        "skills": _file_status(registry_path, yaml_count=skill_dir),
        "rules": _file_status(rule_path),
        "llm": {
            "status": "configured",
            "api_url": llm_profile.api_url,
            "model": llm_profile.model,
            "profile_id": llm_profile.id,
            "profiles": public_llm_profiles(settings)["profiles"],
            **_runtime_llm_status(llm_profile.id),
        },
        "embedding": {
            "status": "configured",
            "api_url": settings.EMBED_API_URL,
            "model": settings.EMBED_MODEL,
        },
    }

    try:
        orch = get_orchestrator()
        status["runtime"] = {
            "status": "ok",
            "domain_classifier": orch.domain_clf.__class__.__name__,
            "skill_embedding_index": orch.skill_embedding_index is not None,
        }
    except HTTPException as exc:
        status["runtime"] = {"status": "not_initialized", "detail": exc.detail}

    if probe:
        status["llm"].update(await _probe_llm(llm_profile))
        status["embedding"] = await _probe_embedding(settings)

    return status


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    return {"sessions": get_demo_store().list_sessions()}


@router.get("/resources")
async def resources() -> dict[str, Any]:
    return {
        "resources": [
            _meta_response(name, meta)
            for name, meta in RESOURCE_META.items()
        ]
    }


@router.get("/llm-profiles")
async def llm_profiles() -> dict[str, Any]:
    return public_llm_profiles(get_settings())


@router.get("/tools")
async def tools() -> dict[str, Any]:
    return {
        "tools": [
            {"name": name, "permission": meta.get("permission", "read")}
            for name, meta in TOOL_REGISTRY_META.items()
        ]
    }


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    profile = _llm_profile_or_default(req.llm_profile_id)
    return {
        "session": get_demo_store().create_session(
            title=req.title,
            llm_profile_id=profile.id,
        )
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    deleted = get_demo_store().delete_session(session_id)
    return {"deleted": deleted}


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str) -> dict[str, Any]:
    store = get_demo_store()
    store.ensure_session(session_id)
    return {
        "session": store.get_session(session_id),
        "messages": store.list_messages(session_id),
    }


@router.post("/sessions/{session_id}/llm-profile")
async def update_session_llm_profile(session_id: str, req: LLMProfileRequest) -> dict[str, Any]:
    store = get_demo_store()
    store.ensure_session(session_id)
    if store.has_customer_messages(session_id):
        raise HTTPException(
            status_code=409,
            detail="会话已开始，模型已固定，不能再切换模型",
        )
    profile = _llm_profile_or_404(req.llm_profile_id)
    session = store.update_session(session_id, llm_profile_id=profile.id)
    return {"session": session, "llm": profile.public_dict()}


@router.post("/sessions/{session_id}/inject-customer")
async def inject_customer(session_id: str, req: InjectCustomerRequest) -> dict[str, Any]:
    store = get_demo_store()
    profile = store.get_customer_payload("customers", req.customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"customer not found: {req.customer_id}")

    orch = get_orchestrator()
    state = orch.ctx.get_or_create(session_id)
    state.customer.customer_id = req.customer_id
    state.customer.verified = True
    state.customer.verification_level = "full"
    state.customer.verification_step = "passed"
    state.customer.verification_attempts = 0
    state.customer.candidate_customer_ids = []
    state.customer.pending_query = ""
    state.customer.pending_route = {}
    state.customer.name_masked = str(profile.get("customer_name") or "")
    state.customer.phone_masked = str(profile.get("phone") or profile.get("phone_masked") or "")
    id_last4 = str(profile.get("id_last4") or "")
    if not id_last4 and profile.get("id_number"):
        id_last4 = str(profile["id_number"])[-4:].upper()
    state.customer.id_last4 = id_last4
    orch.ctx.state_mgr.update_slots(
        state,
        {
            "customer_id": req.customer_id,
            "customer_name": state.customer.name_masked,
            "phone": state.customer.phone_masked,
            "id_last4": state.customer.id_last4,
        },
    )

    session = store.update_session(session_id, customer_id=req.customer_id)
    store.add_message(
        session_id,
        "system",
        f"已注入核身客户 {req.customer_id} - {profile.get('customer_name', '')}",
        metadata={"action": "inject_customer", "customer_id": req.customer_id},
    )
    return {"session": session, "customer": profile}


@router.post("/chat")
async def demo_chat(req: DemoChatRequest) -> dict[str, Any]:
    return await _run_demo_chat(req)


@router.post("/chat/stream")
async def demo_chat_stream(req: DemoChatRequest) -> StreamingResponse:
    async def _events():
        yield _json_line({"type": "status", "message": "已收到客户输入"})
        task = asyncio.create_task(_run_demo_chat(req))
        heartbeat = 0
        while not task.done():
            heartbeat += 1
            yield _json_line({
                "type": "status",
                "message": "正在识别意图、查询工具并生成话术",
                "heartbeat": heartbeat,
            })
            await asyncio.sleep(0.8)
        try:
            data = await task
        except Exception as exc:
            yield _json_line({"type": "error", "message": str(exc)})
            return

        answer = data.get("response", {}).get("answer", "")
        if answer:
            for chunk in _chunk_text(answer):
                yield _json_line({"type": "answer_delta", "delta": chunk})
                await asyncio.sleep(0.015)
        yield _json_line({"type": "final", **data})

    return StreamingResponse(
        _events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_demo_chat(req: DemoChatRequest) -> dict[str, Any]:
    store = get_demo_store()
    session = store.ensure_session(req.session_id)
    has_started = store.has_customer_messages(req.session_id)
    locked_profile_id = session.get("llm_profile_id", "") if has_started else ""
    requested_profile_id = locked_profile_id or req.llm_profile_id or session.get("llm_profile_id", "")
    llm_profile = _llm_profile_or_default(requested_profile_id)
    if (not has_started and req.llm_profile_id) or session.get("llm_profile_id") != llm_profile.id:
        session = store.update_session(req.session_id, llm_profile_id=llm_profile.id)
    if session.get("title") == "新对话" and req.user_text.strip():
        title = req.user_text.strip()[:24]
        session = store.update_session(req.session_id, title=title)

    user_message = store.add_message(req.session_id, "customer", req.user_text)
    orch = get_orchestrator()
    token = set_active_llm_profile(llm_profile)
    try:
        response = await orch.handle_turn(req.session_id, req.user_text)
    finally:
        reset_active_llm_profile(token)
    response_payload = response.model_dump()
    state = orch.ctx.get_or_create(req.session_id)
    customer_id = state.customer.customer_id if state.customer.verified else session.get("customer_id", "")
    if customer_id:
        session = store.update_session(req.session_id, customer_id=customer_id)

    metadata = {
        "session_id": req.session_id,
        "customer_id": customer_id,
        "route": response.route,
        "matched_skill_id": response.matched_skill_id,
        "matched_skill_name": response.matched_skill_name,
        "tools_called": response.tools_called,
        "trace_id": response.trace_id,
        "compliance_passed": response.compliance_passed,
        "llm_profile_id": llm_profile.id,
        "llm_model": llm_profile.model,
    }
    assistant_message = store.add_message(
        req.session_id,
        "assistant",
        response.answer,
        response=response_payload,
        metadata=metadata,
    )
    session = store.get_session(req.session_id) or session
    return {
        "session": session,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "response": response_payload,
        "debug": metadata,
        "llm": llm_profile.public_dict(),
    }


@router.get("/data/{resource}")
async def list_data(resource: str, owner_id: str = Query(default="")) -> dict[str, Any]:
    meta = _resource_meta_or_404(resource)
    records = get_demo_store().list_records(resource, owner_id or None)
    return {"resource": _meta_response(resource, meta), "records": records}


@router.post("/data/{resource}")
async def create_data(resource: str, req: DataRecordRequest) -> dict[str, Any]:
    _resource_meta_or_404(resource)
    try:
        record = get_demo_store().upsert_record(
            resource,
            req.owner_id,
            req.payload,
            req.record_id or None,
        )
    except DemoStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"record": record}


@router.put("/data/{resource}")
async def update_data(resource: str, req: DataRecordRequest) -> dict[str, Any]:
    return await create_data(resource, req)


@router.put("/data/{resource}/{record_id}")
async def update_data_by_id(resource: str, record_id: str, req: DataRecordRequest) -> dict[str, Any]:
    req.record_id = record_id
    return await create_data(resource, req)


@router.delete("/data/{resource}")
async def delete_data(resource: str, record_id: str = Query(default="")) -> dict[str, Any]:
    _resource_meta_or_404(resource)
    if not record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    try:
        deleted = get_demo_store().delete_record(resource, record_id)
    except DemoStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


@router.delete("/data/{resource}/{record_id}")
async def delete_data_by_id(resource: str, record_id: str) -> dict[str, Any]:
    return await delete_data(resource, record_id)


@router.post("/tools/{tool_name}/invoke")
async def invoke_tool(tool_name: str, req: ToolInvokeRequest) -> dict[str, Any]:
    meta = TOOL_REGISTRY_META.get(tool_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")
    state = {
        "customer": {"customer_id": req.customer_id},
        "slots": req.slots,
        "intent": req.intent,
    }
    result = await meta["handler"](state)
    return {
        "tool_name": tool_name,
        "permission": meta.get("permission", "read"),
        "result": result,
    }


@router.get("/skills")
async def skills(detail: bool = Query(default=False), skill_id: str = Query(default="")) -> dict[str, Any]:
    settings = get_settings()
    registry_path = settings.resolve_path(settings.SKILL_REGISTRY_PATH)
    definitions_dir = settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    definitions: list[dict[str, Any]] = []
    if detail or skill_id:
        paths = sorted(definitions_dir.glob("*.yaml"))
        for path in paths:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if skill_id and raw.get("skill_id") != skill_id:
                continue
            definitions.append(raw)

    return {
        "registry": registry,
        "definitions": definitions,
    }


@router.get("/rules")
async def rules() -> dict[str, Any]:
    settings = get_settings()
    rule_path = settings.resolve_path(settings.RULE_ENGINE_PATH)
    return json.loads(rule_path.read_text(encoding="utf-8"))


@router.post("/reset-data")
async def reset_data() -> dict[str, Any]:
    return {"summary": get_demo_store().reset_records()}


@router.post("/eval/txt-files/import")
async def eval_import_txt_files(req: EvalImportRequest) -> dict[str, Any]:
    if not req.files:
        raise HTTPException(status_code=400, detail="files is required")
    store = get_demo_store()
    files = []
    for item in req.files:
        parsed = _parse_eval_txt(item.content)
        files.append(
            store.create_eval_txt_file(
                filename=item.filename or "未命名.txt",
                raw_text=item.content,
                messages=parsed["messages"],
                dropped_lines=parsed["dropped_lines"],
                parse_summary=parsed["parse_summary"],
            )
        )
    return {"files": files}


@router.get("/eval/txt-files")
async def eval_list_txt_files(view: str = Query(default="all")) -> dict[str, Any]:
    store = get_demo_store()
    files = store.list_eval_txt_files()
    profiles = public_llm_profiles(get_settings())["profiles"]
    if view == "all":
        return {
            "view": "all",
            "files": [_eval_file_summary(file, store.list_eval_runs(file["txt_id"])) for file in files],
            "profiles": profiles,
        }
    profile = _llm_profile_or_404(view)
    runs_by_txt = {run["txt_id"]: run for run in store.list_eval_runs(llm_profile_id=profile.id)}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file in files:
        run = runs_by_txt.get(file["txt_id"])
        item = _eval_file_summary(file, [run] if run else [])
        item["run"] = run
        if run is None:
            grouped["未生成"].append(item)
        elif run["status"] == "running":
            grouped["生成中"].append(item)
        elif run["status"] in {"error", "partial_failed", "cancelled"}:
            grouped["失败"].append(item)
        else:
            grouped[_effective_intent(run).get("l2") or "未分类"].append(item)
    order = ["未生成", "生成中", "失败"]
    groups = [
        {"name": name, "items": grouped.pop(name)}
        for name in order
        if grouped.get(name)
    ]
    groups.extend(
        {"name": name, "items": items}
        for name, items in sorted(grouped.items(), key=lambda pair: pair[0])
    )
    return {"view": profile.id, "groups": groups, "profiles": profiles}


@router.get("/eval/intent-options")
async def eval_intent_options() -> dict[str, Any]:
    return {"intents": _eval_intent_options()}


@router.get("/eval/txt-files/{txt_id}")
async def eval_get_txt_file(
    txt_id: str,
    llm_profile_id: str = Query(default=""),
) -> dict[str, Any]:
    store = get_demo_store()
    file = store.get_eval_txt_file(txt_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"unknown txt file: {txt_id}")
    runs = store.list_eval_runs(txt_id=txt_id)
    selected_profile = llm_profile_id or (runs[0]["llm_profile_id"] if runs else "")
    run = store.get_eval_run(txt_id, selected_profile) if selected_profile else None
    turns = store.list_eval_turn_results(run["run_id"]) if run else []
    return {
        "file": file,
        "runs": runs,
        "selected_llm_profile_id": selected_profile,
        "run": run,
        "turn_results": turns,
        "identity_flow": EVAL_IDENTITY_FLOW,
    }


@router.delete("/eval/txt-files")
async def eval_delete_txt_files(req: EvalDeleteRequest) -> dict[str, Any]:
    deleted = get_demo_store().delete_eval_txt_files(req.txt_file_ids)
    return {"deleted": deleted}


@router.post("/eval/txt-files/{txt_id}/badcase")
async def eval_mark_txt_badcase(txt_id: str, req: EvalTxtBadcaseRequest) -> dict[str, Any]:
    try:
        file = get_demo_store().update_eval_txt_badcase(
            txt_id,
            badcase=req.badcase,
            note=req.note,
        )
    except DemoStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"file": file}


@router.post("/eval/runs/{run_id}/intent-review")
async def eval_review_run_intent(run_id: str, req: EvalRunIntentReviewRequest) -> dict[str, Any]:
    corrected = _intent_by_l2(req.corrected_intent_l2)
    if req.intent_error and not corrected:
        raise HTTPException(status_code=400, detail="corrected_intent_l2 is required")
    try:
        run = get_demo_store().update_eval_run_intent_review(
            run_id,
            intent_error=req.intent_error,
            corrected_intent=corrected,
            note=req.note,
        )
    except DemoStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run": run}


@router.post("/eval/runs/generate")
async def eval_generate_runs(req: EvalGenerateRequest) -> dict[str, Any]:
    profile = _llm_profile_or_404(req.llm_profile_id)
    store = get_demo_store()
    files = []
    total_turns = 0
    for txt_id in req.txt_file_ids:
        file = store.get_eval_txt_file(txt_id)
        if file is None:
            raise HTTPException(status_code=404, detail=f"unknown txt file: {txt_id}")
        files.append(file)
        if req.retry_failed_only:
            existing_run = store.get_eval_run(txt_id, profile.id)
            if existing_run:
                total_turns += sum(
                    1
                    for turn in store.list_eval_turn_results(existing_run["run_id"])
                    if turn["status"] == "error"
                )
            continue
        total_turns += len(_eval_user_messages(file["messages"]))
    job = store.create_eval_job(
        profile.id,
        total_turns,
        {
            "txt_file_ids": req.txt_file_ids,
            "concurrency": req.concurrency,
            "timeout_seconds": req.timeout_seconds,
            "retry_failed_only": req.retry_failed_only,
            "identity_flow": EVAL_IDENTITY_FLOW,
        },
    )
    task = asyncio.create_task(_run_eval_generation_job(job["job_id"], profile, files, req))
    _eval_job_tasks[job["job_id"]] = task
    task.add_done_callback(lambda _task: _eval_job_tasks.pop(job["job_id"], None))
    return {"job": job}


@router.get("/eval/jobs")
async def eval_list_jobs(limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    store = get_demo_store()
    jobs = [_eval_job_detail(job, store) for job in store.list_eval_jobs(limit=limit)]
    return {"jobs": jobs}


@router.get("/eval/jobs/{job_id}")
async def eval_get_job(job_id: str) -> dict[str, Any]:
    store = get_demo_store()
    job = store.get_eval_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown eval job: {job_id}")
    return {"job": _eval_job_detail(job, store)}


@router.post("/eval/jobs/{job_id}/cancel")
async def eval_cancel_job(job_id: str) -> dict[str, Any]:
    store = get_demo_store()
    job = store.get_eval_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown eval job: {job_id}")
    store.update_eval_job(job_id, cancelled=1, status="cancelled")
    task = _eval_job_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
    return {"job": store.get_eval_job(job_id)}


@router.post("/eval/turn-results/{turn_result_id}/annotation")
async def eval_annotate_turn(turn_result_id: str, req: EvalAnnotationRequest) -> dict[str, Any]:
    try:
        result = get_demo_store().annotate_eval_turn_result(
            turn_result_id,
            accepted=req.accepted,
            reject_reasons=req.reject_reasons,
            note=req.note,
            badcase=req.badcase,
        )
    except DemoStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"turn_result": result}


@router.get("/eval/analytics/summary")
async def eval_analytics_summary(
    llm_profile_id: str = Query(default=""),
    intent_l2: str = Query(default=""),
    status: str = Query(default=""),
    badcase: bool = Query(default=False),
) -> dict[str, Any]:
    return _build_eval_analytics(
        llm_profile_id=llm_profile_id,
        intent_l2=intent_l2,
        status=status,
        badcase_only=badcase,
    )


def _parse_eval_txt(raw_text: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    lines = str(raw_text or "").splitlines()
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        marker = None
        content = ""
        for prefix in ("客户:", "客户：", "客服:", "客服："):
            if stripped.startswith(prefix):
                marker = prefix[:2]
                content = stripped[len(prefix):].strip()
                break
        if marker is None:
            dropped.append({"line": line_no, "content": line})
            continue
        messages.append({
            "message_id": f"m{len(messages) + 1:03d}",
            "index": len(messages) + 1,
            "role": "user" if marker == "客户" else "assistant",
            "content": _clean_eval_text(content),
            "source_line": line_no,
        })
    return {
        "messages": messages,
        "dropped_lines": dropped,
        "parse_summary": {
            "raw_lines": len(lines),
            "kept_messages": len(messages),
            "user_messages": sum(1 for item in messages if item["role"] == "user"),
            "assistant_messages": sum(1 for item in messages if item["role"] == "assistant"),
            "dropped_lines": len(dropped),
        },
    }


def _clean_eval_text(text: str) -> str:
    return " ".join(str(text or "").strip().strip('"“”').split())


def _eval_user_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in messages if item.get("role") == "user"]


def _eval_file_summary(file: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "txt_id": file["txt_id"],
        "filename": file["filename"],
        "parse_summary": file["parse_summary"],
        "user_turn_count": file["user_turn_count"],
        "model_count": len([run for run in runs if run]),
        "runs": [run for run in runs if run],
        "badcase": bool(file.get("badcase")),
        "badcase_note": file.get("badcase_note") or "",
        "imported_at": file["imported_at"],
    }


async def _run_eval_generation_job(
    job_id: str,
    profile: LLMProfile,
    files: list[dict[str, Any]],
    req: EvalGenerateRequest,
) -> None:
    store = get_demo_store()
    sem = asyncio.Semaphore(req.concurrency)
    try:
        for file in files:
            if _eval_job_cancelled(job_id):
                break
            await _run_eval_file(profile, file, req, job_id, sem)
        job = store.get_eval_job(job_id) or {}
        if job.get("cancelled"):
            store.update_eval_job(job_id, status="cancelled")
        elif job.get("failed_turns", 0):
            store.update_eval_job(job_id, status="partial_failed")
        else:
            store.update_eval_job(job_id, status="completed")
    except asyncio.CancelledError:
        store.update_eval_job(job_id, status="cancelled", cancelled=1)
    except Exception as exc:
        store.update_eval_job(job_id, status="error", error=_error_summary(exc))


async def _run_eval_file(
    profile: LLMProfile,
    file: dict[str, Any],
    req: EvalGenerateRequest,
    job_id: str,
    sem: asyncio.Semaphore,
) -> None:
    store = get_demo_store()
    messages = file["messages"]
    user_messages = _eval_user_messages(messages)
    run = store.start_eval_run(
        txt_id=file["txt_id"],
        llm_profile_id=profile.id,
        total_turns=len(user_messages),
        job_id=job_id,
        retry_failed_only=req.retry_failed_only,
    )
    existing_by_index = {
        row["message_index"]: row
        for row in store.list_eval_turn_results(run["run_id"])
    }

    prior_turns: list[dict[str, Any]] = []

    async def one_turn(user_msg: dict[str, Any]) -> dict[str, Any]:
        if req.retry_failed_only:
            existing = existing_by_index.get(int(user_msg["index"]))
            if existing and existing["status"] != "error":
                return existing
        async with sem:
            if _eval_job_cancelled(job_id):
                raise asyncio.CancelledError()
            result = await _generate_eval_turn(
                profile=profile,
                file=file,
                run_id=run["run_id"],
                user_msg=user_msg,
                timeout_seconds=req.timeout_seconds,
                prior_turns=prior_turns,
            )
            get_demo_store().refresh_eval_run_summary(run["run_id"])
            get_demo_store().increment_eval_job(job_id, success=result["status"] == "success")
            return result

    for msg in user_messages:
        result = await one_turn(msg)
        if isinstance(result, asyncio.CancelledError):
            raise result
        prior_turns.append(result)
    turns = store.list_eval_turn_results(run["run_id"])
    main_skill = _rank_main_skill(turns)
    main_intent = _map_skill_to_intent(main_skill)
    failed = [turn for turn in turns if turn["status"] == "error"]
    status_value = "partial_failed" if failed and len(failed) < len(user_messages) else "error" if failed else "completed"
    store.finish_eval_run(
        run["run_id"],
        status=status_value,
        main_skill_id=main_skill,
        main_intent=main_intent,
        error=f"{len(failed)} turn(s) failed" if failed else "",
    )


async def _generate_eval_turn(
    *,
    profile: LLMProfile,
    file: dict[str, Any],
    run_id: str,
    user_msg: dict[str, Any],
    timeout_seconds: float,
    prior_turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    store = get_demo_store()
    context_messages = [
        item for item in file["messages"]
        if int(item.get("index", 0)) < int(user_msg["index"])
    ]
    started = time.monotonic()
    try:
        orch = get_orchestrator()
        session_id = f"eval-{run_id}-{user_msg['index']}-{uuid.uuid4().hex[:6]}"
        eval_context = _seed_eval_session(
            orch,
            session_id,
            context_messages,
            prior_turns or [],
            user_msg,
        )
        token = set_active_llm_profile(profile)
        try:
            response = await asyncio.wait_for(
                orch.handle_turn(session_id, user_msg["content"]),
                timeout=timeout_seconds,
            )
        finally:
            reset_active_llm_profile(token)
        payload = response.model_dump()
        payload["eval_context"] = eval_context
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return store.upsert_eval_turn_result(
            run_id=run_id,
            txt_id=file["txt_id"],
            message_index=int(user_msg["index"]),
            user_query=user_msg["content"],
            context_messages=context_messages,
            status="success",
            model_answer=response.answer,
            route=response.route,
            matched_skill_id=response.matched_skill_id or "",
            matched_skill_name=response.matched_skill_name or "",
            mapped_intent=_map_skill_to_intent(response.matched_skill_id or ""),
            tools_called=response.tools_called,
            trace_id=response.trace_id,
            latency_ms=latency_ms,
            response=payload,
        )
    except Exception as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return store.upsert_eval_turn_result(
            run_id=run_id,
            txt_id=file["txt_id"],
            message_index=int(user_msg["index"]),
            user_query=user_msg["content"],
            context_messages=context_messages,
            status="error",
            error=_error_summary(exc),
            latency_ms=latency_ms,
        )


def _seed_eval_session(
    orch: Any,
    session_id: str,
    context_messages: list[dict[str, Any]],
    prior_turns: list[dict[str, Any]],
    user_msg: dict[str, Any],
) -> dict[str, Any]:
    state = ConversationState(session_id=session_id, customer=CustomerInfo())
    profile = get_demo_store().get_customer_payload("customers", "C100") or {}
    bill = get_demo_store().get_customer_payload("bills", "C100") or {}
    loan = get_demo_store().get_customer_payload("loans", "C100") or {}
    state.customer.customer_id = "C100"
    state.customer.verified = True
    state.customer.verification_level = "full"
    state.customer.verification_step = "passed"
    state.customer.name_masked = str(profile.get("customer_name") or "")
    state.customer.phone_masked = str(profile.get("phone") or profile.get("phone_masked") or "")
    state.customer.id_last4 = str(profile.get("id_last4") or str(profile.get("id_number") or "")[-4:])
    state.slots.update({
        "customer_id": "C100",
        "customer_name": state.customer.name_masked,
    })
    state.slots.update(_eval_business_slots(profile, bill, loan))

    now = time.monotonic()
    if profile:
        state.tool_cache["get_customer_profile"] = ToolCacheEntry(data=profile, ts=now)
    if bill:
        state.tool_cache["get_bill_and_repayment_plan"] = ToolCacheEntry(data=bill, ts=now)
    if loan:
        state.tool_cache["get_loan_service_info"] = ToolCacheEntry(data=loan, ts=now)

    turn_no = 0
    current_assistant_block: list[str] = []
    last_assistant_block: list[str] = []
    for item in context_messages:
        role = "customer" if item.get("role") == "user" else "agent"
        if role == "customer":
            turn_no += 1
            current_assistant_block = []
        else:
            if turn_no == 0:
                turn_no = 1
            current_assistant_block.append(str(item.get("content") or ""))
            last_assistant_block = list(current_assistant_block)
        state.messages.append(
            Message(
                role=role,
                text=str(item.get("content") or ""),
                turn=turn_no,
            )
        )
    state.total_turns = turn_no

    target_text = str(user_msg.get("content") or "")
    dialogue_context = _eval_dialogue_context(context_messages, prior_turns, target_text)
    if last_assistant_block:
        state.last_agent_reply = "\n".join(last_assistant_block)
    elif dialogue_context.get("last_agent_reply"):
        state.last_agent_reply = str(dialogue_context["last_agent_reply"])

    prior_skill = _eval_prior_skill(prior_turns, context_messages, dialogue_context, target_text)
    if prior_skill:
        state.intent.current_skill_id = prior_skill
        state.intent.domain = "逾期"
        state.intent.turn_in_skill = _eval_turn_in_skill(prior_turns, prior_skill)

    state.slots.update(dialogue_context.get("slots", {}))
    state.slots["eval_force_contextual_generation"] = True
    state.slots["eval_generation_mode"] = "sequential_teacher_forcing"
    state.slots["eval_no_business_operation_claim"] = True
    state.slots["eval_identity_flow_mode"] = "display_only_c100"
    state.slots["eval_identity_policy"] = (
        "评测固定使用 C100 mock 数据；核身只展示成功流程，不校验 TXT 内真实身份。"
        "首次需要核身时只能泛化提示客户提供姓名、注册手机号或证件后四位，不得复述或泄露 C100 的手机号、身份证号、身份证后四位。"
        "历史真实坐席一旦出现信息安全核身、等待处理或已继续追问业务，即视为核身展示完成，后续不得再次发起核身。"
    )
    state.summary = str(dialogue_context.get("summary") or "")
    state.narrative_summary = str(dialogue_context.get("narrative_summary") or "")
    # Eval generation should re-route/generate with the restored transcript
    # context, not shortcut through a zero-LLM sticky template.
    state.last_slot_fingerprint = ""
    if hasattr(orch.ctx, "_session_last_access"):
        orch.ctx._session_last_access[session_id] = time.monotonic()
    orch.ctx._sessions[session_id] = state
    return dialogue_context


def _eval_business_slots(
    profile: dict[str, Any],
    bill: dict[str, Any],
    loan: dict[str, Any],
) -> dict[str, Any]:
    slots: dict[str, Any] = {
        "customer_id": "C100",
        "customer_name": profile.get("customer_name") or "",
    }
    for key in (
        "bill_amount", "overdue_amount", "overdue_days", "repayment_status",
        "monthly_payment", "current_period", "remaining_periods",
    ):
        if key in bill:
            slots[key] = bill[key]
    if bill.get("next_repayment_date"):
        slots["due_date"] = bill["next_repayment_date"]
    for key in ("loan_amount", "loan_status", "loan_product"):
        if key in loan:
            slots[key] = loan[key]
    return slots


def _eval_dialogue_context(
    context_messages: list[dict[str, Any]],
    prior_turns: list[dict[str, Any]],
    target_text: str,
) -> dict[str, Any]:
    last_agent_reply = _eval_last_assistant_reply(context_messages)
    last_agent_act = _eval_assistant_act(last_agent_reply)
    target_act = _eval_user_act(target_text)
    stage = _eval_flow_stage(context_messages, last_agent_act, target_act)
    slots = _eval_context_slots(context_messages, target_text, last_agent_act, target_act, stage)
    prior_skill = _eval_prior_skill(prior_turns, context_messages, {
        "last_agent_act": last_agent_act,
        "target_act": target_act,
        "stage": stage,
    }, target_text)
    prior_skill_name = _eval_skill_name(prior_skill)
    spoken_acts = _eval_spoken_acts(context_messages)
    narrative = [
        "评测生成模式：逐轮推荐，当前轮只能参考目标客户句之前的真实客户/真实坐席历史。",
        "生成目标：推荐当前客户句之后坐席可说的话术；必须承接上一句真实坐席动作，禁止回到开场或重复首轮话术。",
        "操作边界：这是话术推荐，不代表已执行系统操作；没有明确写操作成功结果时，禁止宣称已处理、已提交、已申请成功或承诺停催时长。",
        f"上一句真实坐席：{last_agent_reply or '无'}",
        f"上一真实坐席动作：{_eval_act_label(last_agent_act)}",
        f"当前客户句动作：{_eval_act_label(target_act)}",
        f"当前流程阶段：{_eval_stage_label(stage)}",
        "评测核身规则：固定 C100 mock 数据；核身只展示流程，不校验 TXT 内输入，也不得复述 C100 的手机号、身份证号或证件后四位。",
    ]
    if slots.get("eval_identity_display_needed"):
        narrative.append("本轮只允许泛化展示核身引导：请客户提供姓名、注册手机号或证件后四位，不得把系统内证件后四位读给客户确认。")
    if slots.get("eval_identity_already_displayed"):
        narrative.append("历史真实坐席已展示过核身/信息安全流程，本轮视为核身已完成，必须继续推进业务，禁止再次索要手机号、身份证后四位或其他身份信息。")
    if prior_skill:
        narrative.append(f"最近业务技能：{prior_skill_name}（{prior_skill}），请在该业务进度内推进，除非客户明确换话题。")
    if spoken_acts:
        narrative.append("此前真实坐席已做动作：" + "、".join(_eval_act_label(act) for act in spoken_acts))
    narrative.append("若客户正在回答上一句坐席提问，应使用该回答推进下一步；若客户只是确认/致谢，应收束或确认处理结果。")
    return {
        "last_agent_reply": last_agent_reply,
        "last_agent_act": last_agent_act,
        "target_act": target_act,
        "stage": stage,
        "prior_skill": prior_skill,
        "spoken_acts": spoken_acts,
        "slots": slots,
        "summary": "；".join(narrative[-4:]),
        "narrative_summary": "\n".join(narrative),
    }


def _eval_last_assistant_reply(context_messages: list[dict[str, Any]]) -> str:
    block: list[str] = []
    for item in reversed(context_messages):
        if item.get("role") == "assistant":
            block.append(str(item.get("content") or ""))
        elif block:
            break
    return "\n".join(reversed(block)).strip()


def _eval_spoken_acts(context_messages: list[dict[str, Any]]) -> list[str]:
    acts: list[str] = []
    for item in context_messages:
        if item.get("role") != "assistant":
            continue
        act = _eval_assistant_act(str(item.get("content") or ""))
        if act and act not in acts:
            acts.append(act)
    return acts


def _eval_assistant_act(text: str) -> str:
    if not text:
        return ""
    if any(token in text for token in ("什么原因导致", "无法还款", "什么原因")):
        return "ask_overdue_reason"
    if "信息安全" in text and ("提供" in text or "核实" in text):
        return "identity_prompt"
    if any(token in text for token in ("稍微等等", "查清楚", "努力的处理")):
        return "processing_wait"
    if any(token in text for token in ("家人朋友", "周转一下", "及时还款导致逾期")):
        return "ask_funding_source"
    if any(token in text for token in ("担心电话打扰", "担心电话", "打扰是吗")):
        return "ask_stop_call_confirm"
    if any(token in text for token in ("申请停呼", "申请停催", "停呼本人", "联系人两天")):
        return "submit_stop_collection"
    if any(token in text for token in ("申请好了", "处理好了", "已经申请")):
        return "stop_collection_done"
    if "您看可以吗" in text:
        return "ask_confirm"
    if any(token in text for token in ("五星好评", "好评")):
        return "request_rating"
    if any(token in text for token in ("客气", "谢谢")):
        return "thanks_response"
    if any(token in text for token in ("有什么可以帮", "可以帮您")):
        return "opening_question"
    return "assistant_reply"


def _eval_user_act(text: str) -> str:
    q = str(text or "").strip()
    if not q:
        return ""
    if q in {"你好", "您好", "喂", "在吗"}:
        return "greeting"
    if q in {"对", "对的", "嗯", "好的", "好", "可以", "行"}:
        return "affirm"
    if any(token in q for token in ("感谢", "谢谢", "辛苦")):
        return "thanks"
    if any(token in q for token in ("不要继续电话", "不要再打", "别打电话", "电话信息", "催收电话", "停催", "停呼")):
        return "stop_call_request"
    if any(token in q for token in ("延期", "周五", "晚点还", "协商", "还上", "周转", "款想")):
        return "repayment_negotiation"
    if len(q) <= 12 and any(token in q for token in ("公司", "事项", "困难", "工资", "拖欠", "没钱")):
        return "reason_or_fragment"
    return "customer_reply"


def _eval_flow_stage(
    context_messages: list[dict[str, Any]],
    last_agent_act: str,
    target_act: str,
) -> str:
    if last_agent_act == "ask_stop_call_confirm":
        return "stop_collection.confirming_need"
    if last_agent_act == "submit_stop_collection":
        return "stop_collection.submitted_waiting_customer_confirm"
    if last_agent_act == "stop_collection_done":
        return "stop_collection.done_closing"
    if last_agent_act == "ask_overdue_reason":
        return "overdue_negotiation.collecting_reason"
    if last_agent_act == "ask_funding_source":
        return "overdue_negotiation.collecting_funding_source_or_stop_request"
    if last_agent_act in {"identity_prompt", "processing_wait"}:
        return "identity.display_or_querying"
    if target_act == "stop_call_request":
        return "stop_collection.requested"
    if target_act == "repayment_negotiation":
        if any(_eval_assistant_act(str(item.get("content") or "")) == "identity_prompt" for item in context_messages):
            return "overdue_negotiation.in_progress"
        return "identity.display_needed_before_business"
    if target_act in {"affirm", "thanks"}:
        return "closing_or_confirmation"
    return "general"


def _eval_context_slots(
    context_messages: list[dict[str, Any]],
    target_text: str,
    last_agent_act: str,
    target_act: str,
    stage: str,
) -> dict[str, Any]:
    history_text = "\n".join(str(item.get("content") or "") for item in context_messages)
    combined = f"{history_text}\n{target_text}"
    history_acts = [
        _eval_assistant_act(str(item.get("content") or ""))
        for item in context_messages
        if item.get("role") == "assistant"
    ]
    identity_already_displayed = any(
        act in {"identity_prompt", "processing_wait", "ask_overdue_reason"}
        for act in history_acts
    )
    slots: dict[str, Any] = {
        "eval_last_agent_act": last_agent_act,
        "eval_target_user_act": target_act,
        "eval_flow_stage": stage,
        "eval_previous_agent_reply": _eval_last_assistant_reply(context_messages),
        "eval_no_business_operation_claim": True,
        "eval_operation_boundary": (
            "话术推荐不能替坐席执行停催、工单、退款等系统操作；"
            "没有明确写操作成功结果时，不得说已处理、已提交、已申请成功或承诺停催时长。"
        ),
        "eval_identity_flow_mode": "display_only_c100",
        "eval_identity_already_displayed": identity_already_displayed,
        "eval_identity_policy": (
            "核身只展示成功流程，不校验输入；不得复述或泄露手机号、身份证号、身份证后四位。"
            "历史真实坐席已展示过核身后，后续推荐不得再次核身。"
        ),
    }
    if "周五" in combined:
        slots["repayment_time"] = "周五"
        slots["mentioned_repayment_time"] = "周五"
    if any(token in combined for token in ("公司", "事项", "困难", "拖欠", "工资")):
        slots["overdue_reason"] = _eval_reason_text(target_text)
    if any(token in combined for token in ("不要继续电话", "别打电话", "电话信息", "催收电话", "停催", "停呼")):
        slots["customer_requests_stop_collection"] = True
        slots["target"] = "self"
    if stage.startswith("stop_collection"):
        slots.setdefault("target", "self")
        if any(token in combined for token in ("两天", "2天", "二天")):
            slots["eval_reference_stop_days_mentioned"] = 2
    if stage in {"stop_collection.submitted_waiting_customer_confirm", "stop_collection.done_closing"}:
        slots["eval_real_agent_stop_request_progressed"] = True
    if stage == "identity.display_needed_before_business":
        slots["eval_identity_display_needed"] = True
    if identity_already_displayed:
        slots["eval_skip_identity_generation"] = True
    return slots


def _eval_reason_text(text: str) -> str:
    cleaned = str(text or "").strip()
    return cleaned[:40] if cleaned else "客户表示暂时资金周转困难"


def _eval_prior_skill(
    prior_turns: list[dict[str, Any]],
    context_messages: list[dict[str, Any]],
    dialogue_context: dict[str, Any],
    target_text: str,
) -> str:
    last_agent_act = str(dialogue_context.get("last_agent_act") or "")
    target_act = str(dialogue_context.get("target_act") or _eval_user_act(target_text))
    if last_agent_act in {"ask_stop_call_confirm", "submit_stop_collection", "stop_collection_done"}:
        return "stop_collection"
    if target_act == "stop_call_request":
        return "stop_collection"
    session_flow = set(_load_eval_intent_config().get("session_flow_skills") or [])
    for turn in reversed(prior_turns):
        sid = str(turn.get("matched_skill_id") or "")
        if sid and sid not in session_flow:
            if target_act in {"affirm", "thanks", "reason_or_fragment"}:
                return sid
            if sid == "stop_collection" and target_act in {"repayment_negotiation", "customer_reply"}:
                return sid
            return sid
    recent = "\n".join(str(item.get("content") or "") for item in context_messages[-6:])
    if any(token in f"{recent}\n{target_text}" for token in ("延期", "协商", "周五还", "周转", "还不上")):
        return "overdue_negotiation"
    return ""


def _eval_turn_in_skill(prior_turns: list[dict[str, Any]], skill_id: str) -> int:
    count = 0
    for turn in reversed(prior_turns):
        if turn.get("matched_skill_id") == skill_id:
            count += 1
        elif count:
            break
    return max(1, min(count + 1, 2))


def _eval_skill_name(skill_id: str) -> str:
    if skill_id == "overdue_negotiation":
        return "协商还款"
    if skill_id == "stop_collection":
        return "要求停催"
    return skill_id or "无"


def _eval_act_label(act: str) -> str:
    return {
        "identity_prompt": "核身引导",
        "processing_wait": "查询等待",
        "ask_overdue_reason": "询问无法还款原因",
        "ask_funding_source": "询问周转来源",
        "ask_stop_call_confirm": "确认是否担心电话打扰",
        "submit_stop_collection": "提出申请停呼/停催",
        "stop_collection_done": "停催申请完成",
        "ask_confirm": "请求客户确认",
        "request_rating": "请求评价",
        "thanks_response": "回应感谢",
        "opening_question": "开场询问诉求",
        "greeting": "问候",
        "affirm": "确认/肯定",
        "thanks": "感谢",
        "stop_call_request": "要求停止电话/信息",
        "repayment_negotiation": "延期/协商还款诉求",
        "reason_or_fragment": "原因/补充片段",
        "customer_reply": "客户补充",
        "assistant_reply": "坐席回复",
    }.get(act, act or "无")


def _eval_stage_label(stage: str) -> str:
    return {
        "stop_collection.confirming_need": "停催诉求确认中",
        "stop_collection.submitted_waiting_customer_confirm": "已提出停催申请，等待客户确认",
        "stop_collection.done_closing": "停催已完成，进入收尾",
        "overdue_negotiation.collecting_reason": "协商还款中，客户正在说明困难原因",
        "overdue_negotiation.collecting_funding_source_or_stop_request": "已提示征信费用，等待客户补充周转/停催诉求",
        "identity.display_or_querying": "核身展示或查询等待中",
        "stop_collection.requested": "客户提出停止电话/信息诉求",
        "overdue_negotiation.in_progress": "协商还款流程中",
        "identity.display_needed_before_business": "初次账户类诉求，需先展示核身成功流程",
        "closing_or_confirmation": "客户确认或感谢，适合收束",
        "general": "普通对话",
    }.get(stage, stage or "未知")


def _eval_job_cancelled(job_id: str) -> bool:
    job = get_demo_store().get_eval_job(job_id)
    return bool(job and job.get("cancelled"))


def _eval_job_detail(job: dict[str, Any], store: Any) -> dict[str, Any]:
    config = job.get("config") or {}
    txt_ids = list(config.get("txt_file_ids") or [])
    files_by_id = {file["txt_id"]: file for file in store.list_eval_txt_files()}
    runs_by_txt = {
        run["txt_id"]: run
        for run in store.list_eval_runs(llm_profile_id=job.get("llm_profile_id") or None)
        if run.get("job_id") == job.get("job_id")
    }
    progress: list[dict[str, Any]] = []
    for txt_id in txt_ids:
        file = files_by_id.get(txt_id)
        run = runs_by_txt.get(txt_id)
        if run:
            progress.append({
                "txt_id": txt_id,
                "filename": file["filename"] if file else txt_id,
                "llm_profile_id": run["llm_profile_id"],
                "status": run["status"],
                "total_turns": run["total_turns"],
                "generated_turns": run["generated_turns"],
                "failed_turns": run["failed_turns"],
                "accepted_turns": run["accepted_turns"],
                "rejected_turns": run["rejected_turns"],
                "main_intent": run.get("main_intent") or {},
                "error": run.get("error") or "",
                "updated_at": run.get("updated_at") or "",
            })
        else:
            messages = file.get("messages", []) if file else []
            progress.append({
                "txt_id": txt_id,
                "filename": file["filename"] if file else txt_id,
                "llm_profile_id": job.get("llm_profile_id") or "",
                "status": "pending",
                "total_turns": len(_eval_user_messages(messages)),
                "generated_turns": 0,
                "failed_turns": 0,
                "accepted_turns": 0,
                "rejected_turns": 0,
                "main_intent": {},
                "error": "TXT 已删除" if not file else "",
                "updated_at": "",
            })
    out = dict(job)
    out["file_progress"] = progress
    return out


def _load_eval_intent_config() -> dict[str, Any]:
    path = get_settings().resolve_path("config/eval_intent_mapping.json")
    config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    source = str(config.get("source") or "").strip()
    if source:
        source_path = get_settings().resolve_path(source)
        if source_path.exists():
            merged = _eval_intent_config_from_mapping(source_path)
            merged["session_flow_skills"] = config.get("session_flow_skills") or merged.get("session_flow_skills") or []
            merged["source"] = source
            return merged
    config.setdefault("session_flow_skills", [])
    config.setdefault("skill_to_intent", {})
    config.setdefault("skill_to_intents", {})
    config.setdefault("intent_options", [])
    return config


def _eval_intent_config_from_mapping(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mappings = data.get("mappings") or []
    intent_options: list[dict[str, Any]] = []
    seen_l2: set[str] = set()
    skill_to_intents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in mappings:
        intent = _intent_from_label(str(item.get("intent") or ""))
        if not intent:
            continue
        intent["notes"] = str(item.get("notes") or "")
        skill_ids = [str(skill_id).strip() for skill_id in item.get("skill_ids") or [] if str(skill_id).strip()]
        intent["skill_ids"] = skill_ids
        if intent["l2"] not in seen_l2:
            intent_options.append(dict(intent))
            seen_l2.add(intent["l2"])
        for skill_id in skill_ids:
            skill_to_intents[skill_id].append(dict(intent))
    skill_to_intent = {
        skill_id: intents[0]
        for skill_id, intents in skill_to_intents.items()
        if intents
    }
    return {
        "source": str(path),
        "session_flow_skills": [],
        "skill_to_intent": skill_to_intent,
        "skill_to_intents": dict(skill_to_intents),
        "intent_options": intent_options,
    }


def _intent_from_label(label: str) -> dict[str, Any]:
    raw = str(label or "").strip()
    if not raw:
        return {}
    if "/" in raw:
        l1, l2 = raw.split("/", 1)
    else:
        l1, l2 = "", raw
    return {"l1": l1.strip(), "l2": l2.strip(), "label": raw}


def _map_skill_to_intent(skill_id: str) -> dict[str, Any]:
    if not skill_id:
        return {}
    config = _load_eval_intent_config()
    return dict(config.get("skill_to_intent", {}).get(skill_id, {}))


def _eval_intent_options() -> list[dict[str, Any]]:
    config = _load_eval_intent_config()
    by_l2: dict[str, dict[str, Any]] = {}
    for intent in config.get("intent_options") or []:
        l2 = str(intent.get("l2") or "")
        if not l2:
            continue
        by_l2.setdefault(l2, {
            "l1": str(intent.get("l1") or ""),
            "l2": l2,
            "label": str(intent.get("label") or l2),
            "skill_ids": list(intent.get("skill_ids") or []),
            "notes": str(intent.get("notes") or ""),
        })
    for intent in (config.get("skill_to_intent") or {}).values():
        l2 = str(intent.get("l2") or "")
        if not l2:
            continue
        by_l2.setdefault(l2, {
            "l1": str(intent.get("l1") or ""),
            "l2": l2,
            "label": str(intent.get("label") or l2),
        })
    return sorted(by_l2.values(), key=lambda item: (item["l1"], item["l2"]))


def _intent_by_l2(intent_l2: str) -> dict[str, Any]:
    target = str(intent_l2 or "").strip()
    if not target:
        return {}
    for intent in _eval_intent_options():
        if intent.get("l2") == target:
            return dict(intent)
    return {"l1": "人工纠正", "l2": target, "label": target}


def _rank_main_skill(turns: list[dict[str, Any]]) -> str:
    config = _load_eval_intent_config()
    session_flow = set(config.get("session_flow_skills") or [])
    counts: Counter[str] = Counter()
    confidence_sum: defaultdict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    for idx, turn in enumerate(turns):
        sid = turn.get("matched_skill_id") or ""
        if not sid or sid in session_flow:
            continue
        counts[sid] += 1
        confidence_sum[sid] += float((turn.get("response") or {}).get("confidence") or 0)
        first_seen.setdefault(sid, idx)
    ranked = sorted(
        counts,
        key=lambda sid: (
            -counts[sid],
            -(confidence_sum[sid] / counts[sid] if counts[sid] else 0),
            first_seen[sid],
            sid,
        ),
    )
    return ranked[0] if ranked else ""


def _build_eval_analytics(
    *,
    llm_profile_id: str = "",
    intent_l2: str = "",
    status: str = "",
    badcase_only: bool = False,
) -> dict[str, Any]:
    store = get_demo_store()
    files_by_id = {file["txt_id"]: file for file in store.list_eval_txt_files()}
    badcase_txt_ids = {txt_id for txt_id, file in files_by_id.items() if file.get("badcase")}
    runs = store.list_eval_runs(llm_profile_id=llm_profile_id or None)
    if intent_l2:
        runs = [run for run in runs if _effective_intent(run).get("l2") == intent_l2]
    if status:
        runs = [run for run in runs if run.get("status") == status]
    if badcase_only:
        runs = [run for run in runs if run.get("txt_id") in badcase_txt_ids]
    scoped_txt_ids = {run["txt_id"] for run in runs}
    txt_badcases = [
        file for file in files_by_id.values()
        if file.get("badcase") and file.get("txt_id") in scoped_txt_ids
    ]
    all_turns = []
    for run in runs:
        turns = store.list_eval_turn_results(run["run_id"])
        all_turns.extend({**turn, "run": run} for turn in turns)
    rated = [turn for turn in all_turns if (turn.get("annotation") or {}).get("accepted") is not None]
    accepted = [turn for turn in rated if turn["annotation"].get("accepted") is True]
    failed = [turn for turn in all_turns if turn.get("status") == "error"]
    problem_turns = [turn for turn in all_turns if _turn_has_problem(turn)]
    low_acceptance_runs = [
        {**run, "filename": files_by_id.get(run["txt_id"], {}).get("filename", "")}
        for run in runs
        if _run_is_low_acceptance(run)
    ]
    reason_counts: Counter[str] = Counter()
    for turn in all_turns:
        if turn.get("annotation", {}).get("accepted") is False:
            reason_counts.update(turn.get("annotation", {}).get("reject_reasons") or ["未填写原因"])
    return {
        "summary": {
            "txt_count": len({run["txt_id"] for run in runs}),
            "run_count": len(runs),
            "turn_count": len(all_turns),
            "generated_count": len([turn for turn in all_turns if turn.get("status") == "success"]),
            "failed_count": len(failed),
            "rated_count": len(rated),
            "accepted_count": len(accepted),
            "acceptance_rate": (len(accepted) / len(rated)) if rated else None,
            "badcase_count": len(txt_badcases),
            "problem_turn_count": len(problem_turns),
            "low_acceptance_count": len(low_acceptance_runs),
            "intent_error_count": len([run for run in runs if run.get("intent_error")]),
            "route_accuracy": _route_accuracy(runs),
            "avg_latency_ms": _avg([turn.get("latency_ms") or 0 for turn in all_turns]),
        },
        "by_model": _aggregate_turns(all_turns, lambda turn: turn["run"]["llm_profile_id"], files_by_id),
        "by_intent": _aggregate_turns(
            all_turns,
            lambda turn: _effective_intent(turn["run"]).get("l2") or "未分类",
            files_by_id,
        ),
        "intent_errors": [
            {**run, "filename": files_by_id.get(run["txt_id"], {}).get("filename", "")}
            for run in runs
            if run.get("intent_error")
        ][:100],
        "reject_reasons": [{"reason": key, "count": value} for key, value in reason_counts.most_common()],
        "txt_badcases": txt_badcases[:100],
        "problem_turns": problem_turns[:100],
        "low_acceptance_runs": low_acceptance_runs[:100],
        "failures": failed[:100],
    }


def _aggregate_turns(
    turns: list[dict[str, Any]],
    key_fn,
    files_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for turn in turns:
        buckets[key_fn(turn)].append(turn)
    out = []
    for key, items in buckets.items():
        rated = [turn for turn in items if turn.get("annotation", {}).get("accepted") is not None]
        accepted = [turn for turn in rated if turn.get("annotation", {}).get("accepted") is True]
        txt_badcase_count = len({
            turn["run"]["txt_id"]
            for turn in items
            if files_by_id.get(turn["run"]["txt_id"], {}).get("badcase")
        })
        out.append({
            "name": key,
            "turn_count": len(items),
            "rated_count": len(rated),
            "accepted_count": len(accepted),
            "acceptance_rate": (len(accepted) / len(rated)) if rated else None,
            "failed_count": len([turn for turn in items if turn.get("status") == "error"]),
            "issue_count": len([turn for turn in items if _turn_has_problem(turn)]),
            "badcase_count": txt_badcase_count,
            "intent_error_count": len({turn["run"]["run_id"] for turn in items if turn["run"].get("intent_error")}),
            "avg_latency_ms": _avg([turn.get("latency_ms") or 0 for turn in items]),
        })
    return sorted(out, key=lambda row: (-row["turn_count"], row["name"]))


def _effective_intent(run: dict[str, Any]) -> dict[str, Any]:
    if run.get("intent_error") and (run.get("corrected_intent") or {}).get("l2"):
        return run.get("corrected_intent") or {}
    return run.get("main_intent") or {}


def _route_accuracy(runs: list[dict[str, Any]]) -> float | None:
    generated_runs = [
        run for run in runs
        if int(run.get("generated_turns") or 0) > 0 or run.get("status") in {"completed", "partial_failed"}
    ]
    if not generated_runs:
        return None
    accurate = len([run for run in generated_runs if not run.get("intent_error")])
    return accurate / len(generated_runs)


def _turn_has_problem(turn: dict[str, Any]) -> bool:
    annotation = turn.get("annotation") or {}
    return bool(annotation.get("accepted") is False or turn.get("status") == "error")


def _run_is_low_acceptance(run: dict[str, Any]) -> bool:
    rated = int(run.get("accepted_turns") or 0) + int(run.get("rejected_turns") or 0)
    if rated < 3:
        return False
    return (int(run.get("accepted_turns") or 0) / rated) < 0.5


def _avg(values: list[float]) -> float:
    values = [float(value or 0) for value in values if value]
    return round(sum(values) / len(values), 2) if values else 0


def _resource_meta_or_404(resource: str):
    meta = RESOURCE_META.get(resource)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"unknown resource: {resource}")
    return meta


def _meta_response(resource: str, meta) -> dict[str, Any]:
    return {
        "name": resource,
        "label": meta.label,
        "kind": meta.kind,
        "id_field": meta.id_field,
    }


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _chunk_text(text: str, size: int = 8):
    for start in range(0, len(text), size):
        yield text[start:start + size]


def _file_status(path: Path, yaml_count: Path | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "ok" if path.exists() else "missing",
        "path": path.name,
    }
    if path.exists():
        out["bytes"] = path.stat().st_size
    if yaml_count:
        out["definition_count"] = len(list(yaml_count.glob("*.yaml")))
    return out


def _llm_profile_or_default(profile_id: str = "") -> LLMProfile:
    profiles, default_id = load_llm_profiles(get_settings())
    by_id = {profile.id: profile for profile in profiles}
    return by_id.get(profile_id) or by_id[default_id]


def _llm_profile_or_404(profile_id: str) -> LLMProfile:
    profiles, _default_id = load_llm_profiles(get_settings())
    by_id = {profile.id: profile for profile in profiles}
    profile = by_id.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"unknown llm profile: {profile_id}")
    return profile


def _runtime_llm_status(profile_id: str) -> dict[str, Any]:
    try:
        llm_client = get_llm_client()
        last_call = llm_client.last_call_status(profile_id)
        return {
            "runtime_client": {"status": "ready"},
            "last_call": last_call,
        }
    except HTTPException as exc:
        return {
            "runtime_client": {"status": "not_initialized", "detail": exc.detail},
            "last_call": {
                "status": "not_called",
                "error": "",
                "status_code": None,
                "updated_at": "",
            },
        }


async def _probe_llm(profile: LLMProfile) -> dict[str, Any]:
    payload = {
        "model": profile.model,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "max_tokens": 4,
    }
    try:
        async with httpx.AsyncClient(
            base_url=profile.api_url,
            headers={"Authorization": f"Bearer {profile.api_key}"},
            timeout=min(profile.timeout, 8.0),
        ) as client:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        return {
            "status": "ok",
            "api_url": profile.api_url,
            "model": profile.model,
            "profile_id": profile.id,
        }
    except Exception as exc:
        return {
            "status": "error",
            "api_url": profile.api_url,
            "model": profile.model,
            "profile_id": profile.id,
            "error": _error_summary(exc),
        }


def _error_summary(exc: Exception) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


async def _probe_embedding(settings) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                settings.EMBED_API_URL,
                json={"model": settings.EMBED_MODEL, "input": "ping"},
            )
            resp.raise_for_status()
        return {
            "status": "ok",
            "api_url": settings.EMBED_API_URL,
            "model": settings.EMBED_MODEL,
        }
    except Exception as exc:
        return {
            "status": "error",
            "api_url": settings.EMBED_API_URL,
            "model": settings.EMBED_MODEL,
            "error": str(exc),
        }
