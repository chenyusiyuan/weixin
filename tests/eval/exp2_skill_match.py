"""Exp 2 — Skill Match Accuracy.

Evaluates the L1 → Skill Router pipeline against gold skill_id labels
from test.jsonl. Gold labels are derived from `服务标签` via
`scripts/references/skill_gold_mapping.json`.

For each call:
  1. Extract first meaningful customer utterance (smart extraction)
  2. Run DomainClassifier or EmbeddingDomainClassifier -> domain
  3. Run SkillRouter (LLM) -> matched_skill_id
  4. Compare against gold

Outputs:
  - Overall Top-1 accuracy
  - Accuracy after excluding calls where L1 domain is wrong (isolates Skill Router quality)
  - Per-risk-level / per-route-mode breakdowns
  - Sample errors

Usage:
    python scripts/eval_skill_match.py --classifier embed --smart
    python scripts/eval_skill_match.py --classifier embed --smart --first-n 3 --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.config import get_settings  # noqa: E402
from fin_copilot.llm.client import LLMClient  # noqa: E402
from fin_copilot.models.conversation import ConversationState, CustomerInfo, IntentState  # noqa: E402
from fin_copilot.routing.domain_classifier import DomainClassifier  # noqa: E402
from fin_copilot.routing.embedding_domain_classifier import EmbeddingDomainClassifier  # noqa: E402
from fin_copilot.routing.fewshot_retriever import FewShotRetriever  # noqa: E402
from fin_copilot.routing.skill_router import SkillRouter  # noqa: E402
from fin_copilot.skills.loader import SkillLoader  # noqa: E402
from scripts.dialog_extract import extract_first_meaningful, extract_first_business_intent  # noqa: E402

TEST_PATH = ROOT / "test.jsonl"
GOLDEN_PATH = ROOT / "tests" / "golden_test.jsonl"
SKILL_GOLD = ROOT / "scripts" / "references" / "skill_gold_mapping.json"
EMBED_CACHE_PATH = ROOT / "tests" / ".embed_topk_cache.json"


def load_embed_cache() -> dict[str, list[list]]:
    if EMBED_CACHE_PATH.exists():
        try:
            return json.loads(EMBED_CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_embed_cache(cache: dict) -> None:
    EMBED_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def load_skill_gold() -> dict[str, str | None]:
    data = json.loads(SKILL_GOLD.read_text(encoding="utf-8"))
    return {m["tag"]: m["skill_id"] for m in data["mappings"]}


def clean_tag(raw) -> str:
    if not isinstance(raw, str):
        return ""
    return raw.strip().strip("`").strip()


def empty_state(session_id: str) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        customer=CustomerInfo(),
        intent=IntentState(),
    )


async def run(
    classifier_kind: str,
    first_n: int,
    extract_mode: str,
    limit: int | None,
    json_out: Path | None,
    multi_domain_k: int,
    use_fewshot: bool,
    fewshot_k: int,
    source: str,
    min_confidence: float,
    router_concurrency: int,
) -> int:
    settings = get_settings()
    skill_gold = load_skill_gold()

    loader = SkillLoader(
        str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
        str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
    )
    llm_client = LLMClient(
        base_url=settings.LLM_API_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        timeout=settings.LLM_TIMEOUT,
    )
    retriever = FewShotRetriever() if use_fewshot else None
    router = SkillRouter(
        llm_client=llm_client,
        skill_loader=loader,
        prompt_path=str(settings.resolve_path(settings.SKILL_PROMPTS_DIR) / "skill_routing.md"),
        fewshot_retriever=retriever,
        fewshot_k=fewshot_k,
    )
    if classifier_kind == "embed":
        domain_clf = EmbeddingDomainClassifier()
    else:
        domain_clf = DomainClassifier()

    # Build skill_id -> (domain, risk_level, route_mode) lookup
    skill_meta: dict[str, dict] = {}
    for sid in loader.get_all_skill_ids():
        s = loader.get_skill(sid)
        if s is not None:
            skill_meta[sid] = {
                "domain": s.domain,
                "risk_level": s.risk_level,
                "route_mode": s.route_mode,
                "name": s.name,
            }

    records: list[dict] = []
    n_done = 0
    if source == "golden":
        data_path = GOLDEN_PATH
        if not data_path.exists():
            print(f"❌ golden source not found: {data_path}")
            return 1
    else:
        data_path = TEST_PATH

    # Phase 1: read + prepare all records (fast, no LLM)
    embed_cache = load_embed_cache() if classifier_kind == "embed" else {}
    cache_hits = 0
    cache_misses = 0
    pending: list[dict] = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            if limit is not None and len(pending) >= limit:
                break
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if source == "golden":
                gold_skill = r.get("gold_skill")
                if not gold_skill:
                    continue
                if r.get("confidence", 1.0) < min_confidence:
                    continue
                query = r.get("query", "").strip()
                tag = ""
            else:
                tag = clean_tag(r.get("服务标签"))
                gold_skill = skill_gold.get(tag)
                if not gold_skill:
                    continue
                dialog_text = r.get("完整对话_清洗后") or r.get("完整对话_原始") or ""
                if extract_mode == "smart":
                    query = extract_first_meaningful(dialog_text, k=first_n)
                elif extract_mode == "business":
                    query = extract_first_business_intent(dialog_text, k=first_n)
                else:
                    query = _naive_extract(r, first_n)
            if not query:
                continue
            state = empty_state(r.get("call_id", "eval"))
            if multi_domain_k > 1 and hasattr(domain_clf, "classify_topk"):
                cache_key = f"{query}||k={multi_domain_k}"
                cached = embed_cache.get(cache_key) if classifier_kind == "embed" else None
                if cached:
                    pred_domains = [d for d, _ in cached]
                    cache_hits += 1
                else:
                    topk = domain_clf.classify_topk(query, state, k=multi_domain_k)
                    pred_domains = [d for d, _ in topk]
                    if classifier_kind == "embed":
                        embed_cache[cache_key] = [[d, s] for d, s in topk]
                        cache_misses += 1
                pred_domain = pred_domains[0]
            else:
                pred_domain = domain_clf.classify(query, state)
                pred_domains = [pred_domain]
            state.intent.domain = pred_domain
            gold_domain = skill_meta.get(gold_skill, {}).get("domain", "")
            pending.append({
                "call_id": r.get("call_id"),
                "tag": tag,
                "query": query,
                "state": state,
                "gold_skill": gold_skill,
                "gold_domain": gold_domain,
                "pred_domain": pred_domain,
                "pred_domains": pred_domains,
            })

    print(f"Prepared {len(pending)} records. Dispatching router with concurrency={router_concurrency}.")
    if classifier_kind == "embed":
        print(f"Embed cache: hits={cache_hits}, misses={cache_misses}")
        if cache_misses > 0:
            save_embed_cache(embed_cache)

    # Phase 2: concurrent router calls
    sem = asyncio.Semaphore(router_concurrency)
    progress = {"done": 0}

    async def route_one(item: dict) -> dict:
        async with sem:
            try:
                if multi_domain_k > 1:
                    match = await router.route_multi_domain(
                        item["query"], item["pred_domains"], item["state"],
                        sliding_window_text="", summary="",
                    )
                else:
                    match = await router.route(
                        item["query"], item["pred_domain"], item["state"],
                        sliding_window_text="", summary="",
                    )
                err = ""
            except Exception as exc:
                match = None
                err = str(exc)
            pred_skill = match.skill_id if match else "none"
            topk_preds = match.top_k_skill_ids(k=3) if match else []
            progress["done"] += 1
            if progress["done"] % 50 == 0 or progress["done"] == len(pending):
                print(f"  ... processed {progress['done']}/{len(pending)}", flush=True)
            return {
                "call_id": item["call_id"],
                "tag": item["tag"],
                "gold_skill": item["gold_skill"],
                "gold_domain": item["gold_domain"],
                "pred_domain": item["pred_domain"],
                "pred_domains_topk": item["pred_domains"],
                "domain_correct": item["gold_domain"] in item["pred_domains"],
                "pred_skill": pred_skill,
                "topk_skills": topk_preds,
                "skill_correct": pred_skill == item["gold_skill"],
                "skill_correct_topk": item["gold_skill"] in topk_preds,
                "confidence": match.confidence if match else 0.0,
                "alternatives": match.alternatives if match else [],
                "query": item["query"],
                "error": err,
            }

    records = await asyncio.gather(*(route_one(it) for it in pending))

    await llm_client.close() if hasattr(llm_client, "close") else None

    total = len(records)
    correct_skill = sum(1 for r in records if r["skill_correct"])
    correct_skill_topk = sum(1 for r in records if r["skill_correct_topk"])
    correct_domain = sum(1 for r in records if r["domain_correct"])
    skill_acc = correct_skill / total if total else 0.0
    skill_topk_acc = correct_skill_topk / total if total else 0.0
    domain_acc = correct_domain / total if total else 0.0

    # Skill accuracy conditioned on correct domain
    domain_ok = [r for r in records if r["domain_correct"]]
    skill_given_domain = (
        sum(1 for r in domain_ok if r["skill_correct"]) / len(domain_ok)
        if domain_ok else 0.0
    )
    skill_topk_given_domain = (
        sum(1 for r in domain_ok if r["skill_correct_topk"]) / len(domain_ok)
        if domain_ok else 0.0
    )

    # Per risk level / route mode
    by_risk: dict[str, list] = defaultdict(list)
    by_route: dict[str, list] = defaultdict(list)
    for r in records:
        meta = skill_meta.get(r["gold_skill"], {})
        by_risk[meta.get("risk_level", "?")].append(r)
        by_route[meta.get("route_mode", "?")].append(r)

    print(f"\n── Exp 2: Skill Match (L1={classifier_kind}, extract={extract_mode}, first_n={first_n}, multi_domain_k={multi_domain_k}) ──")
    print(f"Samples:                     {total}")
    print(f"Domain covered (in L1 Top-{multi_domain_k}): {domain_acc:.2%}  ({correct_domain}/{total})")
    print(f"Skill Top-1 accuracy:        {skill_acc:.2%}  ({correct_skill}/{total})")
    print(f"Skill Top-3 accuracy:        {skill_topk_acc:.2%}  ({correct_skill_topk}/{total})")
    print(f"Skill Top-1 | domain-covered: {skill_given_domain:.2%}  ({sum(1 for r in domain_ok if r['skill_correct'])}/{len(domain_ok)})")
    print(f"Skill Top-3 | domain-covered: {skill_topk_given_domain:.2%}  ({sum(1 for r in domain_ok if r['skill_correct_topk'])}/{len(domain_ok)})")

    print("\nBy risk_level (gold):")
    for k in ("low", "medium", "high", "?"):
        rs = by_risk.get(k, [])
        if rs:
            acc1 = sum(1 for r in rs if r["skill_correct"]) / len(rs)
            acck = sum(1 for r in rs if r["skill_correct_topk"]) / len(rs)
            print(f"  {k:<7} n={len(rs):>3}  Top-1={acc1:.2%}  Top-3={acck:.2%}")

    print("\nBy route_mode (gold):")
    for k in ("direct_reply", "tool_only", "tool_rag", "?"):
        rs = by_route.get(k, [])
        if rs:
            acc1 = sum(1 for r in rs if r["skill_correct"]) / len(rs)
            acck = sum(1 for r in rs if r["skill_correct_topk"]) / len(rs)
            print(f"  {k:<13} n={len(rs):>3}  Top-1={acc1:.2%}  Top-3={acck:.2%}")

    # Top confusions
    confusion = Counter(
        (r["gold_skill"], r["pred_skill"]) for r in records if not r["skill_correct"]
    )
    print("\nTop skill confusions (gold → pred, count):")
    for (g, p), c in confusion.most_common(10):
        print(f"  {g:<35} → {p:<35} ×{c}")

    wrongs = [r for r in records if not r["skill_correct"]]
    print(f"\nSample errors (showing up to 8 of {len(wrongs)}):")
    for r in wrongs[:8]:
        print(f"  [gold={r['gold_skill']:<30} pred={r['pred_skill']:<30} dom={r['pred_domain']}] {r['query'][:90]}")

    print("\nDecision hint:")
    if skill_topk_given_domain >= 0.85:
        print(f"  ✅ Top-3 | Domain-correct ≥ 85%  →  SkillRouter 召回质量足够")
    elif skill_topk_given_domain >= 0.70:
        print(f"  ⚠️  Top-3 | Domain-correct 70-85%  →  可接受，看业务容忍度")
    else:
        print(f"  ❌ Top-3 | Domain-correct < 70%  →  需要调 prompt 或补 triggers.examples")

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps({
            "config": {"classifier": classifier_kind, "extract": extract_mode, "first_n": first_n, "limit": limit},
            "metrics": {
                "skill_top1_accuracy": skill_acc,
                "skill_top3_accuracy": skill_topk_acc,
                "domain_accuracy": domain_acc,
                "skill_top1_given_domain_correct": skill_given_domain,
                "skill_top3_given_domain_correct": skill_topk_given_domain,
                "total": total,
            },
            "confusion": [{"gold": g, "pred": p, "count": c} for (g, p), c in confusion.items()],
            "records": records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON report: {json_out}")
    return 0


def _naive_extract(record: dict, n: int) -> str:
    msgs: list[str] = []
    dialog = record.get("完整对话_清洗后") or record.get("完整对话_原始") or ""
    for line in dialog.split("\n"):
        line = line.strip()
        if line.startswith("[客户]"):
            text = line.replace("[客户]", "", 1).strip()
            if text:
                msgs.append(text)
            if len(msgs) >= n:
                break
    return " ".join(msgs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classifier", choices=["rule", "embed"], default="embed")
    ap.add_argument("--first-n", type=int, default=3)
    ap.add_argument("--extract", choices=["naive", "smart", "business"], default="business")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", dest="json_out", type=Path)
    ap.add_argument("--multi-domain-k", type=int, default=1,
                    help="L1 Top-K domains to include as candidates (1 = single-domain as before)")
    ap.add_argument("--fewshot", action="store_true", help="use few-shot retrieval in Router")
    ap.add_argument("--fewshot-k", type=int, default=5, help="number of fewshot examples to inject")
    ap.add_argument("--source", choices=["test", "golden"], default="test",
                    help="'test' reads test.jsonl (98 conversations); 'golden' reads tests/golden_test.jsonl (2844 queries)")
    ap.add_argument("--min-confidence", type=float, default=0.0,
                    help="when --source=golden, skip rows with confidence below this threshold")
    ap.add_argument("--concurrency", type=int, default=10,
                    help="number of concurrent router calls (default 10)")
    args = ap.parse_args()
    asyncio.run(run(
        args.classifier, args.first_n, args.extract, args.limit, args.json_out,
        args.multi_domain_k, args.fewshot, args.fewshot_k,
        args.source, args.min_confidence, args.concurrency,
    ))


if __name__ == "__main__":
    main()
