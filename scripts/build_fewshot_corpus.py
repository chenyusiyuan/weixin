"""Build few-shot retrieval corpus from the 303 cleaned dialogs.

Reads `清洗后数据1.xlsx` / `清洗后数据2.xlsx`, dedupes by call_id, extracts
the first business-intent customer utterance from each dialog, maps
`小结名称` → skill_id via scripts/references/fewshot_label_mapping.json,
then embeds every query with bge-m3 (Ollama) and writes a corpus file.

The corpus is a JSON list:
    [{"skill_id": "...", "query": "...", "embedding": [...], "level3": "...", "call_id": "..."}]

Run:
    python scripts/build_fewshot_corpus.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dialog_extract import extract_first_business_intent  # noqa: E402

XLSX_FILES = [
    ROOT / "清洗后数据1.xlsx",
    ROOT / "清洗后数据2.xlsx",
]
MAPPING_PATH = ROOT / "scripts" / "references" / "fewshot_label_mapping.json"
OUTPUT_PATH = ROOT / "scripts" / "references" / "fewshot_corpus.json"

EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"


def build_mapping() -> dict[str, str | None]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {m["level3"]: m["skill_id"] for m in data["mappings"]}


def load_dialogs() -> pd.DataFrame:
    dfs = []
    for path in XLSX_FILES:
        df = pd.read_excel(path, sheet_name="data")
        dfs.append(df)
    combined = pd.concat(dfs).drop_duplicates(subset="call_id", keep="first")
    return combined


def normalise_dialog(dialog_text: str) -> str:
    """xlsx cells use ' | ' as turn separator; our extractor expects newlines."""
    if not isinstance(dialog_text, str):
        return ""
    return dialog_text.replace(" | ", "\n")


def embed_batch(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    resp = client.post(EMBED_URL, json={"model": EMBED_MODEL, "input": texts})
    resp.raise_for_status()
    return resp.json().get("embeddings") or []


def main() -> None:
    mapping = build_mapping()
    df = load_dialogs()
    print(f"loaded {len(df)} dialogs (after dedup)")

    records: list[dict] = []
    skipped_no_label = 0
    skipped_no_query = 0
    for _, row in df.iterrows():
        level3 = str(row.get("小结名称") or "").strip()
        skill_id = mapping.get(level3)
        if not skill_id:
            skipped_no_label += 1
            continue
        dialog = normalise_dialog(row.get("完整对话_清洗后") or row.get("完整对话_原始") or "")
        query = extract_first_business_intent(dialog, k=1)
        if not query or len(query) < 4:
            skipped_no_query += 1
            continue
        records.append({
            "call_id": str(row.get("call_id")),
            "level3": level3,
            "skill_id": skill_id,
            "query": query,
        })

    print(f"records with label+query: {len(records)}")
    print(f"skipped no label: {skipped_no_label}, skipped no query: {skipped_no_query}")

    # Embed in batches of 32
    client = httpx.Client(timeout=60.0)
    batch_size = 32
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        vectors = embed_batch(client, [r["query"] for r in batch])
        for r, v in zip(batch, vectors):
            r["embedding"] = v
        print(f"  embedded {min(i + batch_size, len(records))}/{len(records)}")

    OUTPUT_PATH.write_text(
        json.dumps(records, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nwrote {len(records)} records to {OUTPUT_PATH}")
    print(f"file size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")

    # Per-skill count
    from collections import Counter
    c = Counter(r["skill_id"] for r in records)
    print("\nper-skill distribution (top 20):")
    for sid, n in c.most_common(20):
        print(f"  {n:>3}  {sid}")


if __name__ == "__main__":
    main()
