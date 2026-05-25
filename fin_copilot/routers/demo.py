"""Demo API and static workspace support."""

from __future__ import annotations

import asyncio
import json
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
from fin_copilot.routers.gateway import get_llm_client, get_orchestrator
from tools.registry import TOOL_REGISTRY_META

router = APIRouter(prefix="/api/demo", tags=["demo"])


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
