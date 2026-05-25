"""Evaluate multi-turn call skill recall with call-level TopK scoring.

Scoring logic:
  - Each call has K gold intents from the current multi-turn golden set.
  - Every extracted raw customer query is routed to one predicted skill.
  - For a call, count predicted skill occurrences across all routed queries.
  - Take Top-K predicted skills, where K is the number of mapped gold intents.
  - If N of the K gold intents are hit by Top-K, call score is N / K.
  - Final score is total call scores divided by the merged sample count.

Inputs:
  golden_test.jsonl
  scripts/references/merged_intent_skill_mapping.json

Outputs:
  tests/reports/merged_multi_turn_<timestamp>/
    query_predictions.jsonl
    call_scores.jsonl
    summary.json

Examples:
  # Fast smoke test using skill cosine only, no LLM router.
  python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode skill-cos --limit 20

  # Full router run. Use LIMIT first; full 1519 query run can take a while.
  python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode router --limit 20
  python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode router --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fin_copilot.config import get_settings  # noqa: E402
from fin_copilot.llm.client import LLMClient  # noqa: E402
from fin_copilot.models.conversation import ConversationState, CustomerInfo, IntentState, Message  # noqa: E402
from fin_copilot.routing.embedding_domain_classifier import EmbeddingDomainClassifier  # noqa: E402
from fin_copilot.routing.fewshot_retriever import FewShotRetriever  # noqa: E402
from fin_copilot.routing.skill_embedding_index import SkillEmbeddingIndex  # noqa: E402
from fin_copilot.routing.skill_router import SkillRouter  # noqa: E402
from fin_copilot.skills.loader import SkillLoader  # noqa: E402


CALLS_PATH = ROOT / "golden_test.jsonl"
MAPPING_PATH = ROOT / "scripts" / "references" / "merged_intent_skill_mapping.json"
CHUNK_SUMMARY_PATH = ROOT / "tests" / "merged_turn_filter" / "chunk_summary.json"
CACHE_PATH = ROOT / "tests" / "merged_turn_filter" / ".merged_multi_turn_route_cache.json"
AUDIT_CACHE_PATH = ROOT / "tests" / "merged_turn_filter" / ".merged_multi_turn_audit_cache.json"

DEFAULT_AUDIT_INTENTS = [
    "还款相关/存对公还款",
    "还款相关/账单信息查询",
    "营销活动/会员退费",
    "营销活动/新活动咨询",
    "产品与信息/非我司产品",
]

AUDIT_PROMPT_VERSION = "family-v2-20260427"

AUDIT_INTENT_POLICIES: dict[str, dict[str, Any]] = {
    "还款相关/存对公还款": {
        "policy_name": "corporate_repayment_family",
        "evaluation_unit": "对公还款业务族",
        "accept_when": [
            "客户主要诉求属于存对公还款、对公账户/账号获取、对公还款方式、对公转账后入账/账单更新/还款结果、对公账号或贷后信息核实、对公转错/转多/误转/退溢余中的任一子场景。",
            "pred skill 在 acceptable_skill_ids_from_mapping 内，并且能承接客户真实子场景；不要求 pred skill 覆盖对公还款业务族的全部子场景。",
            "对公转账少转/补差如果被映射到对公还款方式、入账状态或还款结果类 skill，应按合理命中判断；只有明确要求退多转/误转款项时才更偏向 overpayment_refund。",
        ],
        "reject_when": [
            "客户主要诉求不是对公还款相关。",
            "pred skill 只命中了无关的费用、催收、证明或普通贷款咨询能力。",
            "客户只是在流程确认、核身、问候或补充无业务信息，无法支撑该业务族命中。",
        ],
    },
    "还款相关/账单信息查询": {
        "policy_name": "bill_query_evidence_family",
        "evaluation_unit": "账单查询证据型业务族",
        "accept_when": [
            "客户主要诉求有明确账单证据：账单金额、每期金额、剩余本金、欠款、还款计划、扣款明细、扣款异常、重复扣款、多扣/少扣、还款后账单未更新、还款状态异常、提前结清金额/利息/计划、结清证明或还清状态中的任一子场景。",
            "pred skill 在 acceptable_skill_ids_from_mapping 内，并且与客户话语中的子场景证据匹配；例如扣款异常对应 deduction_issues，还款未更新对应 repayment_status_issue，提前结清金额对应 early_loan_clearance，结清证明对应 clearance_certificate。",
            "如果一通电话里先查账单、再转到扣款异常/提前结清/结清证明，只要命中的 skill 覆盖了真实展开后的账单相关子场景，可判 true。",
        ],
        "reject_when": [
            "客户主要诉求不是账单、扣款、还款状态、提前结清金额/计划或结清证明相关。",
            "pred skill 是换绑卡、销户、催收、征信/代偿、普通贷款咨询、非我司产品等非账单业务，且没有承接账单子场景。",
            "客户话语只有流程确认、核身、问候或模糊应答，没有能支撑账单查询业务族的具体证据。",
        ],
    },
    "营销活动/会员退费": {
        "policy_name": "product_service_action_family",
        "evaluation_unit": "会员/优享卡/轻享卡/增值服务产品服务族",
        "accept_when": [
            "客户主要诉求属于会员、优享卡、轻享卡、权益卡、权益包、增值服务等产品服务的咨询、取消/关闭续费、扣费解释、退费/退款任一动作。",
            "当前生产结构保留 member_* 和 premium_card_* 作为重要产品专属 skill，同时保留 value_added_service_* 与 light_card_cancel_refund 作为泛产品服务兜底；这些映射内 skill 可以互为合理命中。",
            "不要因为 gold_intent 字面是“会员退费”就否定优享卡取消/咨询/退费、轻享卡取消/退费、增值服务咨询/取消/退费等映射内命中。",
        ],
        "reject_when": [
            "客户主要诉求与产品服务、活动权益、会员卡权益无关。",
            "pred skill 虽在 TopK 中，但实际只回答账单、还款、催收、放款或贷后核实等非产品服务问题。",
            "客户话语只有流程确认或核身信息，没有可判断的产品服务动作。",
        ],
    },
    "营销活动/新活动咨询": {
        "policy_name": "marketing_product_service_family",
        "evaluation_unit": "活动/产品服务业务族",
        "accept_when": [
            "merged 标注中的新活动咨询是粗标签，实际可能是会员、优享卡、轻享卡、权益包、增值服务、营销触达等产品服务相关咨询、取消、退费或停止营销动作。",
            "pred skill 在 acceptable_skill_ids_from_mapping 内，并且能承接客户真实的活动/产品服务动作，即可判 true。",
            "如果命中的是 member_*、premium_card_*、value_added_service_*、light_card_cancel_refund 或 stop_marketing，应按产品服务族或营销动作判断，不按“新活动”四个字做严格限制。",
        ],
        "reject_when": [
            "客户主要诉求不是活动、权益、产品服务或营销触达相关。",
            "pred skill 实际承接的是还款、账单、催收、放款、证明等其他业务族。",
            "客户话语没有清晰业务动作，只是确认、寒暄、核身或流程配合。",
        ],
    },
    "产品与信息/非我司产品": {
        "policy_name": "external_or_unowned_product_family",
        "evaluation_unit": "非我司/导流/未命中产品归属业务族",
        "accept_when": [
            "客户主要诉求是在问非我司产品、导流产品、合作方/第三方平台、未知产品归属、非本公司扣费/贷款/服务的来源、处理入口或联系方式。",
            "当前链路不为每个非我司产品单独建 skill，允许通过增值服务咨询、贷款咨询、放款进度、贷后核实、账单扣款查询等映射内 skill 承接不同落点。",
            "只要 pred skill 在 acceptable_skill_ids_from_mapping 内，且能把客户引向对应的归属澄清、非我司说明、查询或转接处理，就应判 true。",
        ],
        "reject_when": [
            "客户问的是我司明确贷款、账单、还款、催收等普通业务，不涉及非我司/合作方/未知产品归属。",
            "pred skill 只解决内部单一业务，无法支持非我司产品识别、澄清或引导。",
            "客户话语没有具体业务信息，不能判断为非我司产品问题。",
        ],
    },
}

SESSION_FLOW_SKILLS = {
    "greeting_opening",
    "identity_readback",
    "acknowledgement",
    "channel_check",
    "closing",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def empty_state(session_id: str) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        customer=CustomerInfo(),
        intent=IntentState(),
    )


def keyword_overlap_score(query: str, skill) -> float:
    keywords = skill.triggers.keywords or []
    if not query or not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if kw and kw in query)
    return min(1.0, hits / 3.0)


def load_route_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_route_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def parse_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def load_intent_mapping(path: Path, loader: SkillLoader) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = {
        item["intent"]: list(item.get("skill_ids") or [])
        for item in data.get("mappings", [])
    }
    known = set(loader.get_all_skill_ids())
    unknown = sorted({sid for sids in mapping.values() for sid in sids if sid not in known})
    if unknown:
        raise ValueError(f"intent mapping references unknown skill ids: {unknown}")
    return mapping


def parse_audit_intents(value: str, intent_mapping: dict[str, list[str]]) -> set[str]:
    value = (value or "").strip()
    if not value or value.lower() in {"none", "off", "false"}:
        return set()
    if value == "default":
        return set(DEFAULT_AUDIT_INTENTS)
    if value == "all-one-to-many":
        return {intent for intent, skill_ids in intent_mapping.items() if len(skill_ids) > 1}
    return {item.strip() for item in value.split(",") if item.strip()}


def get_total_merged_samples(call_count: int) -> int:
    if CHUNK_SUMMARY_PATH.exists():
        try:
            data = json.loads(CHUNK_SUMMARY_PATH.read_text(encoding="utf-8"))
            return int(data.get("unique_records") or call_count)
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return call_count


class QueryRouter:
    def __init__(
        self,
        *,
        route_mode: str,
        multi_domain_k: int,
        skill_cos_top_m: int,
        candidate_source: str,
        max_candidates: int,
        prior_skill_weight: float,
        prior_domain_weight: float,
        prior_keyword_weight: float,
        use_fewshot: bool,
        fewshot_k: int,
    ) -> None:
        self.route_mode = route_mode
        self.multi_domain_k = multi_domain_k
        self.skill_cos_top_m = skill_cos_top_m
        self.candidate_source = candidate_source
        self.max_candidates = max_candidates
        self.prior_skill_weight = prior_skill_weight
        self.prior_domain_weight = prior_domain_weight
        self.prior_keyword_weight = prior_keyword_weight

        settings = get_settings()
        self.settings = settings
        self.loader = SkillLoader(
            str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
            str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
        )
        self.domain_clf = EmbeddingDomainClassifier(
            api_url=settings.EMBED_API_URL,
            model=settings.EMBED_MODEL,
            timeout=settings.LLM_TIMEOUT,
        )
        self.skill_index = SkillEmbeddingIndex(
            self.loader,
            api_url=settings.EMBED_API_URL,
            model=settings.EMBED_MODEL,
            timeout=settings.LLM_TIMEOUT,
        )
        self.retriever = FewShotRetriever() if use_fewshot and route_mode == "router" else None
        self.llm_client: LLMClient | None = None
        self.router: SkillRouter | None = None
        if route_mode == "router":
            self.llm_client = LLMClient(
                base_url=settings.LLM_API_URL,
                api_key=settings.LLM_API_KEY,
                model=settings.LLM_MODEL,
                timeout=settings.LLM_TIMEOUT,
            )
            self.router = SkillRouter(
                llm_client=self.llm_client,
                skill_loader=self.loader,
                prompt_path=str(settings.resolve_path(settings.SKILL_PROMPTS_DIR) / "skill_routing.md"),
                fewshot_retriever=self.retriever,
                fewshot_k=fewshot_k,
            )

        self.query_vector_cache: dict[str, list[float]] = {}

    async def close(self) -> None:
        if self.llm_client is not None:
            await self.llm_client.close()

    def get_query_vector(self, query: str) -> list[float]:
        cached = self.query_vector_cache.get(query)
        if cached is not None:
            return cached
        vector = self.domain_clf.embed_query(query)
        self.query_vector_cache[query] = vector
        return vector

    def build_candidates(self, query: str, state: ConversationState) -> dict[str, Any]:
        q_vec = self.get_query_vector(query)
        domain_pairs = self.domain_clf.classify_topk_from_vector(
            q_vec, state, k=self.multi_domain_k,
        )
        pred_domains = [domain for domain, _ in domain_pairs]
        skill_pairs = self.skill_index.rank_vector(q_vec, k=self.skill_cos_top_m)

        domain_scores = dict(domain_pairs)
        skill_scores = dict(skill_pairs)

        domain_candidate_ids: list[str] = []
        for domain in pred_domains:
            for skill in self.loader.get_skills_by_domain(domain):
                if skill.skill_id not in domain_candidate_ids:
                    domain_candidate_ids.append(skill.skill_id)
        skill_candidate_ids = [sid for sid, _ in skill_pairs]

        if self.candidate_source == "domain":
            candidate_ids = list(domain_candidate_ids)
        elif self.candidate_source == "skill":
            candidate_ids = list(skill_candidate_ids)
        else:
            candidate_ids = list(domain_candidate_ids)
            for sid in skill_candidate_ids:
                if sid not in candidate_ids:
                    candidate_ids.append(sid)

        candidate_priors: dict[str, dict[str, Any]] = {}
        candidates = []
        for sid in candidate_ids:
            skill = self.loader.get_skill(sid)
            if skill is None:
                continue
            domain_cos = domain_scores.get(skill.domain)
            skill_cos = skill_scores.get(sid)
            overlap = keyword_overlap_score(query, skill)
            prior_score = (
                self.prior_skill_weight * (skill_cos or 0.0)
                + self.prior_domain_weight * (domain_cos or 0.0)
                + self.prior_keyword_weight * overlap
            )
            source_bits = []
            if sid in domain_candidate_ids:
                source_bits.append("domain")
            if sid in skill_candidate_ids:
                source_bits.append("skill_cos")
            candidate_priors[sid] = {
                "domain_cos": domain_cos,
                "skill_cos": skill_cos,
                "keyword_overlap": overlap,
                "prior_score": prior_score,
                "source": "+".join(source_bits) or "unknown",
            }
            candidates.append(skill)

        candidates.sort(
            key=lambda s: (
                -candidate_priors.get(s.skill_id, {}).get("prior_score", 0.0),
                -candidate_priors.get(s.skill_id, {}).get("skill_cos", 0.0)
                if candidate_priors.get(s.skill_id, {}).get("skill_cos") is not None else 0.0,
                -s.priority,
            )
        )
        if self.max_candidates > 0:
            candidates = candidates[:self.max_candidates]
            kept = {skill.skill_id for skill in candidates}
            candidate_priors = {
                sid: prior
                for sid, prior in candidate_priors.items()
                if sid in kept
            }

        return {
            "q_vec": q_vec,
            "pred_domains": pred_domains,
            "pred_domain_scores": domain_pairs,
            "skill_cos_topk": skill_pairs,
            "candidates": candidates,
            "candidate_priors": candidate_priors,
        }

    async def route_query(
        self,
        item: dict[str, Any],
        *,
        state: ConversationState | None = None,
        sliding_window_text: str = "",
    ) -> dict[str, Any]:
        query = item["query"]
        state = state or empty_state(item["call_id"])
        prepared = self.build_candidates(query, state)
        state.intent.domain = prepared["pred_domains"][0] if prepared["pred_domains"] else None

        if self.route_mode == "skill-cos":
            ranked = [
                {"skill_id": sid, "score": round(score, 4)}
                for sid, score in prepared["skill_cos_topk"]
            ]
            pred_skill = ranked[0]["skill_id"] if ranked else "none"
            confidence = ranked[0]["score"] if ranked else 0.0
            topk_skills = [row["skill_id"] for row in ranked[:3]]
            error = ""
        else:
            assert self.router is not None
            try:
                match = await self.router.route_over_candidates(
                    query,
                    prepared["candidates"],
                    state,
                    sliding_window_text=sliding_window_text,
                    summary="",
                    candidate_priors=prepared["candidate_priors"],
                )
                pred_skill = match.skill_id
                confidence = match.confidence
                topk_skills = match.top_k_skill_ids(k=3)
                ranked = match.alternatives
                error = ""
            except Exception as exc:
                pred_skill = "none"
                confidence = 0.0
                topk_skills = []
                ranked = []
                error = str(exc)

        return {
            "sample_id": item["sample_id"],
            "call_id": item["call_id"],
            "record_index": item["record_index"],
            "query_index": item["query_index"],
            "turn_id": item["turn_id"],
            "query": query,
            "pred_skill": pred_skill,
            "topk_skills": topk_skills,
            "confidence": confidence,
            "pred_domains_topk": prepared["pred_domains"],
            "pred_domain_scores": [
                [domain, round(score, 4)]
                for domain, score in prepared["pred_domain_scores"]
            ],
            "skill_cos_topk": [
                [sid, round(score, 4)]
                for sid, score in prepared["skill_cos_topk"]
            ],
            "candidate_count": len(prepared["candidates"]),
            "alternatives": ranked,
            "error": error,
        }


def flatten_call_queries(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for call in calls:
        for query in call.get("queries", []):
            items.append({
                "sample_id": query["sample_id"],
                "call_id": call["call_id"],
                "record_index": call["record_index"],
                "query_index": query["query_index"],
                "turn_id": query["turn_id"],
                "query": query["query"],
                "gold_intents": call.get("gold_intents", []),
            })
    return items


def route_cache_key(
    route_mode: str,
    item: dict[str, Any],
    args: argparse.Namespace,
    *,
    context_key: str = "",
) -> str:
    params = {
        "mode": route_mode,
        "turn_mode": args.turn_mode,
        "sample_id": item["sample_id"],
        "query": item["query"],
        "context": context_key,
        "multi_domain_k": args.multi_domain_k,
        "skill_cos_top_m": args.skill_cos_top_m,
        "candidate_source": args.candidate_source,
        "max_candidates": args.max_candidates,
        "model": get_settings().LLM_MODEL if route_mode == "router" else "",
    }
    return json.dumps(params, ensure_ascii=False, sort_keys=True)


async def route_all(
    args: argparse.Namespace,
    calls: list[dict[str, Any]],
    out_dir: Path,
) -> list[dict[str, Any]]:
    router = QueryRouter(
        route_mode=args.route_mode,
        multi_domain_k=args.multi_domain_k,
        skill_cos_top_m=args.skill_cos_top_m,
        candidate_source=args.candidate_source,
        max_candidates=args.max_candidates,
        prior_skill_weight=args.prior_skill_weight,
        prior_domain_weight=args.prior_domain_weight,
        prior_keyword_weight=args.prior_keyword_weight,
        use_fewshot=args.use_fewshot,
        fewshot_k=args.fewshot_k,
    )
    cache = load_route_cache(CACHE_PATH) if args.use_cache else {}
    items = flatten_call_queries(calls)
    sem = asyncio.Semaphore(args.concurrency)
    results: list[dict[str, Any]] = []
    done = 0

    def format_sliding_window(history: list[str]) -> str:
        if not history:
            return ""
        return "\n".join(f"客户: {text}" for text in history[-8:])

    def update_state_after_prediction(
        state: ConversationState,
        item: dict[str, Any],
        prediction: dict[str, Any],
    ) -> None:
        previous_skill = state.intent.current_skill_id
        pred_skill = prediction.get("pred_skill") or "none"
        if pred_skill != "none":
            state.intent.current_skill_id = pred_skill
        if pred_skill == previous_skill:
            state.intent.turn_in_skill += 1
        else:
            state.intent.turn_in_skill = 1 if pred_skill != "none" else 0
        domains = prediction.get("pred_domains_topk") or []
        if domains:
            state.intent.domain = domains[0]
        state.messages.append(
            Message(
                role="customer",
                text=item["query"],
                turn=int(item.get("query_index") or len(state.messages) + 1),
            )
        )
        state.total_turns += 1

    async def run_one(
        item: dict[str, Any],
        *,
        state: ConversationState | None = None,
        history: list[str] | None = None,
    ) -> dict[str, Any]:
        nonlocal done
        context = format_sliding_window(history or [])
        key = route_cache_key(args.route_mode, item, args, context_key=context)
        if args.use_cache and key in cache:
            result = cache[key]
        else:
            async with sem:
                result = await router.route_query(
                    item,
                    state=state,
                    sliding_window_text=context,
                )
            if args.use_cache:
                cache[key] = result
        done += 1
        if done % args.progress_every == 0 or done == len(items):
            print(f"  routed {done}/{len(items)}", flush=True)
            if args.use_cache:
                save_route_cache(CACHE_PATH, cache)
        return result

    try:
        print(
            f"Routing {len(items)} queries with mode={args.route_mode}, "
            f"turn_mode={args.turn_mode}, concurrency={args.concurrency}"
        )
        if args.turn_mode == "independent":
            results = await asyncio.gather(*(run_one(item) for item in items))
        else:
            results_by_call: dict[str, list[dict[str, Any]]] = {}

            async def run_call(call: dict[str, Any]) -> None:
                call_state = empty_state(call["call_id"])
                history: list[str] = []
                call_results: list[dict[str, Any]] = []
                for query in call.get("queries", []):
                    item = {
                        "sample_id": query["sample_id"],
                        "call_id": call["call_id"],
                        "record_index": call["record_index"],
                        "query_index": query["query_index"],
                        "turn_id": query["turn_id"],
                        "query": query["query"],
                        "gold_intents": call.get("gold_intents", []),
                    }
                    prediction = await run_one(item, state=call_state, history=history)
                    call_results.append(prediction)
                    update_state_after_prediction(call_state, item, prediction)
                    history.append(item["query"])
                results_by_call[call["call_id"]] = call_results

            await asyncio.gather(*(run_call(call) for call in calls))
            results = []
            for call in calls:
                results.extend(results_by_call.get(call["call_id"], []))
    finally:
        if args.use_cache:
            save_route_cache(CACHE_PATH, cache)
        await router.close()

    write_jsonl(out_dir / "query_predictions.jsonl", results)
    return results


def rank_call_skills(predictions: list[dict[str, Any]], exclude_session_flow: bool) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    conf_sum: defaultdict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    for idx, pred in enumerate(predictions):
        sid = pred.get("pred_skill") or "none"
        if sid == "none":
            continue
        if exclude_session_flow and sid in SESSION_FLOW_SKILLS:
            continue
        counts[sid] += 1
        conf_sum[sid] += float(pred.get("confidence") or 0.0)
        first_seen.setdefault(sid, idx)

    ranked = []
    for sid, count in counts.items():
        ranked.append({
            "skill_id": sid,
            "count": count,
            "avg_confidence": round(conf_sum[sid] / count, 4) if count else 0.0,
            "first_seen": first_seen[sid],
        })
    ranked.sort(key=lambda item: (-item["count"], -item["avg_confidence"], item["first_seen"], item["skill_id"]))
    return ranked


def score_calls(
    calls: list[dict[str, Any]],
    query_predictions: list[dict[str, Any]],
    intent_mapping: dict[str, list[str]],
    *,
    exclude_session_flow: bool,
) -> list[dict[str, Any]]:
    preds_by_call: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for pred in query_predictions:
        preds_by_call[pred["call_id"]].append(pred)

    scored: list[dict[str, Any]] = []
    for call in calls:
        gold_items = []
        unmapped = []
        for intent in call.get("gold_intents", []):
            skill_ids = intent_mapping.get(intent)
            if not skill_ids:
                unmapped.append(intent)
                continue
            gold_items.append({
                "intent": intent,
                "skill_ids": skill_ids,
            })

        k = len(gold_items)
        ranked = rank_call_skills(preds_by_call.get(call["call_id"], []), exclude_session_flow)
        topk = [item["skill_id"] for item in ranked[:k]] if k > 0 else []
        hits = []
        misses = []
        topk_set = set(topk)
        for gold in gold_items:
            matched_skill_ids = sorted(topk_set & set(gold["skill_ids"]))
            gold_with_match = dict(gold)
            gold_with_match["matched_skill_ids"] = matched_skill_ids
            (hits if matched_skill_ids else misses).append(gold_with_match)

        score = len(hits) / k if k else 0.0
        scored.append({
            "call_id": call["call_id"],
            "record_index": call["record_index"],
            "gold_intents": call.get("gold_intents", []),
            "mapped_gold_intents": gold_items,
            "unmapped_gold_intents": unmapped,
            "gold_k": k,
            "predicted_skill_ranking": ranked,
            "predicted_topk": topk,
            "hit_count": len(hits),
            "miss_count": len(misses),
            "score": round(score, 6),
            "hit_gold_intents": hits,
            "missed_gold_intents": misses,
            "query_count": len(call.get("queries", [])),
            "routed_query_count": len(preds_by_call.get(call["call_id"], [])),
        })
    return scored


def get_audit_intent_policy(intent: str) -> dict[str, Any]:
    policy = AUDIT_INTENT_POLICIES.get(intent)
    if policy:
        return policy
    return {
        "policy_name": "generic_one_to_many_family",
        "evaluation_unit": "映射表配置的一对多业务族",
        "accept_when": [
            "客户主要诉求落在 gold_intent 对应的业务族内。",
            "pred skill 在 acceptable_skill_ids_from_mapping 内，并且能承接客户真实业务动作。",
        ],
        "reject_when": [
            "客户主要诉求与该业务族无关。",
            "pred skill 只是宽映射误命中，不能处理客户真实诉求。",
            "客户话语只有流程、核身、问候或确认信息，缺少可判断业务动作。",
        ],
    }


def skill_audit_snapshot(loader: SkillLoader, sid: str, *, include_description: bool = True) -> dict[str, Any]:
    skill = loader.get_skill(sid)
    if not skill:
        return {
            "skill_id": sid,
            "name": sid,
            "description": "",
            "intent_hierarchy": {},
        }
    snapshot = {
        "skill_id": sid,
        "name": skill.name,
        "intent_hierarchy": skill.intent_hierarchy,
    }
    if include_description:
        snapshot["description"] = skill.description
    return snapshot


def one_to_many_audit_key(
    call: dict[str, Any],
    row: dict[str, Any],
    hit: dict[str, Any],
    settings_model: str,
) -> str:
    policy = get_audit_intent_policy(hit["intent"])
    payload = {
        "audit_prompt_version": AUDIT_PROMPT_VERSION,
        "audit_policy_name": policy["policy_name"],
        "call_id": row["call_id"],
        "record_index": row["record_index"],
        "gold_intent": hit["intent"],
        "matched_skill_ids": hit.get("matched_skill_ids") or [],
        "predicted_topk": row.get("predicted_topk") or [],
        "queries": [q.get("query") for q in call.get("queries", [])],
        "model": settings_model,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_audit_prompt(
    *,
    call: dict[str, Any],
    row: dict[str, Any],
    hit: dict[str, Any],
    loader: SkillLoader,
) -> list[dict[str, str]]:
    policy = get_audit_intent_policy(hit["intent"])
    matched_skills = [
        skill_audit_snapshot(loader, sid, include_description=True)
        for sid in hit.get("matched_skill_ids") or []
    ]
    acceptable_skills = [
        skill_audit_snapshot(loader, sid, include_description=False)
        for sid in hit.get("skill_ids") or []
    ]
    queries = [
        {
            "query_index": q.get("query_index"),
            "query": q.get("query"),
        }
        for q in call.get("queries", [])
    ]
    payload = {
        "audit_prompt_version": AUDIT_PROMPT_VERSION,
        "gold_intent": hit["intent"],
        "audit_policy": policy,
        "acceptable_skill_ids_from_mapping": hit.get("skill_ids") or [],
        "acceptable_skill_brief": acceptable_skills,
        "matched_skill_ids_to_audit": hit.get("matched_skill_ids") or [],
        "matched_skill_definitions": matched_skills,
        "predicted_topk": row.get("predicted_topk") or [],
        "predicted_skill_ranking": row.get("predicted_skill_ranking") or [],
        "customer_queries_in_call": queries,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是金融客服意图评测复核员。你的任务是判断一次一对多映射命中是否真实合理。\n"
                "只判断 pred skill 是否能覆盖该通电话中的真实客户业务诉求，不评价坐席回复质量。\n"
                "评测口径以 acceptable_skill_ids_from_mapping 和 audit_policy 为准；"
                "不要按 gold_intent 的字面名称做严格同义判断。\n"
                "对配置为一对多映射的业务族，如果 pred skill 在映射表内，且客户话语真实落在该业务族，"
                "应判 true；不要求 pred skill 与 gold_intent 文案完全同名。\n"
                "会员、优享卡、轻享卡、增值服务这类当前是“重要产品专属 skill + 泛增值服务兜底”结构，"
                "复核时按产品服务族和动作判断，不要把专属 skill 与兜底 skill 当成互斥错误。\n"
                "仍然需要判 false 的情况：客户主要诉求与该业务族无关，pred skill 不在映射可接受范围内，"
                "或客户话语只有流程、核身、问候、确认等无业务信息。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请基于下面 JSON 复核。返回严格 JSON：\n"
                "{\n"
                '  "acceptable": true/false,\n'
                '  "accepted_skill_id": "命中的 skill_id 或空字符串",\n'
                '  "reason": "一句中文理由"\n'
                "}\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


async def audit_one_to_many_hits(
    *,
    args: argparse.Namespace,
    calls: list[dict[str, Any]],
    call_scores: list[dict[str, Any]],
    audit_intents: set[str],
    loader: SkillLoader,
    out_dir: Path,
) -> list[dict[str, Any]]:
    if not args.llm_audit_one_to_many or not audit_intents:
        return []

    settings = get_settings()
    llm_client = LLMClient(
        base_url=settings.LLM_API_URL,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        timeout=settings.LLM_TIMEOUT,
    )
    cache = load_route_cache(AUDIT_CACHE_PATH) if args.use_cache else {}
    calls_by_id = {call["call_id"]: call for call in calls}
    decisions: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(args.audit_concurrency)
    jobs: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []

    for row in call_scores:
        call = calls_by_id.get(row["call_id"])
        if not call:
            continue
        for hit in row.get("hit_gold_intents", []):
            if hit.get("intent") in audit_intents and hit.get("matched_skill_ids"):
                jobs.append((call, row, hit))

    async def audit_one(
        call: dict[str, Any],
        row: dict[str, Any],
        hit: dict[str, Any],
    ) -> dict[str, Any]:
        key = one_to_many_audit_key(call, row, hit, settings.LLM_MODEL)
        if args.use_cache and key in cache:
            cached = cache[key]
            return dict(cached, from_cache=True)
        messages = build_audit_prompt(call=call, row=row, hit=hit, loader=loader)
        async with sem:
            raw = await llm_client.chat_completion(
                messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        data = parse_json_object(raw)
        acceptable = bool(data.get("acceptable"))
        matched_skill_ids = hit.get("matched_skill_ids") or []
        accepted_skill_id = str(data.get("accepted_skill_id") or "")
        if acceptable and accepted_skill_id not in matched_skill_ids:
            accepted_skill_id = matched_skill_ids[0]
        decision = {
            "audit_prompt_version": AUDIT_PROMPT_VERSION,
            "audit_policy_name": get_audit_intent_policy(hit["intent"])["policy_name"],
            "call_id": row["call_id"],
            "record_index": row["record_index"],
            "gold_intent": hit["intent"],
            "matched_skill_ids": matched_skill_ids,
            "predicted_topk": row.get("predicted_topk") or [],
            "acceptable": acceptable,
            "accepted_skill_id": accepted_skill_id if acceptable else "",
            "reason": str(data.get("reason") or "").strip(),
            "raw_response": raw,
            "from_cache": False,
            "error": "" if data else "empty_or_invalid_json",
        }
        if args.use_cache:
            cache[key] = decision
        return decision

    try:
        if jobs:
            print(f"Auditing {len(jobs)} one-to-many mapped hits with LLM", flush=True)
        for idx, task in enumerate(asyncio.as_completed([audit_one(*job) for job in jobs]), start=1):
            decision = await task
            decisions.append(decision)
            if idx % args.progress_every == 0 or idx == len(jobs):
                print(f"  audited {idx}/{len(jobs)}", flush=True)
                if args.use_cache:
                    save_route_cache(AUDIT_CACHE_PATH, cache)
    finally:
        if args.use_cache:
            save_route_cache(AUDIT_CACHE_PATH, cache)
        await llm_client.close()

    write_jsonl(out_dir / "llm_audit_decisions.jsonl", decisions)
    return decisions


def apply_audit_to_scores(
    call_scores: list[dict[str, Any]],
    audit_decisions: list[dict[str, Any]],
    audit_intents: set[str],
) -> list[dict[str, Any]]:
    decision_map = {
        (row["call_id"], row["gold_intent"]): row
        for row in audit_decisions
    }
    audited_rows: list[dict[str, Any]] = []
    for row in call_scores:
        audited_hits = []
        audited_misses = list(row.get("missed_gold_intents", []))
        audit_rejections = []
        for hit in row.get("hit_gold_intents", []):
            if hit.get("intent") not in audit_intents:
                audited_hits.append(hit)
                continue
            decision = decision_map.get((row["call_id"], hit["intent"]))
            if decision and decision.get("acceptable"):
                audited_hit = dict(hit)
                audited_hit["audit_decision"] = decision
                audited_hits.append(audited_hit)
            else:
                audited_miss = dict(hit)
                audited_miss["audit_decision"] = decision or {
                    "acceptable": False,
                    "reason": "missing audit decision",
                }
                audited_misses.append(audited_miss)
                audit_rejections.append(audited_miss)

        k = row.get("gold_k") or 0
        score = len(audited_hits) / k if k else 0.0
        audited_row = dict(row)
        audited_row.update({
            "score": round(score, 6),
            "hit_count": len(audited_hits),
            "miss_count": len(audited_misses),
            "hit_gold_intents": audited_hits,
            "missed_gold_intents": audited_misses,
            "audit_rejections": audit_rejections,
        })
        audited_rows.append(audited_row)
    return audited_rows


def build_metric_breakdown(
    *,
    args: argparse.Namespace,
    call_scores: list[dict[str, Any]],
    audited_call_scores: list[dict[str, Any]],
    audit_decisions: list[dict[str, Any]],
    audit_intents: set[str],
    total_samples: int,
) -> dict[str, Any]:
    denominator = total_samples if args.denominator == "merged" else len(call_scores)
    direct_total = sum(row["score"] for row in call_scores)
    audited_total = sum(row["score"] for row in audited_call_scores)

    non_audit_rows = (
        [
            row for row in call_scores
            if not (set(row.get("gold_intents", [])) & audit_intents)
        ]
        if audit_intents else list(call_scores)
    )
    non_audit_total = sum(row["score"] for row in non_audit_rows)
    non_audit_denominator = len(non_audit_rows)

    accepted = sum(1 for row in audit_decisions if row.get("acceptable"))
    rejected = sum(1 for row in audit_decisions if not row.get("acceptable"))
    errors = sum(1 for row in audit_decisions if row.get("error"))

    return {
        "audit_intents": sorted(audit_intents),
        "direct_mapped_accuracy": {
            "scope": args.denominator,
            "score_percent": round(direct_total / denominator * 100.0, 4) if denominator else 0.0,
            "total_score": round(direct_total, 6),
            "denominator": denominator,
        },
        "non_one_to_many_accuracy": {
            "scope": (
                "calls_without_one_to_many_audit_intents"
                if audit_intents else "all_calls_audit_disabled"
            ),
            "score_percent": round(non_audit_total / non_audit_denominator * 100.0, 4)
            if non_audit_denominator else 0.0,
            "total_score": round(non_audit_total, 6),
            "denominator": non_audit_denominator,
        },
        "llm_audited_accuracy": {
            "enabled": args.llm_audit_one_to_many and bool(audit_intents),
            "audit_prompt_version": AUDIT_PROMPT_VERSION,
            "scope": args.denominator,
            "score_percent": round(audited_total / denominator * 100.0, 4) if denominator else 0.0,
            "total_score": round(audited_total, 6),
            "denominator": denominator,
            "audit_decisions": len(audit_decisions),
            "audit_accepted": accepted,
            "audit_rejected": rejected,
            "audit_errors": errors,
        },
    }


def build_summary(
    args: argparse.Namespace,
    calls: list[dict[str, Any]],
    call_scores: list[dict[str, Any]],
    query_predictions: list[dict[str, Any]],
    total_samples: int,
    metric_breakdown: dict[str, Any],
) -> dict[str, Any]:
    total_score = sum(row["score"] for row in call_scores)
    denominator = total_samples if args.denominator == "merged" else len(calls)
    percent = (total_score / denominator * 100.0) if denominator else 0.0
    evaluated_percent = (total_score / len(calls) * 100.0) if calls else 0.0
    zero_scores = [row for row in call_scores if row["score"] == 0]
    full_scores = [row for row in call_scores if row["score"] == 1]
    errors = [row for row in query_predictions if row.get("error")]

    confusion = Counter()
    for row in call_scores:
        for miss in row["missed_gold_intents"]:
            confusion[(miss["intent"], tuple(row["predicted_topk"]))] += 1

    return {
        "route_mode": args.route_mode,
        "input_calls": str(args.calls),
        "intent_mapping": str(args.intent_mapping),
        "total_merged_samples": total_samples,
        "call_records_with_queries": len(calls),
        "query_predictions": len(query_predictions),
        "denominator_mode": args.denominator,
        "score_percent": round(percent, 4),
        "score_fraction": round(total_score / denominator, 6) if denominator else 0.0,
        "total_score": round(total_score, 6),
        "denominator": denominator,
        "score_percent_over_calls_with_queries": round(evaluated_percent, 4),
        "full_score_calls": len(full_scores),
        "zero_score_calls": len(zero_scores),
        "router_errors": len(errors),
        "unmapped_intent_calls": sum(1 for row in call_scores if row["unmapped_gold_intents"]),
        "top_missed_intents": [
            {"intent": intent, "predicted_topk": list(topk), "count": count}
            for (intent, topk), count in confusion.most_common(20)
        ],
        "session_flow_skills_filtered": args.exclude_session_flow,
        "metric_breakdown": metric_breakdown,
        "params": {
            "turn_mode": args.turn_mode,
            "multi_domain_k": args.multi_domain_k,
            "skill_cos_top_m": args.skill_cos_top_m,
            "candidate_source": args.candidate_source,
            "max_candidates": args.max_candidates,
            "concurrency": args.concurrency,
            "limit": args.limit,
            "llm_audit_one_to_many": args.llm_audit_one_to_many,
            "audit_intents": args.audit_intents,
            "audit_prompt_version": AUDIT_PROMPT_VERSION,
        },
    }


async def async_main(args: argparse.Namespace) -> int:
    calls = load_jsonl(args.calls)
    if args.limit:
        calls = calls[:args.limit]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or ROOT / "tests" / "reports" / f"merged_multi_turn_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Initialise loader once for mapping validation. QueryRouter will initialise
    # its own loader when routing.
    settings = get_settings()
    loader = SkillLoader(
        str(settings.resolve_path(settings.SKILL_DEFINITIONS_DIR)),
        str(settings.resolve_path(settings.SKILL_REGISTRY_PATH)),
    )
    intent_mapping = load_intent_mapping(args.intent_mapping, loader)
    audit_intents = (
        parse_audit_intents(args.audit_intents, intent_mapping)
        if args.llm_audit_one_to_many else set()
    )

    start = time.time()
    query_predictions = await route_all(args, calls, out_dir)
    call_scores = score_calls(
        calls,
        query_predictions,
        intent_mapping,
        exclude_session_flow=args.exclude_session_flow,
    )
    write_jsonl(out_dir / "call_scores.jsonl", call_scores)

    total_samples = len(calls) if args.limit else get_total_merged_samples(len(calls))
    audit_decisions = await audit_one_to_many_hits(
        args=args,
        calls=calls,
        call_scores=call_scores,
        audit_intents=audit_intents,
        loader=loader,
        out_dir=out_dir,
    )
    if args.llm_audit_one_to_many and audit_intents:
        audited_call_scores = apply_audit_to_scores(call_scores, audit_decisions, audit_intents)
        write_jsonl(out_dir / "call_scores_llm_audited.jsonl", audited_call_scores)
    else:
        audited_call_scores = list(call_scores)

    metric_breakdown = build_metric_breakdown(
        args=args,
        call_scores=call_scores,
        audited_call_scores=audited_call_scores,
        audit_decisions=audit_decisions,
        audit_intents=audit_intents,
        total_samples=total_samples,
    )
    summary = build_summary(
        args,
        calls,
        call_scores,
        query_predictions,
        total_samples,
        metric_breakdown,
    )
    summary["elapsed_seconds"] = round(time.time() - start, 2)
    summary["output_dir"] = str(out_dir)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n── Merged Multi-turn Skill Recall ──")
    print(f"Output dir: {out_dir}")
    print(f"Route mode: {args.route_mode}")
    print(f"Intent mapping: {args.intent_mapping}")
    print(f"Calls with queries: {len(calls)}")
    print(f"Query predictions: {len(query_predictions)}")
    print(f"Score: {summary['score_percent']:.2f}%  ({summary['total_score']}/{summary['denominator']})")
    print("Metric breakdown:")
    print(
        "  1) Direct mapped: "
        f"{metric_breakdown['direct_mapped_accuracy']['score_percent']:.2f}% "
        f"({metric_breakdown['direct_mapped_accuracy']['total_score']}/"
        f"{metric_breakdown['direct_mapped_accuracy']['denominator']})"
    )
    if metric_breakdown["llm_audited_accuracy"]["enabled"]:
        print(
            "  2) Non-one-to-many: "
            f"{metric_breakdown['non_one_to_many_accuracy']['score_percent']:.2f}% "
            f"({metric_breakdown['non_one_to_many_accuracy']['total_score']}/"
            f"{metric_breakdown['non_one_to_many_accuracy']['denominator']})"
        )
        print(
            "  3) LLM audited: "
            f"{metric_breakdown['llm_audited_accuracy']['score_percent']:.2f}% "
            f"({metric_breakdown['llm_audited_accuracy']['total_score']}/"
            f"{metric_breakdown['llm_audited_accuracy']['denominator']}; "
            f"accepted={metric_breakdown['llm_audited_accuracy']['audit_accepted']}, "
            f"rejected={metric_breakdown['llm_audited_accuracy']['audit_rejected']})"
        )
    else:
        print("  2) LLM audited: disabled (using intent mapping directly)")
    print(f"Score over calls-with-queries: {summary['score_percent_over_calls_with_queries']:.2f}%")
    print(f"Full-score calls: {summary['full_score_calls']}; zero-score calls: {summary['zero_score_calls']}")
    print(f"Router errors: {summary['router_errors']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=Path, default=CALLS_PATH)
    parser.add_argument("--intent-mapping", type=Path, default=MAPPING_PATH)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--route-mode", choices=["router", "skill-cos"], default="router")
    parser.add_argument("--turn-mode", choices=["sequential", "independent"], default="sequential")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--use-cache", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--denominator", choices=["merged", "calls"], default="merged")
    parser.add_argument("--exclude-session-flow", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--llm-audit-one-to-many",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Optionally use LLM to audit mapped hits for configured one-to-many "
            "intent categories. Default is disabled because the intent mapping "
            "file is the scoring source of truth."
        ),
    )
    parser.add_argument(
        "--audit-intents",
        default="default",
        help=(
            "Comma-separated intent labels to audit; use 'default', 'all-one-to-many', or 'none'. "
            "Default audits the recently widened mapping categories."
        ),
    )
    parser.add_argument("--audit-concurrency", type=int, default=4)

    parser.add_argument("--multi-domain-k", type=int, default=get_settings().SKILL_MULTI_DOMAIN_K)
    parser.add_argument("--skill-cos-top-m", type=int, default=get_settings().SKILL_COS_TOP_M)
    parser.add_argument("--candidate-source", choices=["domain", "skill", "hybrid"], default=get_settings().SKILL_CANDIDATE_SOURCE)
    parser.add_argument("--max-candidates", type=int, default=get_settings().SKILL_MAX_CANDIDATES)
    parser.add_argument("--prior-skill-weight", type=float, default=get_settings().PRIOR_SKILL_WEIGHT)
    parser.add_argument("--prior-domain-weight", type=float, default=get_settings().PRIOR_DOMAIN_WEIGHT)
    parser.add_argument("--prior-keyword-weight", type=float, default=get_settings().PRIOR_KEYWORD_WEIGHT)
    parser.add_argument("--use-fewshot", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fewshot-k", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
