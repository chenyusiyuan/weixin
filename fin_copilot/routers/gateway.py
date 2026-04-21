"""FastAPI route handlers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Will be set by main.py lifespan
_orchestrator = None


def set_orchestrator(orch: Any) -> None:
    global _orchestrator
    _orchestrator = orch


def get_orchestrator():
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _orchestrator


class ChatRequest(BaseModel):
    session_id: str
    user_text: str
    channel: str = "online"
    customer_id: str = ""


@router.post("/api/chat")
async def chat(req: ChatRequest):
    orch = get_orchestrator()
    response = await orch.handle_turn(
        session_id=req.session_id,
        user_query=req.user_text,
    )
    return response.model_dump()


@router.get("/api/health")
async def health():
    return {"status": "ok"}
