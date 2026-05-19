"""End-to-end multi-turn scenarios against the live LLM.

Runs 3 multi-turn scripts and prints route / latency / sticky-status / answer
for each turn. No assertions — human-eval friendly output.

Usage:
    python tests/eval/multi_turn_scenarios.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from fin_copilot.config import get_settings
from fin_copilot.main import build_orchestrator


SCENARIOS: list[dict] = [
    {
        "name": "S1 查账单 → 跟进 → 话题切换",
        "session": "e2e-s1",
        "turns": [
            "你好我想查一下账单",
            "我叫张三，手机号13812345678，身份证后四位1234",
            "嗯",                       # 期望 sticky
            "那什么时候扣款",           # 期望 sticky or follow_up
            "换个问题，我想问怎么还款", # 期望 破粘
        ],
    },
    {
        "name": "S2 查额度 → 短确认 → 继续追问",
        "session": "e2e-s2",
        "turns": [
            "我的额度是多少",
            "我叫李四，手机号13900001111，身份证后四位5678",
            "好的",                    # 期望 sticky
            "那额度怎么提",            # 可能 sticky / follow_up
        ],
    },
    {
        "name": "S3 投诉 → 风险触发破粘",
        "session": "e2e-s3",
        "turns": [
            "我要查账单",
            "我叫王五，手机号18600002222，身份证后四位9012",
            "我要投诉你们催收！",     # 风险标签应破粘
        ],
    },
    {
        "name": "S4 单轮携全套身份+业务",
        "session": "e2e-s4",
        "turns": [
            "我叫张三，手机号13812345678，身份证后四位1234，帮我查一下账单",
            "嗯",                       # 期望 sticky(账单 skill)
            "还有什么费用",             # 期望 sticky/route_b 保留在费用域
        ],
    },
    {
        "name": "S5 纯问候 + 业务意图混合",
        "session": "e2e-s5",
        "turns": [
            "你好",                     # 纯问候
            "我想查还款记录",            # 不应被 greeting 吞掉
            "我叫张三 13812345678 1234",  # 主动核身
            "嗯",                       # 期望 sticky
        ],
    },
]


def summarize(resp) -> str:
    ans = (resp.answer or "").replace("\n", " ")
    if len(ans) > 80:
        ans = ans[:80] + "…"
    sticky_tag = "STICKY" if resp.route == "route_a_sticky" else resp.route
    return (
        f"route={sticky_tag:20s} skill={resp.matched_skill_id or '-':28s} "
        f"conf={resp.confidence:.2f} "
        f"lat={resp.latency_ms:6.1f}ms  ans={ans}"
    )


async def run_scenario(orch, scenario: dict) -> dict:
    name = scenario["name"]
    sid = scenario["session"]
    print("\n" + "=" * 90)
    print(f"SCENARIO {name} (session={sid})")
    print("=" * 90)

    stats = {"turns": 0, "sticky_hits": 0, "total_latency": 0.0, "llm_turns": 0}
    for q in scenario["turns"]:
        t0 = time.monotonic()
        resp = await orch.handle_turn(sid, q)
        elapsed = (time.monotonic() - t0) * 1000
        stats["turns"] += 1
        stats["total_latency"] += elapsed
        if resp.route == "route_a_sticky":
            stats["sticky_hits"] += 1
        elif resp.route == "route_b":
            stats["llm_turns"] += 1
        print(f"  客户> {q}")
        print(f"  坐席> {summarize(resp)}")

    # Dump final narrative summary for the human
    state = orch.ctx.get_or_create(sid)
    print(f"  [narrative] {state.narrative_summary!r}")
    print(f"  [intent   ] skill={state.intent.current_skill_id} "
          f"turn_in_skill={state.intent.turn_in_skill} "
          f"total_turns={state.total_turns}")
    return stats


async def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    print(f"LLM URL: {settings.LLM_API_URL}  model: {settings.LLM_MODEL}")
    orch, llm = build_orchestrator(settings)

    all_stats: list[dict] = []
    try:
        for sc in SCENARIOS:
            s = await run_scenario(orch, sc)
            s["name"] = sc["name"]
            all_stats.append(s)
    finally:
        await llm.close()

    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    for s in all_stats:
        avg = s["total_latency"] / max(1, s["turns"])
        print(
            f"{s['name']:45s}  turns={s['turns']}  "
            f"sticky={s['sticky_hits']}  route_b={s['llm_turns']}  "
            f"avg_latency={avg:6.1f}ms"
        )


if __name__ == "__main__":
    asyncio.run(main())
