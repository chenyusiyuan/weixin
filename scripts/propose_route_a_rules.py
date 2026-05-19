"""Propose Chain A route_a rules from raw_test.jsonl.

Strategy:
  1. For each skill with frequency >= FREQ_MIN in the golden set, simulate
     a rule match using its skill YAML `triggers.keywords` as the rule's
     keywords. Exclude keywords come from `triggers.exclude_keywords`.
  2. Compute hits (queries matching the rule) and correct (hits whose
     gold_skill equals this skill). Precision = correct / hits.
  3. Skills meeting `precision >= PREC_MIN` AND `hits >= HITS_MIN` become
     rule candidates.
  4. For each candidate, suggest additional exclude_keywords drawn from
     the most common keywords of other skills it collides with — these
     would need human review before adopting.
  5. Emit a JSON payload you can paste-merge into rules/rule_engine.json
     after review.

No files are modified. Read-only analysis.

Usage:
    python scripts/propose_route_a_rules.py
    python scripts/propose_route_a_rules.py --freq-min 30 --prec-min 0.92
    python scripts/propose_route_a_rules.py --json tests/reports/route_a_proposals.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
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


def run(freq_min: int, prec_min: float, hits_min: int, json_out: Path | None) -> int:
    settings = get_settings()
    loader = SkillLoader(
        str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
        str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
    )

    # Load golden
    golden: list[dict] = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("gold_skill") and r.get("query"):
                golden.append(r)
    print(f"loaded golden: {len(golden)} queries")

    # Load existing rule's skills (to exclude — don't propose what's already covered)
    existing_skills: set[str] = set()
    if EXISTING_RULES.exists():
        data = json.loads(EXISTING_RULES.read_text(encoding="utf-8"))
        for r in data.get("rules", []):
            existing_skills.add(r.get("skill_id", ""))
    print(f"existing route_a skills: {sorted(existing_skills)}")

    # Skill frequency on golden
    freq: Counter[str] = Counter(r["gold_skill"] for r in golden)
    print(f"\nTop-15 skills by golden freq:")
    for sid, n in freq.most_common(15):
        marker = " (已有规则)" if sid in existing_skills else ""
        print(f"  {sid:<35} {n:>5}{marker}")

    all_skill_ids = loader.get_all_skill_ids()
    all_skill_kwset: dict[str, set[str]] = {}
    for sid in all_skill_ids:
        skill = loader.get_skill(sid)
        if skill:
            all_skill_kwset[sid] = set(kw for kw in (skill.triggers.keywords or []) if kw)

    # For each candidate skill, run simulated match across entire golden
    proposals: list[dict] = []
    per_skill_conflicts: dict[str, Counter] = defaultdict(Counter)

    for sid, n in freq.most_common():
        if n < freq_min:
            break  # sorted desc, can stop early
        if sid in existing_skills:
            continue
        skill = loader.get_skill(sid)
        if skill is None:
            continue
        keywords = [kw for kw in (skill.triggers.keywords or []) if kw]
        excludes = [kw for kw in (skill.triggers.exclude_keywords or []) if kw]
        if not keywords:
            continue

        hits = 0
        correct = 0
        wrong_examples: list[dict] = []
        for r in golden:
            q = r["query"]
            if not _match(q, keywords, excludes):
                continue
            hits += 1
            if r["gold_skill"] == sid:
                correct += 1
            else:
                per_skill_conflicts[sid][r["gold_skill"]] += 1
                if len(wrong_examples) < 4:
                    wrong_examples.append({
                        "query": q[:60],
                        "gold": r["gold_skill"],
                    })

        if hits < hits_min:
            continue
        precision = correct / hits if hits else 0.0
        recall_among_skill = correct / n

        proposals.append({
            "skill_id": sid,
            "freq_in_golden": n,
            "hits": hits,
            "correct": correct,
            "precision": precision,
            "recall_within_skill": recall_among_skill,
            "keywords": keywords,
            "excludes_from_yaml": excludes,
            "risk_level": skill.risk_level,
            "route_mode": skill.route_mode,
            "domain": skill.domain,
            "wrong_examples": wrong_examples,
            "top_confusions": per_skill_conflicts[sid].most_common(5),
            "pass_threshold": precision >= prec_min,
        })

    # Sort by precision desc, then hits desc
    proposals.sort(key=lambda x: (-int(x["pass_threshold"]), -x["precision"], -x["hits"]))

    # Report
    print(f"\n── Rule Proposals (freq>={freq_min}, hits>={hits_min}, prec>={prec_min:.0%}) ──")
    print(f"{'skill_id':<35} {'freq':>5} {'hits':>5} {'ok':>5} {'prec':>7} {'recall':>7} {'risk':>6}  pass")
    for p in proposals:
        mark = "✅" if p["pass_threshold"] else "⚠️ "
        print(f"  {p['skill_id']:<33} {p['freq_in_golden']:>5} {p['hits']:>5} {p['correct']:>5}"
              f" {p['precision']:>6.1%} {p['recall_within_skill']:>6.1%} {p['risk_level']:>6}  {mark}")

    # Show confusions for non-passing proposals (they need exclude_keywords)
    print(f"\n── Near-misses: add exclude_keywords to lift precision ──")
    near = [p for p in proposals if not p["pass_threshold"] and p["hits"] >= hits_min]
    for p in near[:8]:
        confusing = per_skill_conflicts[p["skill_id"]].most_common(3)
        suggest_excludes: set[str] = set()
        for other_sid, _ in confusing:
            other_kws = all_skill_kwset.get(other_sid, set())
            # Keywords uniquely in the other skill but not in this one
            uniq = other_kws - set(p["keywords"])
            for kw in uniq:
                # heuristic: short-enough and content-bearing
                if 2 <= len(kw) <= 8:
                    suggest_excludes.add(kw)
        print(f"\n  {p['skill_id']}  (prec {p['precision']:.1%}, hits {p['hits']})")
        for other_sid, cnt in confusing:
            print(f"    ↳ 混入 {other_sid} × {cnt}")
        if suggest_excludes:
            sample = list(sorted(suggest_excludes))[:12]
            print(f"    建议 exclude_keywords (需人工审核): {'、'.join(sample)}")
        for ex in p["wrong_examples"][:3]:
            print(f"    - ❌「{ex['query']}」 gold={ex['gold']}")

    # Generate draft rules for passing proposals
    pass_list = [p for p in proposals if p["pass_threshold"]]
    print(f"\n── Draft rule_engine.json entries ({len(pass_list)} rules) ──")
    existing_count = 0
    if EXISTING_RULES.exists():
        existing_count = len(json.loads(EXISTING_RULES.read_text(encoding="utf-8")).get("rules", []))
    draft_rules = []
    for i, p in enumerate(pass_list):
        rule_id = f"RULE_{existing_count + i + 1:03d}"
        draft_rules.append({
            "rule_id": rule_id,
            "skill_id": p["skill_id"],
            "name": p["skill_id"],
            "match_type": "keyword",
            "keywords": p["keywords"],
            "exclude_keywords": p["excludes_from_yaml"],
            "template_variant": "first_contact",
            "expires": "2026-07-21",
            "accept_rate_threshold": 0.85,
            "source": "derived-from-golden",
            "_stats": {
                "golden_freq": p["freq_in_golden"],
                "simulated_hits": p["hits"],
                "simulated_precision": round(p["precision"], 4),
                "simulated_recall": round(p["recall_within_skill"], 4),
            },
        })
    print(json.dumps(draft_rules, ensure_ascii=False, indent=2))

    # Coverage summary
    total_hits = sum(p["hits"] for p in pass_list)
    print(f"\n── Coverage impact ──")
    print(f"Golden total: {len(golden)}")
    print(f"Existing route_a skills: {len(existing_skills)}")
    print(f"Proposed new rules (passing): {len(pass_list)}")
    print(f"New rules hit coverage: {total_hits} queries ({total_hits/len(golden):.1%} of golden)")
    print(f"New rules precision floor: {min((p['precision'] for p in pass_list), default=0):.1%}")

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps({
                "config": {
                    "freq_min": freq_min,
                    "hits_min": hits_min,
                    "prec_min": prec_min,
                },
                "existing_skills": sorted(existing_skills),
                "proposals": proposals,
                "draft_rules_passing": draft_rules,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON report: {json_out}")

    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq-min", type=int, default=20,
                    help="min gold frequency for a skill to be considered")
    ap.add_argument("--hits-min", type=int, default=15,
                    help="min simulated hits before scoring precision")
    ap.add_argument("--prec-min", type=float, default=0.90,
                    help="min precision to mark as passing (default 0.90)")
    ap.add_argument("--json", dest="json_out", type=Path,
                    default=ROOT / "tests" / "reports" / "route_a_proposals.json")
    args = ap.parse_args()
    sys.exit(run(args.freq_min, args.prec_min, args.hits_min, args.json_out))


if __name__ == "__main__":
    main()
