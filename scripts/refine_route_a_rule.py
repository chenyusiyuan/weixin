"""Refine a route_a rule for a target skill by mining exclude_keywords.

Two-tier strategy:
  1. **Auto-accept** exclude candidates that drop >=1 wrong prediction
     AND drop 0 true-gold queries (pure wins, no recall loss).
  2. **Flag for review** candidates with positive FP/TP ratio >= ratio_min
     (default 3). These trade some recall for precision — user decides.

Candidates come from other skills' YAML keywords that appear in the
mis-labelled queries of the current skill and are NOT present in the
current skill's own keyword list. Extra candidates can be loaded from
a handcrafted list.

Usage:
    python scripts/refine_route_a_rule.py early_loan_clearance
    python scripts/refine_route_a_rule.py overdue_negotiation --auto-review
    python scripts/refine_route_a_rule.py stop_collection --prec-target 0.90
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.config import get_settings  # noqa: E402
from fin_copilot.skills.loader import SkillLoader  # noqa: E402

GOLDEN_PATH = ROOT / "raw_test.jsonl"
EXISTING_RULES = ROOT / "rules" / "rule_engine.json"


def _match(query: str, keywords: list[str], excludes: list[str]) -> bool:
    if not any(kw and kw in query for kw in keywords):
        return False
    if any(kw and kw in query for kw in excludes):
        return False
    return True


def _eval_rule(
    golden: list[dict],
    target_skill: str,
    keywords: list[str],
    excludes: list[str],
) -> dict:
    hits, correct = 0, 0
    wrong: list[tuple[str, str]] = []
    missed_gold: list[str] = []
    total_gold = sum(1 for r in golden if r["gold_skill"] == target_skill)
    for r in golden:
        q = r["query"]
        g = r["gold_skill"]
        is_gold = g == target_skill
        hit = _match(q, keywords, excludes)
        if hit:
            hits += 1
            if is_gold:
                correct += 1
            else:
                wrong.append((g, q))
        else:
            if is_gold:
                missed_gold.append(q)
    return {
        "hits": hits,
        "correct": correct,
        "wrong": wrong,
        "missed_gold": missed_gold,
        "total_gold": total_gold,
        "precision": correct / hits if hits else 0.0,
        "recall": correct / total_gold if total_gold else 0.0,
    }


def _impact_of(
    golden: list[dict],
    target_skill: str,
    keywords: list[str],
    current_excludes: list[str],
    candidate: str,
) -> dict:
    """How many TP vs FP would adding `candidate` to excludes drop?"""
    drop_tp = drop_fp = 0
    for r in golden:
        q = r["query"]
        g = r["gold_skill"]
        hit_now = _match(q, keywords, current_excludes)
        if not hit_now:
            continue
        # would this addition drop it?
        if candidate in q:
            if g == target_skill:
                drop_tp += 1
            else:
                drop_fp += 1
    return {"drop_tp": drop_tp, "drop_fp": drop_fp}


def _candidate_pool(
    loader: SkillLoader,
    target_skill: str,
    own_keywords: set[str],
    wrong_records: list[tuple[str, str]],
) -> list[str]:
    """Collect candidate exclude keywords.

    Takes keywords from other skills (the ones we're confusing with),
    filters to those actually present in our wrong queries, removes
    candidates that appear in our own keywords.
    """
    other_skill_kws: Counter[str] = Counter()
    confusing_skills = Counter(g for g, _ in wrong_records)
    for other_sid, _ in confusing_skills.most_common(10):
        other = loader.get_skill(other_sid)
        if not other:
            continue
        for kw in (other.triggers.keywords or []):
            if not kw:
                continue
            if kw in own_keywords:
                continue
            if 2 <= len(kw) <= 12:
                other_skill_kws[kw] += 1

    # Keep only candidates that appear in at least one wrong query
    candidates: list[str] = []
    wrong_queries = [q for _, q in wrong_records]
    for kw in other_skill_kws:
        if any(kw in q for q in wrong_queries):
            candidates.append(kw)
    return candidates


def run(
    skill_id: str,
    prec_target: float,
    ratio_min: float,
    auto_review: bool,
    dry_run: bool,
    extra_excludes: list[str],
) -> int:
    settings = get_settings()
    loader = SkillLoader(
        str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
        str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
    )
    skill = loader.get_skill(skill_id)
    if skill is None:
        print(f"❌ skill not found: {skill_id}")
        return 2

    keywords = [kw for kw in (skill.triggers.keywords or []) if kw]
    base_excludes = [kw for kw in (skill.triggers.exclude_keywords or []) if kw]

    # Load golden
    golden: list[dict] = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("query") and r.get("gold_skill"):
                golden.append(r)

    # Baseline
    base = _eval_rule(golden, skill_id, keywords, base_excludes)
    print(f"\n── Target skill: {skill_id} ({skill.name}) ──")
    print(f"Base keywords ({len(keywords)}): {keywords}")
    print(f"Base excludes ({len(base_excludes)}): {base_excludes}")
    print(f"Gold total: {base['total_gold']}")
    print(f"Baseline  hits={base['hits']}  correct={base['correct']}"
          f"  prec={base['precision']:.1%}  recall={base['recall']:.1%}")

    if base["hits"] == 0:
        print("⚠️  No hits from current keywords; cannot refine.")
        return 1

    # Candidate pool
    candidates = _candidate_pool(loader, skill_id, set(keywords), base["wrong"])
    for kw in extra_excludes:
        if kw not in candidates and kw not in keywords:
            candidates.append(kw)
    print(f"\nCandidate exclude pool: {len(candidates)}")

    # Phase 1: auto-accept pure wins (drop_fp >= 1, drop_tp == 0)
    current_excludes = list(base_excludes)
    auto_accepted: list[tuple[str, int, int]] = []  # (kw, drop_fp, drop_tp)
    flagged: list[tuple[str, int, int]] = []

    for kw in candidates:
        impact = _impact_of(golden, skill_id, keywords, current_excludes, kw)
        if impact["drop_fp"] >= 1 and impact["drop_tp"] == 0:
            current_excludes.append(kw)
            auto_accepted.append((kw, impact["drop_fp"], impact["drop_tp"]))

    print(f"\n── Phase 1: Auto-accepted pure wins ({len(auto_accepted)}) ──")
    for kw, fp, tp in sorted(auto_accepted, key=lambda x: -x[1]):
        print(f"  + '{kw}'  drops {fp} FP, 0 TP")

    # Phase 2: flagged (positive ratio but has TP cost)
    for kw in candidates:
        if kw in current_excludes:
            continue
        impact = _impact_of(golden, skill_id, keywords, current_excludes, kw)
        if impact["drop_fp"] == 0:
            continue
        if impact["drop_tp"] == 0:
            # might be a late pure win after phase 1
            current_excludes.append(kw)
            auto_accepted.append((kw, impact["drop_fp"], 0))
            continue
        ratio = impact["drop_fp"] / max(impact["drop_tp"], 1)
        if ratio >= ratio_min:
            flagged.append((kw, impact["drop_fp"], impact["drop_tp"]))

    print(f"\n── Phase 2: Flagged (FP/TP ratio >= {ratio_min}) ──")
    for kw, fp, tp in sorted(flagged, key=lambda x: -x[1] / max(x[2], 1)):
        ratio = fp / max(tp, 1)
        print(f"  ? '{kw}'  drops {fp} FP vs {tp} TP  (ratio {ratio:.1f}x)")

    # Compute state after phase 1
    mid = _eval_rule(golden, skill_id, keywords, current_excludes)
    print(f"\nAfter phase 1:  hits={mid['hits']}  correct={mid['correct']}"
          f"  prec={mid['precision']:.1%}  recall={mid['recall']:.1%}")

    # Phase 3: if precision still below target, optionally take flagged
    final_excludes = list(current_excludes)
    if mid["precision"] < prec_target and flagged and auto_review:
        print(f"\n── Phase 3: Auto-applying flagged (precision below {prec_target:.0%}) ──")
        # Greedily apply best-ratio flagged until target met
        flagged_sorted = sorted(
            flagged,
            key=lambda x: (-x[1] / max(x[2], 1), -x[1]),
        )
        for kw, fp, tp in flagged_sorted:
            # Re-measure under current state
            imp = _impact_of(golden, skill_id, keywords, final_excludes, kw)
            if imp["drop_fp"] == 0:
                continue
            final_excludes.append(kw)
            print(f"  + '{kw}'  drops {imp['drop_fp']} FP, {imp['drop_tp']} TP")
            cur = _eval_rule(golden, skill_id, keywords, final_excludes)
            if cur["precision"] >= prec_target:
                break

    final = _eval_rule(golden, skill_id, keywords, final_excludes)
    print("\n── Final ──")
    print(f"excludes ({len(final_excludes)}): {final_excludes}")
    print(f"hits={final['hits']}  correct={final['correct']}"
          f"  prec={final['precision']:.1%}  recall={final['recall']:.1%}")

    if final["precision"] >= prec_target:
        print(f"✅ Meets precision target {prec_target:.0%}")
    else:
        print(f"⚠️  Below precision target {prec_target:.0%}.")
        print(f"   Remaining wrong examples (first 5 of {len(final['wrong'])}):")
        for g, q in final["wrong"][:5]:
            print(f"     gold={g}  q={q[:90]}")

    # Emit draft rule JSON
    if EXISTING_RULES.exists():
        existing = json.loads(EXISTING_RULES.read_text(encoding="utf-8"))
        next_id = f"RULE_{len(existing.get('rules', [])) + 1:03d}"
    else:
        next_id = "RULE_001"

    draft = {
        "rule_id": next_id,
        "skill_id": skill_id,
        "name": skill.name,
        "match_type": "keyword",
        "keywords": keywords,
        "exclude_keywords": final_excludes,
        "template_variant": "first_contact",
        "expires": "2026-07-21",
        "accept_rate_threshold": 0.85,
        "source": "derived-from-golden",
        "_stats": {
            "golden_freq": final["total_gold"],
            "simulated_hits": final["hits"],
            "simulated_precision": round(final["precision"], 4),
            "simulated_recall": round(final["recall"], 4),
        },
    }
    print("\n── Draft rule (ready to paste into rules/rule_engine.json) ──")
    print(json.dumps(draft, ensure_ascii=False, indent=2))

    if not dry_run and final["precision"] >= prec_target:
        target_file = ROOT / "tests" / "reports" / f"route_a_rule_{skill_id}.json"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved draft to: {target_file}")

    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("skill_id", help="target skill to refine a rule for")
    ap.add_argument("--prec-target", type=float, default=0.90)
    ap.add_argument("--ratio-min", type=float, default=3.0,
                    help="min FP/TP ratio for flagged phase (default 3.0)")
    ap.add_argument("--auto-review", action="store_true",
                    help="auto-apply flagged greedily until prec target met")
    ap.add_argument("--dry-run", action="store_true",
                    help="don't save draft JSON to disk")
    ap.add_argument("--extra-excludes", nargs="*", default=[],
                    help="additional manual candidate excludes to try")
    args = ap.parse_args()
    sys.exit(run(
        args.skill_id,
        args.prec_target,
        args.ratio_min,
        args.auto_review,
        args.dry_run,
        args.extra_excludes,
    ))


if __name__ == "__main__":
    main()
