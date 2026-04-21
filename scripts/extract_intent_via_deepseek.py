"""Stage A — Extract + polish primary business-intent query from each dialog via DeepSeek.

Input:
  - raw_data.csv (3000 dialogs)
  - 清洗后数据1.xlsx / 清洗后数据2.xlsx (303, already merged in raw)
  - test.jsonl (98, already merged in raw)
All are union-deduped on call_id; we process 3000 unique dialogs.

Output:
  - tests/golden_raw_intent.jsonl
    One line per dialog, schema:
      {call_id, level3, primary_query_raw, primary_query_polished,
       intent, confidence, quality, reason?}
    `quality ∈ {"clear", "noisy", "unusable"}` — from DeepSeek's self-assessment.

Run:
    python scripts/extract_intent_via_deepseek.py                 # all 3000
    python scripts/extract_intent_via_deepseek.py --limit 50      # smoke
    python scripts/extract_intent_via_deepseek.py --concurrency 8 # default 8
    python scripts/extract_intent_via_deepseek.py --resume        # skip rows already in output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.config import get_settings  # noqa: E402
from fin_copilot.llm.client import LLMClient  # noqa: E402

RAW_CSV = ROOT / "raw_data.csv"
OUTPUT_PATH = ROOT / "tests" / "golden_raw_intent.jsonl"

EXTRACT_PROMPT = """你是金融客服对话分析专家。请从下面一段客户与客服的通话记录中，提取**客户的首个核心业务诉求**。

要求：
1. 忽略寒暄（喂/你好/早上好）、身份核验回答（姓名/银行卡/身份证号）、简单应答（嗯/对/好的）、通道确认（能听到吗）。
2. 找到客户第一次真正表达业务诉求的那句话（如"想协商还款"、"想查账单"、"要求退费"等）。
3. 对客户原话做**清晰化润色**：修正口语化、方言、倒装、重复、省略，形成一句清晰明确的 query。但**不得添加原文没有的业务细节**。
4. 用一段规范化的 `intent` 概括诉求，如"客户要求提前结清贷款"、"客户投诉催收频繁骚扰"。
5. 评估质量：
   - `clear`：原文语义明确，润色后可靠
   - `noisy`：原文有口语/方言/残缺，润色属推测但仍可用
   - `unusable`：原文完全无法识别业务诉求（纯寒暄/杂音/无关）

严格输出 JSON，不要解释：

```json
{
  "primary_query_raw": "<客户原话，1-2 句>",
  "primary_query_polished": "<润色后的清晰 query>",
  "intent": "<规范化诉求概括>",
  "quality": "clear" | "noisy" | "unusable",
  "confidence": 0.0-1.0,
  "reason": "<仅当 quality=unusable 时填写原因>"
}
```

通话记录：
"""


def load_dialogs() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    return df


def load_processed_call_ids() -> set[str]:
    if not OUTPUT_PATH.exists():
        return set()
    ids: set[str] = set()
    for line in OUTPUT_PATH.read_text(encoding="utf-8").splitlines():
        try:
            ids.add(json.loads(line)["call_id"])
        except Exception:
            continue
    return ids


def normalise_dialog(text: str, max_chars: int = 2500) -> str:
    """xlsx/csv dialogs use '\n' between turns already. Just truncate if huge."""
    if not isinstance(text, str):
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n[...截断]"
    return text


def parse_response(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def process_one(
    llm: LLMClient, sem: asyncio.Semaphore, row: dict,
) -> dict | None:
    dialog = normalise_dialog(row.get("完整对话_清洗后") or row.get("完整对话_原始") or "")
    if len(dialog) < 30:
        return {
            "call_id": row["call_id"],
            "level3": row.get("小结名称"),
            "quality": "unusable",
            "reason": "dialog too short",
        }
    prompt = EXTRACT_PROMPT + dialog
    async with sem:
        try:
            raw = await llm.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            return {"call_id": row["call_id"], "level3": row.get("小结名称"),
                    "quality": "unusable", "reason": f"llm error: {exc}"}
    parsed = parse_response(raw)
    if not parsed:
        return {"call_id": row["call_id"], "level3": row.get("小结名称"),
                "quality": "unusable", "reason": "parse error"}
    return {
        "call_id": row["call_id"],
        "level3": row.get("小结名称"),
        **parsed,
    }


async def run(limit: int | None, concurrency: int, resume: bool) -> None:
    settings = get_settings()
    llm = LLMClient(
        base_url=settings.LLM_API_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        timeout=60.0,
    )

    df = load_dialogs()
    rows = df.to_dict(orient="records")
    if limit is not None:
        rows = rows[:limit]

    processed = load_processed_call_ids() if resume else set()
    pending = [r for r in rows if r["call_id"] not in processed]

    print(f"total dialogs: {len(rows)}, already processed: {len(processed)}, pending: {len(pending)}")
    if not pending:
        print("nothing to do")
        return

    sem = asyncio.Semaphore(concurrency)
    out_file = open(OUTPUT_PATH, "a", encoding="utf-8")
    try:
        start = time.monotonic()
        completed = 0
        last_report = start

        tasks = [asyncio.create_task(process_one(llm, sem, r)) for r in pending]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                out_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_file.flush()
            completed += 1
            now = time.monotonic()
            # Progress update every ~3s or every 20 items
            if now - last_report >= 3.0 or completed % 20 == 0 or completed == len(pending):
                elapsed = now - start
                rate = completed / elapsed if elapsed else 0.0
                eta = (len(pending) - completed) / rate if rate else 0.0
                print(
                    f"  [{completed}/{len(pending)}]  "
                    f"elapsed={elapsed:6.1f}s  rate={rate:5.2f}/s  "
                    f"eta={eta/60:.1f}min",
                    flush=True,
                )
                last_report = now
    finally:
        out_file.close()
        total = time.monotonic() - start
        print(f"\ndone: {completed} records in {total:.1f}s ({completed/total:.2f}/s)")
        print(f"output: {OUTPUT_PATH}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--resume", action="store_true",
                    help="skip call_ids already present in the output file")
    args = ap.parse_args()
    asyncio.run(run(args.limit, args.concurrency, args.resume))


if __name__ == "__main__":
    main()
