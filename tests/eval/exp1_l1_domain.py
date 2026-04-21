"""Exp 1 — L1 Domain Classification Accuracy.

Evaluates fin_copilot.routing.domain_classifier.DomainClassifier against
the gold labels in test.jsonl.

For each conversation we extract the customer's first utterance (or concat
the first N customer lines when --first-n > 1) and ask the classifier to
predict a domain. We compare against the mapped gold domain.

Usage:
    python scripts/eval_l1_domain.py                    # default (first 1 customer msg)
    python scripts/eval_l1_domain.py --first-n 3        # concat first 3 customer msgs
    python scripts/eval_l1_domain.py --json report.json # emit JSON too
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.models.conversation import ConversationState, CustomerInfo, IntentState  # noqa: E402
from fin_copilot.routing.domain_classifier import DomainClassifier  # noqa: E402
from fin_copilot.routing.embedding_domain_classifier import EmbeddingDomainClassifier  # noqa: E402
from fin_copilot.skills.loader import SkillLoader  # noqa: E402
from fin_copilot.config import get_settings  # noqa: E402
from scripts.dialog_extract import extract_first_meaningful, extract_first_business_intent  # noqa: E402

TEST_PATH = ROOT / "test.jsonl"
GOLDEN_PATH = ROOT / "tests" / "golden_test.jsonl"
MAPPING_PATH = ROOT / "scripts" / "references" / "domain_gold_mapping.json"


def load_mapping() -> dict[str, str | None]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return data["level2_to_domain"]


def extract_first_customer_messages(dialog: str, n: int, extract_mode: str = "naive") -> str:
    if extract_mode == "smart":
        return extract_first_meaningful(dialog, k=n)
    if extract_mode == "business":
        return extract_first_business_intent(dialog, k=n)
    # naive fallback
    msgs: list[str] = []
    for line in dialog.split("\n"):
        line = line.strip()
        if line.startswith("[客户]"):
            text = line.replace("[客户]", "", 1).strip()
            if text:
                msgs.append(text)
            if len(msgs) >= n:
                break
    return " ".join(msgs)


def empty_state() -> ConversationState:
    return ConversationState(
        session_id="eval",
        customer=CustomerInfo(),
        intent=IntentState(),
    )


def run(
    first_n: int,
    json_out: Path | None,
    classifier_kind: str,
    extract_mode: str,
    top_k: int,
    source: str,
    min_confidence: float,
    limit: int | None,
    progress_every: int,
) -> int:
    mapping = load_mapping()
    if classifier_kind == "embed":
        classifier = EmbeddingDomainClassifier()
    else:
        classifier = DomainClassifier()

    skill_to_domain: dict[str, str] = {}
    if source == "golden":
        settings = get_settings()
        loader = SkillLoader(
            str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
            str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
        )
        for sid in loader.get_all_skill_ids():
            s = loader.get_skill(sid)
            if s is not None:
                skill_to_domain[sid] = s.domain

    records: list[dict] = []
    data_path = GOLDEN_PATH if source == "golden" else TEST_PATH
    start_ts = time.monotonic()
    progress_suffix = f"/{limit}" if limit is not None else ""
    if progress_every > 0:
        print(
            f"Exp1 evaluating records from {data_path} "
            f"(classifier={classifier_kind}, top_k={top_k}, limit={limit or 'none'})",
            flush=True,
        )
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            if limit is not None and len(records) >= limit:
                break
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if source == "golden":
                gold_skill = r.get("gold_skill")
                gold = skill_to_domain.get(gold_skill)
                if gold is None:
                    continue
                if r.get("confidence", 1.0) < min_confidence:
                    continue
                query = r.get("query", "").strip()
                level2 = ""
            else:
                level2 = r.get("二级分类", "")
                gold = mapping.get(level2)
                if gold is None:
                    continue
                query = extract_first_customer_messages(
                    r.get("完整对话_清洗后") or r.get("完整对话_原始") or "", first_n,
                    extract_mode=extract_mode,
                )
            if not query:
                continue
            pred = classifier.classify(query, empty_state())
            # Top-K recall (embedding classifier supports it; rule classifier only has top-1)
            topk_preds: list[str] = [pred]
            if hasattr(classifier, "classify_topk"):
                topk_preds = [d for d, _ in classifier.classify_topk(query, empty_state(), k=top_k)]
            records.append({
                "call_id": r.get("call_id"),
                "level2": level2,
                "gold_domain": gold,
                "pred_domain": pred,
                "topk_preds": topk_preds,
                "query": query,
                "correct": pred == gold,
                "correct_topk": gold in topk_preds,
            })
            if progress_every > 0 and len(records) % progress_every == 0:
                elapsed = time.monotonic() - start_ts
                running_correct = sum(1 for item in records if item["correct"])
                running_topk = sum(1 for item in records if item["correct_topk"])
                speed = len(records) / elapsed if elapsed > 0 else 0.0
                print(
                    f"  ... exp1 processed {len(records)}{progress_suffix} "
                    f"top1={running_correct / len(records):.2%} "
                    f"top{top_k}={running_topk / len(records):.2%} "
                    f"elapsed={elapsed:.1f}s speed={speed:.1f}/s",
                    flush=True,
                )
    if progress_every > 0 and records and len(records) % progress_every != 0:
        elapsed = time.monotonic() - start_ts
        running_correct = sum(1 for item in records if item["correct"])
        running_topk = sum(1 for item in records if item["correct_topk"])
        speed = len(records) / elapsed if elapsed > 0 else 0.0
        print(
            f"  ... exp1 processed {len(records)}{progress_suffix} "
            f"top1={running_correct / len(records):.2%} "
            f"top{top_k}={running_topk / len(records):.2%} "
            f"elapsed={elapsed:.1f}s speed={speed:.1f}/s",
            flush=True,
        )

    total = len(records)
    correct = sum(1 for r in records if r["correct"])
    correct_topk = sum(1 for r in records if r["correct_topk"])
    overall_acc = correct / total if total else 0.0
    topk_recall = correct_topk / total if total else 0.0

    # Per-domain P/R/F1
    by_gold: dict[str, list[dict]] = defaultdict(list)
    by_pred: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_gold[r["gold_domain"]].append(r)
        by_pred[r["pred_domain"]].append(r)

    per_domain = {}
    all_domains = set(by_gold) | set(by_pred)
    for d in sorted(all_domains):
        tp = sum(1 for r in by_gold.get(d, []) if r["correct"])
        fn = len(by_gold.get(d, [])) - tp
        fp = sum(1 for r in by_pred.get(d, []) if not r["correct"])
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_domain[d] = {
            "support_gold": len(by_gold.get(d, [])),
            "support_pred": len(by_pred.get(d, [])),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp, "fn": fn, "fp": fp,
        }

    # Confusion pairs
    confusion = Counter(
        (r["gold_domain"], r["pred_domain"]) for r in records if not r["correct"]
    )

    print(f"── Exp 1: L1 Domain Classifier ──")
    print(f"Classifier: {classifier_kind}  |  Extract: {extract_mode}")
    print(f"Samples evaluated: {total}  (excludes unmapped labels)")
    print(f"First-N customer msgs concat: {first_n}")
    print(f"Overall accuracy: {overall_acc:.2%}  ({correct}/{total})")
    print(f"Top-{top_k} recall:     {topk_recall:.2%}  ({correct_topk}/{total})\n")

    print("Per-domain:")
    print(f"  {'domain':<10} {'gold':>5} {'pred':>5} {'P':>7} {'R':>7} {'F1':>7}")
    for d, m in sorted(per_domain.items(), key=lambda x: -x[1]["support_gold"]):
        print(f"  {d:<10} {m['support_gold']:>5} {m['support_pred']:>5} "
              f"{m['precision']:>7.2%} {m['recall']:>7.2%} {m['f1']:>7.2%}")

    if confusion:
        print("\nTop confusions (gold → pred, count):")
        for (g, p), c in confusion.most_common(10):
            print(f"  {g:<10} → {p:<10} ×{c}")

    # Wrong samples
    wrongs = [r for r in records if not r["correct"]]
    if wrongs:
        print(f"\nSample errors ({len(wrongs)} total, showing up to 8):")
        for r in wrongs[:8]:
            print(f"  [gold={r['gold_domain']:<5} pred={r['pred_domain']:<5}] "
                  f"{r['query'][:90]}")

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps({
            "overall_accuracy": overall_acc,
            "topk_recall": topk_recall,
            "top_k": top_k,
            "total": total,
            "correct": correct,
            "correct_topk": correct_topk,
            "first_n": first_n,
            "limit": limit,
            "progress_every": progress_every,
            "per_domain": per_domain,
            "confusion": [{"gold": g, "pred": p, "count": c} for (g, p), c in confusion.items()],
            "records": records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDetailed JSON written to {json_out}")

    # Decision gate
    print("\nDecision hint:")
    if overall_acc >= 0.90:
        print("  ✅ ≥ 90%  →  current rule-based classifier is sufficient")
    elif overall_acc >= 0.80:
        print("  ⚠️  80-90%  →  add keyword weights + exclude rules")
    else:
        print("  ❌ < 80%  →  upgrade to embedding similarity or small classifier")

    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-n", type=int, default=1, help="how many customer messages to concat")
    ap.add_argument("--json", dest="json_out", type=Path, help="optional JSON output path")
    ap.add_argument("--classifier", choices=["rule", "embed"], default="rule",
                    help="which classifier to evaluate")
    ap.add_argument("--extract", choices=["naive", "smart", "business"], default="naive",
                    help="naive=first k lines; smart=skip greeting/identity; business=also skip 会话流程")
    ap.add_argument("--top-k", type=int, default=3, help="Top-K recall metric (embedding only)")
    ap.add_argument("--source", choices=["test", "golden"], default="test",
                    help="'test' reads test.jsonl (98 conversations); 'golden' reads tests/golden_test.jsonl")
    ap.add_argument("--min-confidence", type=float, default=0.0,
                    help="when --source=golden, skip rows below this confidence")
    ap.add_argument("--limit", type=int, default=None,
                    help="optional maximum number of evaluable records to run")
    ap.add_argument("--progress-every", type=int, default=50,
                    help="print progress every N evaluated records; set 0 to disable")
    args = ap.parse_args()
    sys.exit(run(
        args.first_n,
        args.json_out,
        args.classifier,
        args.extract,
        args.top_k,
        args.source,
        args.min_confidence,
        args.limit,
        args.progress_every,
    ))


if __name__ == "__main__":
    main()
