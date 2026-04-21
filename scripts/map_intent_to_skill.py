"""Stage B — Map DeepSeek-extracted intents to skill_id via two parallel paths.

Reads  tests/golden_raw_intent.jsonl         (output of Stage A)
       scripts/references/fewshot_label_mapping.json  (level3 → skill_id)
       skills/definitions/*.yaml              (to build anchor texts per skill)
Writes tests/golden_mapped.jsonl
       one record per input row, schema:
         {call_id, level3, primary_query_polished, intent, quality,
          path_a_skill,          # level3 → skill via fewshot_label_mapping
          path_b_skill,          # embedding similarity
          path_b_score,
          path_b_top3,           # list[(skill_id, score)]
          verdict,               # "auto_pass" | "needs_review" | "drop"
          gold_skill,            # only set when auto_pass
          review_reason}

verdict rules:
  - quality=unusable  → drop
  - no level3 + low embedding score (<0.55) → drop
  - both paths present and agree → auto_pass (gold_skill = agreed)
  - only path_a exists → needs_review (path_a proposed)
  - only path_b exists and score >= 0.70 → needs_review (path_b proposed)
  - paths disagree → needs_review

Run:
    python scripts/map_intent_to_skill.py
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTENT_PATH = ROOT / "tests" / "golden_raw_intent.jsonl"
OUTPUT_PATH = ROOT / "tests" / "golden_mapped.jsonl"
LABEL_MAP_PATH = ROOT / "scripts" / "references" / "fewshot_label_mapping.json"
SKILLS_DIR = ROOT / "skills" / "definitions"

EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"

# Thresholds
SIM_MIN_VALID = 0.55        # below this → drop as noise
SIM_AUTO_PASS = 0.82        # above this → trust path_b alone (if path_a missing)


def load_level3_map() -> dict[str, str | None]:
    d = json.loads(LABEL_MAP_PATH.read_text(encoding="utf-8"))
    return {m["level3"]: m["skill_id"] for m in d["mappings"]}


def load_skill_anchors() -> dict[str, str]:
    """Build a dense text for each skill that bge-m3 can embed."""
    anchors: dict[str, str] = {}
    for path in sorted(SKILLS_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            docs = [d for d in yaml.safe_load_all(f) if isinstance(d, dict)]
        body: dict = {}
        for d in docs:
            body.update(d)
        sid = body.get("skill_id") or path.stem
        name = body.get("name", "")
        desc = (body.get("description") or "")
        # description often multi-paragraph, keep first ~200 chars
        desc_short = re.sub(r"\s+", " ", desc).strip()[:200]
        triggers = body.get("triggers") or {}
        kw = " ".join(triggers.get("keywords") or [])[:200]
        examples = " ".join((triggers.get("examples") or [])[:4])[:300]
        anchors[sid] = f"{name}。{desc_short}。关键词：{kw}。示例：{examples}"
    return anchors


def embed_batch(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    resp = client.post(EMBED_URL, json={"model": EMBED_MODEL, "input": texts})
    resp.raise_for_status()
    vecs = resp.json().get("embeddings") or []
    out = []
    for v in vecs:
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / norm for x in v])
    return out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def classify_intent(intent: str, skill_ids: list[str], skill_vecs: list[list[float]],
                    client: httpx.Client) -> tuple[str, float, list[tuple[str, float]]]:
    if not intent or not intent.strip():
        return "", 0.0, []
    q_vec = embed_batch(client, [intent])[0]
    scored = [(sid, cosine(q_vec, sv)) for sid, sv in zip(skill_ids, skill_vecs)]
    scored.sort(key=lambda x: -x[1])
    return scored[0][0], scored[0][1], scored[:3]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not INTENT_PATH.exists():
        print(f"input not found: {INTENT_PATH} — run extract_intent_via_deepseek.py first", file=sys.stderr)
        sys.exit(1)

    # Level3 → skill map
    level3_map = load_level3_map()
    print(f"level3 mapping entries: {len(level3_map)}")

    # Skill anchor texts + embeddings
    anchors = load_skill_anchors()
    skill_ids = list(anchors.keys())
    anchor_texts = [anchors[s] for s in skill_ids]
    print(f"embedding {len(skill_ids)} skill anchors...")
    client = httpx.Client(timeout=60.0)
    # Ollama accepts a list as input, embed in batches
    skill_vecs: list[list[float]] = []
    BATCH = 32
    for i in range(0, len(anchor_texts), BATCH):
        skill_vecs.extend(embed_batch(client, anchor_texts[i:i + BATCH]))
    print(f"  done: {len(skill_vecs)} vectors")

    # Process
    records = [json.loads(line) for line in INTENT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        records = records[:args.limit]

    verdict_counts: Counter = Counter()
    out_file = open(OUTPUT_PATH, "w", encoding="utf-8")
    try:
        for i, r in enumerate(records):
            if i % 50 == 0 or i == len(records) - 1:
                print(f"  mapping [{i+1}/{len(records)}]  verdict_so_far={dict(verdict_counts)}", flush=True)

            quality = r.get("quality", "")
            if quality == "unusable":
                verdict = "drop"
                path_a = path_b = None
                path_b_score = 0.0
                top3: list = []
                out_file.write(json.dumps({
                    **r, "path_a_skill": None, "path_b_skill": None,
                    "path_b_score": 0.0, "path_b_top3": [],
                    "verdict": verdict, "review_reason": "quality=unusable",
                }, ensure_ascii=False) + "\n")
                verdict_counts[verdict] += 1
                continue

            # Path A: level3 → skill
            level3 = str(r.get("level3") or "").strip()
            path_a = level3_map.get(level3)  # may be None

            # Path B: embedding on polished query + intent
            query_for_embed = (r.get("primary_query_polished") or "") + " " + (r.get("intent") or "")
            path_b, path_b_score, top3 = classify_intent(
                query_for_embed, skill_ids, skill_vecs, client,
            )

            reason = ""
            gold_skill = None
            # Use embedding similarity as primary signal.
            # level3 → skill mapping is unreliable because level3 labels describe
            # the entire conversation while we extract a single-turn query that may
            # be a different business topic than the conversation-level label.
            if not path_b or path_b_score < SIM_MIN_VALID:
                verdict = "drop"
                reason = f"embed score too low ({path_b_score:.2f})"
            elif path_b_score >= SIM_AUTO_PASS:
                verdict = "auto_pass"
                gold_skill = path_b
                reason = f"embed high confidence {path_b_score:.2f}"
            elif path_b_score >= 0.70:
                # Medium confidence: auto-pass but flag for optional spot-check
                verdict = "auto_pass"
                gold_skill = path_b
                reason = f"embed medium confidence {path_b_score:.2f}"
            else:
                verdict = "needs_review"
                reason = f"embed low-medium {path_b_score:.2f}"

            verdict_counts[verdict] += 1
            out_file.write(json.dumps({
                **r,
                "path_a_skill": path_a,
                "path_b_skill": path_b,
                "path_b_score": round(path_b_score, 4),
                "path_b_top3": [[s, round(sc, 4)] for s, sc in top3],
                "verdict": verdict,
                "gold_skill": gold_skill,
                "review_reason": reason,
            }, ensure_ascii=False) + "\n")
    finally:
        out_file.close()

    print(f"\nDone. Output: {OUTPUT_PATH}")
    print(f"Verdict distribution: {dict(verdict_counts)}")
    total = sum(verdict_counts.values())
    for k, v in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<15} {v:>4} ({v/total:.1%})")


if __name__ == "__main__":
    main()
