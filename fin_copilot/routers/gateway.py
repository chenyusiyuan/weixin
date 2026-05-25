"""FastAPI route handlers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fin_copilot.config import get_settings
from fin_copilot.llm.profiles import (
    get_llm_profile,
    reset_active_llm_profile,
    set_active_llm_profile,
)

router = APIRouter()

# Will be set by main.py lifespan
_orchestrator = None
_llm_client = None


def set_orchestrator(orch: Any) -> None:
    global _orchestrator
    _orchestrator = orch


def set_llm_client(client: Any) -> None:
    global _llm_client
    _llm_client = client


def get_orchestrator():
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _orchestrator


def get_llm_client():
    if _llm_client is None:
        raise HTTPException(status_code=503, detail="LLM client not initialized")
    return _llm_client


class ChatRequest(BaseModel):
    session_id: str
    user_text: str
    channel: str = "online"
    customer_id: str = ""
    llm_profile_id: str = ""


@router.post("/api/chat")
async def chat(req: ChatRequest):
    orch = get_orchestrator()
    profile = get_llm_profile(req.llm_profile_id, get_settings())
    token = set_active_llm_profile(profile)
    try:
        response = await orch.handle_turn(
            session_id=req.session_id,
            user_query=req.user_text,
        )
    finally:
        reset_active_llm_profile(token)
    return response.model_dump()


@router.get("/api/health")
async def health():
    return {"status": "ok"}
