"""Interactive CLI demo for the Financial Copilot."""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Enable readline for proper terminal input (backspace, arrow keys)
try:
    import readline  # noqa: F401
except ImportError:
    pass

from fin_copilot.config import get_settings
from fin_copilot.main import build_orchestrator


async def _async_input(prompt: str) -> str:
    """Run input() in a thread so readline works properly under asyncio."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def main() -> None:
    settings = get_settings()
    orchestrator, llm_client = build_orchestrator(settings)
    session_id = f"cli-{uuid.uuid4().hex[:8]}"

    print("=" * 60)
    print("  金融客服 Copilot CLI Demo")
    print("  输入客户消息，查看推荐话术")
    print("  输入 'quit' 退出")
    print("=" * 60)

    try:
        while True:
            try:
                query = (await _async_input("\n[客户] ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if query.lower() in ("quit", "exit", "q"):
                break
            if not query:
                continue

            response = await orchestrator.handle_turn(session_id, query)

            print(f"\n[Copilot] {response.answer}")
            print(f"  ├─ Route: {response.route}")
            print(f"  ├─ Skill: {response.matched_skill_id or '-'}")
            print(f"  ├─ Confidence: {response.confidence:.2f}")
            print(f"  ├─ Latency: {response.latency_ms:.0f}ms")
            print(f"  ├─ Compliance: {'✓' if response.compliance_passed else '✗'}")
            if response.next_step_hint:
                print(f"  ├─ Next Step: {response.next_step_hint}")
            if response.warning:
                print(f"  └─ {response.warning}")
            else:
                print(f"  └─ Trace: {response.trace_id}")
    finally:
        await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
