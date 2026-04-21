"""Tool execution result model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCallResult(BaseModel):
    """Mirrors the return type of tools.executor.execute_tools."""

    tool_results: dict[str, Any] = Field(default_factory=dict)
    execution_status: str = "success"  # success | partial_failure | failure
    failed_tools: list[str] = Field(default_factory=list)
