"""
Parallel tool executor with TTL-based caching.

Usage:
    results = await execute_tools(["get_customer_profile", "get_bill_and_repayment_plan"], state)
"""

import asyncio
import time
import logging
from typing import Any

from tools.registry import TOOL_REGISTRY

logger = logging.getLogger(__name__)


async def execute_tools(
    tool_names: list[str],
    state: dict,
    tool_cache: dict[str, Any] | None = None,
    cache_ttl: int = 300,
) -> dict:
    """
    Execute a list of tools in parallel, with optional TTL caching.

    Cache entries are stored as {"value": ..., "ts": <unix timestamp>}.

    Args:
        tool_names:  Names of tools to execute (must be keys in TOOL_REGISTRY).
        state:       Pipeline state passed verbatim to each tool handler.
        tool_cache:  Mutable dict for caching results across calls.  Pass the
                     same dict object across calls to benefit from caching.
                     Pass None to disable caching.
        cache_ttl:   Seconds before a cached entry is considered stale (default 300).

    Returns:
        {
            "tool_results":       {tool_name: result_dict, ...},
            "execution_status":   "success" | "partial_failure" | "failure",
            "failed_tools":       [tool_name, ...],
        }
    """
    now = time.monotonic()
    tool_results: dict[str, Any] = {}
    failed_tools: list[str] = []

    # ------------------------------------------------------------------ #
    # 1. Resolve cache hits / misses
    # ------------------------------------------------------------------ #
    pending: list[str] = []
    for name in tool_names:
        if tool_cache is not None:
            entry = tool_cache.get(name)
            if entry is not None and (now - entry["ts"]) < cache_ttl:
                tool_results[name] = entry["value"]
                logger.debug("cache hit: %s", name)
                continue
        pending.append(name)

    # ------------------------------------------------------------------ #
    # 2. Parallel-execute uncached tools
    # ------------------------------------------------------------------ #
    if pending:
        handlers = []
        valid_pending: list[str] = []
        for name in pending:
            handler = TOOL_REGISTRY.get(name)
            if handler is None:
                logger.warning("unknown tool requested: %s", name)
                failed_tools.append(name)
            else:
                handlers.append(handler(state))
                valid_pending.append(name)

        if handlers:
            # Wrap each handler with a per-tool 3s timeout
            async def _call_with_timeout(coro, tool_name: str, timeout: float = 3.0):
                try:
                    return await asyncio.wait_for(coro, timeout=timeout)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"tool {tool_name} timed out after {timeout}s")

            wrapped = [
                _call_with_timeout(h, n) for h, n in zip(handlers, valid_pending)
            ]
            outcomes = await asyncio.gather(*wrapped, return_exceptions=True)
            for name, outcome in zip(valid_pending, outcomes):
                if isinstance(outcome, Exception):
                    logger.error("tool %s raised: %s", name, outcome, exc_info=outcome)
                    failed_tools.append(name)
                else:
                    tool_results[name] = outcome
                    if tool_cache is not None:
                        tool_cache[name] = {"value": outcome, "ts": time.monotonic()}

    # ------------------------------------------------------------------ #
    # 3. Determine overall execution status
    # ------------------------------------------------------------------ #
    total = len(tool_names)
    n_failed = len(failed_tools)

    if n_failed == 0:
        execution_status = "success"
    elif n_failed < total:
        execution_status = "partial_failure"
    else:
        execution_status = "failure"

    return {
        "tool_results": tool_results,
        "execution_status": execution_status,
        "failed_tools": failed_tools,
    }
