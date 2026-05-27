"""Main orchestrator — dispatches requests through Chain A / B / C."""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fin_copilot.agents.compliant_generator import CompliantGenerator
from fin_copilot.agents.confidence_auditor import ConfidenceAuditor
from fin_copilot.agents.longtail_reasoner import LongtailReasoner
from fin_copilot.compliance.rule_checker import RuleComplianceChecker
from fin_copilot.config import Settings, get_settings
from fin_copilot.context.context_manager import ContextManager
from fin_copilot.models.audit import ConfidenceAuditResult
from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.response import CopilotResponse
from fin_copilot.models.skill import SkillMatch
from fin_copilot.routing.domain_classifier import DOMAIN_KEYWORDS, DomainClassifier
from fin_copilot.routing.rule_engine import RuleEngine, RuleMatchResult
from fin_copilot.routing.skill_router import SkillRouter
from fin_copilot.skills.branch_evaluator import select_branch_variant
from fin_copilot.skills.loader import SkillLoader
from fin_copilot.utils.template_engine import try_fill_template
from fin_copilot.utils.trace import generate_trace_id

# Ensure project root is importable so ``tools.*`` works
_project_root = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.executor import execute_tools  # noqa: E402
from tools.registry import WRITE_TOOLS  # noqa: E402
from fin_copilot.demo.verification import get_verification_db  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class _PendingExecution:
    response: CopilotResponse
    skill_id: str | None = None
    domain: str | None = None
    new_slots: dict[str, Any] = field(default_factory=dict)
    tools_called: list[str] = field(default_factory=list)


class Orchestrator:
    """Central request dispatcher for the three-chain architecture."""

    def __init__(
        self,
        context_mgr: ContextManager,
        rule_engine: RuleEngine,
        domain_classifier: DomainClassifier,
        skill_router: SkillRouter,
        skill_loader: SkillLoader,
        confidence_auditor: ConfidenceAuditor,
        compliant_generator: CompliantGenerator,
        compliance_checker: RuleComplianceChecker,
        longtail_reasoner: LongtailReasoner,
        value_added_knowledge: Any | None = None,
        skill_embedding_index: Any | None = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.ctx = context_mgr
        self.rule_engine = rule_engine
        self.domain_clf = domain_classifier
        self.keyword_domain_clf = DomainClassifier()
        self.skill_router = skill_router
        self.skill_loader = skill_loader
        self.skill_embedding_index = skill_embedding_index
        self.auditor = confidence_auditor
        self.generator = compliant_generator
        self.compliance = compliance_checker
        self.longtail = longtail_reasoner
        self.value_added_knowledge = value_added_knowledge
        self.settings = settings or get_settings()

    async def handle_turn(
        self,
        session_id: str,
        user_query: str,
    ) -> CopilotResponse:
        trace_id = generate_trace_id()
        start = time.monotonic()

        # Get / create session state
        state = self.ctx.get_or_create(session_id)

        # L0 preprocess
        query = self._preprocess(user_query)

        # Reference resolution (safe: short queries + anchor slots only).
        # Done early so every downstream module sees the resolved form.
        if self.settings.ENABLE_REFERENCE_RESOLUTION:
            resolved = self.ctx.resolve_references(state, query)
            if resolved != query:
                logger.info("reference resolved: %r -> %r", query, resolved)
                query = resolved

        # Pre-turn processing (risk flags + slot extraction)
        self.ctx.process_turn_start(state, query)

        # ----------------------------------------------------------
        # Proactive verification gate — fires on *every* turn so that a
        # user who volunteers 「名+手机+身份证后四位」 in any utterance gets
        # verified immediately, even if the step machine said not_started.
        # Matches demo verification data via _match_verification_payload.
        # ----------------------------------------------------------
        if not state.customer.verified:
            one_shot_cid = self._match_verification_payload(query)
            if one_shot_cid:
                pass_resp = self._verification_passed(state, one_shot_cid, trace_id)
                pending_exec = await self._consume_pending_route(state, trace_id)
                if pending_exec is not None:
                    response = self._merge_verified_business_response(
                        state, pending_exec.response,
                    )
                    self._finalize(
                        state, query, response, trace_id, start,
                        skill_id=pending_exec.skill_id,
                        domain=pending_exec.domain,
                        new_slots=pending_exec.new_slots,
                        tools_called=pending_exec.tools_called,
                    )
                    return response
                # Detect whether this turn carried a business intent beyond
                # the identity payload. If so, replay it after the pass msg.
                residual = self._strip_identity_payload(query, one_shot_cid)
                pending = state.customer.pending_query or residual
                state.customer.pending_query = ""
                self._finalize(state, query, pass_resp, trace_id, start)
                if pending and pending.strip():
                    biz = await self.handle_turn(session_id, pending)
                    pass_resp.answer = pass_resp.answer + "\n\n" + biz.answer
                    pass_resp.matched_skill_id = biz.matched_skill_id
                    pass_resp.matched_skill_name = biz.matched_skill_name
                    pass_resp.confidence = biz.confidence
                    pass_resp.route = biz.route
                    pass_resp.next_step_hint = biz.next_step_hint
                    pass_resp.tools_called = biz.tools_called
                    pass_resp.compliance_passed = biz.compliance_passed
                    pass_resp.compliance_issues = biz.compliance_issues
                    pass_resp.warning = biz.warning
                    pass_resp.latency_ms = (time.monotonic() - start) * 1000
                return pass_resp

        # ----------------------------------------------------------
        # Greeting / farewell detection (no LLM, no skill needed)
        # ----------------------------------------------------------
        greeting_resp = self._check_greeting(query, state, trace_id)
        if greeting_resp is not None:
            self._finalize(state, query, greeting_resp, trace_id, start)
            return greeting_resp

        # ----------------------------------------------------------
        # Identity verification flow — if in progress, handle it
        # before regular business routing.
        # ----------------------------------------------------------
        if state.customer.verification_step not in ("not_started", "passed"):
            verify_resp = self._handle_verification(state, query, trace_id)
            if verify_resp is not None:
                if state.customer.verification_step == "passed":
                    pending_exec = await self._consume_pending_route(state, trace_id)
                    if pending_exec is not None:
                        response = self._merge_verified_business_response(
                            state, pending_exec.response,
                        )
                        self._finalize(
                            state, query, response, trace_id, start,
                            skill_id=pending_exec.skill_id,
                            domain=pending_exec.domain,
                            new_slots=pending_exec.new_slots,
                            tools_called=pending_exec.tools_called,
                        )
                        return response
                self._finalize(state, query, verify_resp, trace_id, start)
                # If verification just passed and there's a pending query,
                # re-process it automatically.
                if (state.customer.verification_step == "passed"
                        and state.customer.pending_query):
                    pending = state.customer.pending_query
                    state.customer.pending_query = ""
                    biz_response = await self.handle_turn(session_id, pending)
                    verify_resp.answer = (
                        verify_resp.answer + "\n\n" + biz_response.answer
                    )
                    verify_resp.matched_skill_id = biz_response.matched_skill_id
                    verify_resp.matched_skill_name = biz_response.matched_skill_name
                    verify_resp.confidence = biz_response.confidence
                    verify_resp.route = biz_response.route
                    verify_resp.next_step_hint = biz_response.next_step_hint
                    verify_resp.tools_called = biz_response.tools_called
                    verify_resp.compliance_passed = biz_response.compliance_passed
                    verify_resp.compliance_issues = biz_response.compliance_issues
                    verify_resp.warning = biz_response.warning
                    verify_resp.latency_ms = (time.monotonic() - start) * 1000
                return verify_resp

        # ----------------------------------------------------------
        # Intent stickiness — reuse previous skill's follow_up when
        # the user is clearly issuing a short continuation ("嗯", "那呢").
        # Runs *before* Chain A so acknowledgements stay in-skill.
        # ----------------------------------------------------------
        if self.settings.ENABLE_INTENT_STICKY:
            sticky_resp = await self._maybe_sticky_shortcut(state, query, trace_id)
            if sticky_resp is not None:
                self._finalize(
                    state, query, sticky_resp, trace_id, start,
                    skill_id=state.intent.current_skill_id,
                    domain=state.intent.domain,
                    was_sticky=True,
                )
                return sticky_resp

        # ----------------------------------------------------------
        # Chain A: Rule short-circuit
        # ----------------------------------------------------------
        rule_match = self.rule_engine.match(query, state)
        if rule_match is not None:
            skill = rule_match.skill
            requires_identity = self._skill_requires_identity(skill, query)

            # If the skill will touch account-level data and user not verified
            # → start verification.
            if requires_identity and not state.customer.verified:
                verify_resp = self._start_verification(
                    state, query, trace_id,
                    pending_route=self._build_pending_route_a(query, rule_match),
                )
                if verify_resp is not None:
                    self._finalize(state, query, verify_resp, trace_id, start)
                    return verify_resp

            # For direct_reply skills without tools: use follow_up (business answer)
            # instead of first_contact (greeting/intro) when not in multi-turn
            if not requires_identity and skill and rule_match.template_variant == "first_contact":
                if "follow_up" in skill.templates:
                    rule_match.template_variant = "follow_up"
            if not requires_identity and not state.customer.verified:
                rule_match.tools_needed = []

            # If verified and skill has follow_up template, prefer it over first_contact
            # because first_contact is the verification greeting
            if state.customer.verified and skill and rule_match.template_variant == "first_contact":
                if "follow_up" in skill.templates:
                    rule_match.template_variant = "follow_up"

            response = await self._execute_route_a(state, query, rule_match, trace_id)
            self._finalize(state, query, response, trace_id, start,
                           skill_id=rule_match.skill_id, domain=skill.domain if skill else None)
            return response

        # ----------------------------------------------------------
        # Chain B: LLM Skill Routing
        # ----------------------------------------------------------
        window_text = self.ctx.window.format_for_prompt(state)
        summary = state.summary

        skill_match, domain = await self._route_chain_b(
            query, state, window_text, summary,
        )

        # ----------------------------------------------------------
        # Escalation override: if the previous skill has escalation
        # branches and the user's query contains escalation keywords,
        # keep routing to the same skill so the branch evaluator can
        # select the appropriate escalation variant.
        # ----------------------------------------------------------
        _ESCALATION_KEYWORDS = ("投诉", "领导", "上级", "经理", "不接受", "不行")
        prior_skill_id = state.intent.current_skill_id
        if (
            prior_skill_id
            and prior_skill_id != skill_match.skill_id
            and any(kw in query for kw in _ESCALATION_KEYWORDS)
        ):
            prior_skill = self.skill_loader.get_skill(prior_skill_id)
            if prior_skill and prior_skill.escalation:
                logger.info(
                    "Escalation override: %s -> %s (query contains escalation keywords)",
                    skill_match.skill_id, prior_skill_id,
                )
                skill_match.skill_id = prior_skill_id
                skill_match.confidence = max(skill_match.confidence, 0.85)

        # ----------------------------------------------------------
        # Intercept flow-control skill routes when verification is the
        # actual intent. If LLM picked identity_readback and the user is
        # still not verified, bypass Chain B generation and hand off to
        # the deterministic verification state machine.
        # ----------------------------------------------------------
        if (
            skill_match.skill_id in ("identity_readback", "acknowledgement")
            and not state.customer.verified
        ):
            verify_resp = self._start_verification(state, query, trace_id)
            if verify_resp is not None:
                # Record intent as None so this turn doesn't poison future routing
                self._finalize(state, query, verify_resp, trace_id, start)
                return verify_resp

        # Even when verified, acknowledgement must not hijack intent. If we
        # already have a prior business skill, respond with a friendly probe
        # instead of running the acknowledgement template.
        if (
            skill_match.skill_id == "acknowledgement"
            and state.customer.verified
        ):
            prev_skill_id = state.intent.current_skill_id
            if prev_skill_id and prev_skill_id not in self._STICKY_BLACKLIST_SKILLS:
                prev_skill = self.skill_loader.get_skill(prev_skill_id)
                probe = self._build_closing_reply(
                    state, trace_id,
                    skill_id=prev_skill_id,
                    skill_name=prev_skill.name if prev_skill else prev_skill_id,
                )
            else:
                probe = CopilotResponse(
                    output_type="bot_reply",
                    answer=(
                        f"{state.customer.name_masked or '您'}，请问您是想咨询账单、还款、"
                        "贷款还是其他业务？我来为您处理。"
                    ),
                    next_step_hint="等待客户补充业务意图",
                    route="route_a",
                    confidence=0.8,
                    trace_id=trace_id,
                    compliance_passed=True,
                    compliance_issues=[],
                    tools_called=[],
                )
            self._finalize(state, query, probe, trace_id, start)
            return probe

        # Fallback if no match or very low confidence.
        # T1-E (revised): lower floor further from 0.15 to 0.12; relax alt
        # promotion from 0.25 to 0.18 because Exp2 T1 showed alternatives[0]
        # confidence typically falls in 0.1~0.2 when multi-domain-k=3.
        if skill_match.skill_id == "none" or skill_match.confidence < 0.12:
            promoted = None
            for alt in skill_match.alternatives or []:
                alt_sid = alt.get("skill_id")
                alt_conf = float(alt.get("confidence", 0.0) or 0.0)
                if alt_sid and alt_sid != "none" and alt_conf >= 0.18:
                    promoted = alt
                    break
            if promoted is not None:
                skill_match.skill_id = promoted["skill_id"]
                skill_match.confidence = min(float(promoted.get("confidence", 0.0) or 0.0), 0.5)
                skill_match.reasoning = (
                    f"[T1-E promoted from alt:{promoted.get('skill_id')}] " + skill_match.reasoning
                )
            else:
                response = await self._execute_route_c(state, query, trace_id)
                self._finalize(state, query, response, trace_id, start)
                return response

        skill = self.skill_loader.get_skill(skill_match.skill_id)
        if skill is None:
            response = await self._execute_route_c(state, query, trace_id)
            self._finalize(state, query, response, trace_id, start)
            return response

        value_added_context = self._retrieve_value_added_knowledge(skill, query)
        skip_identity_for_unmatched_value_added = (
            value_added_context.get("slots", {}).get("value_added_match_status")
            == "unmatched"
        )

        # Route B may select first_contact because the skill definition keeps
        # identity verification as the first step. Once the deterministic
        # verification gate has already passed, use the business follow-up
        # template so Agent A can Jinja2-fill tool-backed answers directly
        # instead of asking the LLM to rewrite a stale verification prompt.
        if (
            state.customer.verified
            and skill_match.template_variant == "first_contact"
            and "follow_up" in skill.templates
        ):
            skill_match.template_variant = "follow_up"

        # Route B should verify only after a concrete tool-backed skill is chosen.
        # Otherwise the user can be dragged into identity verification before we
        # even know whether the utterance is a generic long-tail question or a
        # deterministic account query.
        if (
            self._skill_requires_identity(skill, query)
            and not state.customer.verified
            and state.customer.verification_step == "not_started"
            and not skip_identity_for_unmatched_value_added
        ):
            verify_resp = self._start_verification(
                state, query, trace_id,
                pending_route=self._build_pending_route_b(query, skill_match, domain),
            )
            if verify_resp is not None:
                self._finalize(state, query, verify_resp, trace_id, start)
                return verify_resp

        route_b_exec = await self._execute_route_b_from_match(
            state, query, skill_match, domain, trace_id,
        )
        self._finalize(
            state, query, route_b_exec.response, trace_id, start,
            skill_id=route_b_exec.skill_id,
            domain=route_b_exec.domain,
            new_slots=route_b_exec.new_slots,
            tools_called=route_b_exec.tools_called,
        )
        return route_b_exec.response

    async def _route_chain_b(
        self,
        query: str,
        state: ConversationState,
        window_text: str,
        summary: str,
    ) -> tuple[SkillMatch, str]:
        """Route Chain B with hybrid recall when available, else old single-domain path."""
        if self.settings.ENABLE_HYBRID_SKILL_RECALL:
            try:
                return await self._route_chain_b_hybrid(query, state, window_text, summary)
            except Exception as exc:
                logger.warning(
                    "hybrid Chain B routing failed; falling back to single-domain route: %s",
                    exc,
                )

        domain = self.keyword_domain_clf.classify(query, state)
        match = await self.skill_router.route(
            query, domain, state, window_text, summary,
        )
        return match, domain

    async def _route_chain_b_hybrid(
        self,
        query: str,
        state: ConversationState,
        window_text: str,
        summary: str,
    ) -> tuple[SkillMatch, str]:
        """Build domain Top-K + skill-cos candidates, then let SkillRouter rank."""
        domain_k = max(1, int(self.settings.SKILL_MULTI_DOMAIN_K))
        q_vec: list[float] | None = None

        if not hasattr(self.domain_clf, "classify_topk"):
            raise RuntimeError("domain classifier does not support top-k routing")

        if hasattr(self.domain_clf, "embed_query") and hasattr(self.domain_clf, "classify_topk_from_vector"):
            q_vec = self.domain_clf.embed_query(query)
            domain_pairs = self.domain_clf.classify_topk_from_vector(
                q_vec, state, k=domain_k,
            )
        else:
            domain_pairs = self.domain_clf.classify_topk(query, state, k=domain_k)

        domains = [domain for domain, _ in domain_pairs]
        if not domains:
            domains = [self.keyword_domain_clf.classify(query, state)]

        skill_cos_pairs: list[tuple[str, float]] = []
        skill_cos_top_m = max(0, int(self.settings.SKILL_COS_TOP_M))
        if self.skill_embedding_index is not None and q_vec is not None and skill_cos_top_m > 0:
            skill_cos_pairs = self.skill_embedding_index.rank_vector(
                q_vec, k=skill_cos_top_m,
            )

        candidates, candidate_priors = self._build_chain_b_candidates(
            query=query,
            domain_pairs=domain_pairs,
            skill_cos_pairs=skill_cos_pairs,
        )
        match = await self.skill_router.route_over_candidates(
            query, candidates, state, window_text, summary,
            candidate_priors=candidate_priors,
        )
        return match, domains[0]

    def _build_chain_b_candidates(
        self,
        *,
        query: str,
        domain_pairs: list[tuple[str, float]],
        skill_cos_pairs: list[tuple[str, float]],
    ) -> tuple[list, dict[str, dict[str, Any]]]:
        """Merge domain and skill-cos recall into a sorted, capped candidate set."""
        domain_scores = dict(domain_pairs)
        skill_scores = dict(skill_cos_pairs)

        domain_candidate_ids: list[str] = []
        for domain, _ in domain_pairs:
            for skill in self.skill_loader.get_skills_by_domain(domain):
                if skill.skill_id not in domain_candidate_ids:
                    domain_candidate_ids.append(skill.skill_id)

        skill_cos_candidate_ids = [skill_id for skill_id, _ in skill_cos_pairs]
        candidate_source = self.settings.SKILL_CANDIDATE_SOURCE
        if candidate_source == "domain":
            candidate_ids = list(domain_candidate_ids)
        elif candidate_source == "skill":
            candidate_ids = list(skill_cos_candidate_ids)
        else:
            candidate_ids = list(domain_candidate_ids)
            for skill_id in skill_cos_candidate_ids:
                if skill_id not in candidate_ids:
                    candidate_ids.append(skill_id)

        candidate_priors: dict[str, dict[str, Any]] = {}
        candidates = []
        for skill_id in candidate_ids:
            skill = self.skill_loader.get_skill(skill_id)
            if skill is None:
                continue
            domain_cos = domain_scores.get(skill.domain)
            skill_cos = skill_scores.get(skill_id)
            keyword_overlap = self._skill_keyword_overlap(query, skill)
            prior_score = (
                self.settings.PRIOR_SKILL_WEIGHT * (skill_cos or 0.0)
                + self.settings.PRIOR_DOMAIN_WEIGHT * (domain_cos or 0.0)
                + self.settings.PRIOR_KEYWORD_WEIGHT * keyword_overlap
            )
            source_bits: list[str] = []
            if skill_id in domain_candidate_ids:
                source_bits.append("domain")
            if skill_id in skill_cos_candidate_ids:
                source_bits.append("skill_cos")
            candidate_priors[skill_id] = {
                "domain_cos": domain_cos,
                "skill_cos": skill_cos,
                "keyword_overlap": keyword_overlap,
                "prior_score": prior_score,
                "source": "+".join(source_bits) or "unknown",
            }
            candidates.append(skill)

        candidates.sort(
            key=lambda skill: (
                -candidate_priors.get(skill.skill_id, {}).get("prior_score", 0.0),
                -candidate_priors.get(skill.skill_id, {}).get("skill_cos", 0.0)
                if candidate_priors.get(skill.skill_id, {}).get("skill_cos") is not None else 0.0,
                -skill.priority,
            )
        )

        max_candidates = max(0, int(self.settings.SKILL_MAX_CANDIDATES))
        if max_candidates > 0:
            candidates = candidates[:max_candidates]
            kept = {skill.skill_id for skill in candidates}
            candidate_priors = {
                skill_id: prior
                for skill_id, prior in candidate_priors.items()
                if skill_id in kept
            }
        return candidates, candidate_priors

    @staticmethod
    def _skill_keyword_overlap(query: str, skill) -> float:
        keywords = skill.triggers.keywords or []
        if not query or not keywords:
            return 0.0
        hits = sum(1 for kw in keywords if kw and kw in query)
        return min(1.0, hits / 3.0)

    def _retrieve_value_added_knowledge(
        self,
        skill: Any | None,
        query: str,
    ) -> dict[str, Any]:
        """Retrieve structured 活动/增值服务 SOP context for the current turn."""
        if self.value_added_knowledge is None or skill is None:
            return {}
        try:
            result = self.value_added_knowledge.retrieve(query, skill.skill_id)
            return result or {}
        except Exception as exc:
            logger.warning(
                "value-added knowledge retrieval failed for skill=%s: %s",
                getattr(skill, "skill_id", None),
                exc,
            )
            return {}

    # ------------------------------------------------------------------
    # Intent write-through filter — keeps flow-control skills from
    # stomping the user's actual business intent.
    # ------------------------------------------------------------------

    def _intent_skill_for(
        self,
        state: ConversationState,
        new_skill_id: str,
        new_domain: str | None,
    ) -> str | None:
        """Decide whether this turn's skill should be recorded as the active intent.

        Returns ``None`` when the new skill is a flow-control placeholder and
        the session already has a real business intent — preserving context
        for sticky continuations in later turns.
        """
        if not new_skill_id or new_skill_id == "none":
            return new_skill_id
        is_flow = (
            new_skill_id in self._STICKY_BLACKLIST_SKILLS
            or new_domain in self._STICKY_BLACKLIST_DOMAINS
        )
        if is_flow and state.intent.current_skill_id and \
                state.intent.current_skill_id not in self._STICKY_BLACKLIST_SKILLS:
            return None  # don't overwrite a real business intent
        return new_skill_id

    def _intent_domain_for(
        self,
        state: ConversationState,
        new_domain: str | None,
    ) -> str | None:
        """Mirror the skill filter on the domain axis."""
        if new_domain in self._STICKY_BLACKLIST_DOMAINS \
                and state.intent.domain \
                and state.intent.domain not in self._STICKY_BLACKLIST_DOMAINS:
            return None
        return new_domain

    # ==================================================================
    # Route A
    # ==================================================================

    async def _execute_route_a(
        self,
        state: ConversationState,
        query: str,
        rule_match: RuleMatchResult,
        trace_id: str,
    ) -> CopilotResponse:
        skill = rule_match.skill
        tools_needed = rule_match.tools_needed
        tool_results, tools_called = await self._execute_tools(state, tools_needed)
        value_added_context = self._retrieve_value_added_knowledge(skill, query)

        # Jinja2 direct fill (zero LLM)
        gen_result = await self.generator.generate(
            skill, rule_match.template_variant, tool_results,
            state, "", "",
            supplemental_context=value_added_context.get("prompt_text", ""),
        )

        comp = self.compliance.check(
            gen_result.get("answer", ""),
            state,
            skill=skill,
        )

        return CopilotResponse(
            output_type="bot_reply",
            answer=comp.corrected_answer,
            next_step_hint=gen_result.get("next_step_hint", ""),
            route="route_a",
            matched_skill_id=rule_match.skill_id,
            matched_skill_name=skill.name if skill else "",
            confidence=1.0,
            trace_id=trace_id,
            compliance_passed=comp.passed,
            compliance_issues=comp.issues,
            tools_called=tools_called,
            rag_references=value_added_context.get("references", []),
            knowledge_matches=value_added_context.get("knowledge_matches", []),
        )

    # ==================================================================
    # Route C (fallback)
    # ==================================================================

    async def _execute_route_c(
        self,
        state: ConversationState,
        query: str,
        trace_id: str,
    ) -> CopilotResponse:
        # Determine which tools the longtail reasoner suggests
        suggested_tools = self.longtail._suggest_tools(query)

        # Long-tail queries can still ask for personal account data. If the
        # reasoner would need read tools, verify before exposing tool-backed
        # account facts.
        if (
            suggested_tools
            and not state.customer.verified
            and state.customer.verification_step == "not_started"
        ):
            verify_resp = self._start_verification(
                state, query, trace_id,
                pending_route=self._build_pending_route_c(query, suggested_tools),
            )
            if verify_resp is not None:
                return verify_resp

        # Execute suggested tools if user is verified
        tool_results: dict = {}
        tools_called: list[str] = []
        if suggested_tools and state.customer.verified:
            tool_results, tools_called = await self._execute_tools(state, suggested_tools)

        # Run LLM-based reasoning with tool data
        window_text = self.ctx.window.format_for_prompt(state)
        result = await self.longtail.reason(
            query,
            state=state,
            tool_results=tool_results,
            sliding_window_text=window_text,
            summary=state.summary,
        )

        # Post-compliance (strict mode)
        comp = self.compliance.check(
            result.get("answer", ""),
            state,
            is_longtail=True,
        )

        return CopilotResponse(
            output_type="fallback",
            answer=comp.corrected_answer,
            next_step_hint=result.get("next_step_hint", ""),
            route="route_c_fallback",
            confidence=0.0,
            trace_id=trace_id,
            compliance_passed=comp.passed,
            compliance_issues=comp.issues,
            warning=result.get("warning", "⚠️ 该回答无SOP覆盖，请坐席核实后使用"),
            tools_called=tools_called,
        )

    # ==================================================================
    # Helpers
    # ==================================================================

    async def _execute_tools(
        self,
        state: ConversationState,
        tool_names: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        """Execute tools and update state cache. Returns (results_dict, called_list)."""
        if not tool_names:
            return {}, []

        tool_state = state.to_tool_state()
        # Convert ToolCacheEntry to executor-compatible format
        cache_dict: dict[str, Any] = {}
        for name, entry in state.tool_cache.items():
            cache_dict[name] = {"value": entry.data, "ts": entry.ts}

        exec_result = await execute_tools(
            tool_names, tool_state,
            tool_cache=cache_dict,
        )

        tool_results = exec_result.get("tool_results", {})

        # Check for tool execution failures
        if exec_result.get("execution_status") == "failure":
            state.slots["_tools_failed"] = True
            for failed_tool in exec_result.get("failed_tools", []):
                logger.warning("Tool execution failed: %s", failed_tool)

        # Update state tool cache
        for name, result in tool_results.items():
            if result is not None:
                self.ctx.state_mgr.update_tool_cache(state, name, result)
                # Also merge tool data into slots for template filling
                if isinstance(result, dict):
                    self.ctx.state_mgr.update_slots(state, result)

        return tool_results, tool_names

    @staticmethod
    def _skill_requires_identity(skill: Any | None, query: str = "") -> bool:
        """Return whether a skill touches personal account data.

        Low-risk product introductions can be answered without account lookup,
        even if their skill definitions keep tools around for personalized
        follow-up. Query wording decides whether the user is asking for a
        personal account lookup.
        """
        if not skill or not skill.get_required_tools():
            return False

        if skill.risk_level == "low" and not Orchestrator._query_requests_account_lookup(query):
            return False

        return True

    @staticmethod
    def _query_requests_account_lookup(query: str) -> bool:
        """Heuristic for whether the utterance asks to inspect personal data."""
        lookup_keywords = [
            "我的", "我有", "我有没有", "帮我查", "查一下", "查查", "查询",
            "状态", "进度", "记录", "明细", "结果", "到账", "成功了吗",
            "账单", "订单", "扣款", "还款结果", "还款状态", "欠款", "逾期",
            "额度", "可用额度", "退款", "退费", "合同", "放款进度",
            "身份证", "手机号", "银行卡", "开通了吗", "有没有开通", "是否开通",
            "刚才谁给我打电话", "谁给我打电话", "短信",
        ]
        return any(keyword in query for keyword in lookup_keywords)

    # ==================================================================
    # Pending verified route — cache the route decision while verification runs
    # ==================================================================

    @staticmethod
    def _build_pending_route_a(query: str, rule_match: RuleMatchResult) -> dict[str, Any]:
        return {
            "kind": "route_a",
            "query": query,
            "rule_id": rule_match.rule_id,
            "skill_id": rule_match.skill_id,
            "template_variant": rule_match.template_variant,
            "tools_needed": list(rule_match.tools_needed or []),
            "confidence": rule_match.confidence,
        }

    @staticmethod
    def _build_pending_route_b(
        query: str,
        skill_match: SkillMatch,
        domain: str,
    ) -> dict[str, Any]:
        return {
            "kind": "route_b",
            "query": query,
            "domain": domain,
            "skill_match": skill_match.model_dump(),
        }

    @staticmethod
    def _build_pending_route_c(query: str, suggested_tools: list[str]) -> dict[str, Any]:
        return {
            "kind": "route_c",
            "query": query,
            "suggested_tools": list(suggested_tools or []),
        }

    async def _consume_pending_route(
        self,
        state: ConversationState,
        trace_id: str,
    ) -> _PendingExecution | None:
        """Execute the cached business route after verification passes.

        This intentionally skips Chain B routing. It either reuses the exact
        Rule A hit / SkillMatch selected before verification, or resumes the
        long-tail answer path with the tools previously suggested by Route C.
        """
        cust = state.customer
        pending = dict(cust.pending_route or {})
        if not pending:
            return None

        cust.pending_route = {}
        query = str(pending.get("query") or cust.pending_query or "").strip()
        cust.pending_query = ""

        try:
            kind = pending.get("kind")
            if kind == "route_a":
                return await self._execute_pending_route_a(state, query, pending, trace_id)
            if kind == "route_b":
                match_payload = pending.get("skill_match") or {}
                skill_match = SkillMatch(**match_payload)
                return await self._execute_route_b_from_match(
                    state, query, skill_match, str(pending.get("domain") or ""), trace_id,
                )
            if kind == "route_c":
                response = await self._execute_route_c(state, query, trace_id)
                return _PendingExecution(response=response, tools_called=response.tools_called)
        except Exception as exc:
            logger.error("pending verified route execution failed: %s", exc, exc_info=True)
            return _PendingExecution(
                response=self._build_fallback(state, trace_id, "route_pending"),
            )

        logger.warning("unknown pending route kind: %s", pending.get("kind"))
        return _PendingExecution(
            response=self._build_fallback(state, trace_id, "route_pending"),
        )

    async def _execute_pending_route_a(
        self,
        state: ConversationState,
        query: str,
        pending: dict[str, Any],
        trace_id: str,
    ) -> _PendingExecution:
        skill_id = str(pending.get("skill_id") or "")
        skill = self.skill_loader.get_skill(skill_id)
        if skill is None:
            response = await self._execute_route_c(state, query, trace_id)
            return _PendingExecution(response=response, tools_called=response.tools_called)

        variant = str(pending.get("template_variant") or "first_contact")
        if state.customer.verified and variant == "first_contact" and "follow_up" in skill.templates:
            variant = "follow_up"

        rule_match = RuleMatchResult(
            rule_id=str(pending.get("rule_id") or ""),
            skill_id=skill_id,
            skill=skill,
            template_variant=variant,
            tools_needed=list(pending.get("tools_needed") or skill.get_required_tools()),
            confidence=float(pending.get("confidence", 1.0) or 1.0),
        )
        response = await self._execute_route_a(state, query, rule_match, trace_id)
        return _PendingExecution(
            response=response,
            skill_id=rule_match.skill_id,
            domain=skill.domain,
            tools_called=response.tools_called,
        )

    async def _execute_route_b_from_match(
        self,
        state: ConversationState,
        query: str,
        skill_match: SkillMatch,
        domain: str,
        trace_id: str,
    ) -> _PendingExecution:
        """Execute Route B from an already selected SkillMatch."""
        skill = self.skill_loader.get_skill(skill_match.skill_id)
        if skill is None:
            response = await self._execute_route_c(state, query, trace_id)
            return _PendingExecution(response=response, tools_called=response.tools_called)

        value_added_context = self._retrieve_value_added_knowledge(skill, query)
        skip_identity_for_unmatched_value_added = (
            value_added_context.get("slots", {}).get("value_added_match_status")
            == "unmatched"
        )

        if (
            state.customer.verified
            and skill_match.template_variant == "first_contact"
            and "follow_up" in skill.templates
        ):
            skill_match.template_variant = "follow_up"

        try:
            if skill_match.extracted_slots:
                self.ctx.state_mgr.update_slots(state, skill_match.extracted_slots)

            if skip_identity_for_unmatched_value_added:
                tools_needed = []
            elif not state.customer.verified and not self._skill_requires_identity(skill, query):
                tools_needed = []
            else:
                tools_needed = skill_match.tools_needed or skill.get_required_tools()
            tool_results, tools_called = await self._execute_tools(state, tools_needed)

            audit_domain = skill.domain or domain
            if skip_identity_for_unmatched_value_added:
                audit = ConfidenceAuditResult(
                    score=max(skill_match.confidence, 0.5),
                    passed=True,
                    reasons=["value_added_unmatched_clarification"],
                )
            else:
                audit = self.auditor.audit(
                    skill_match, skill, state, audit_domain, tool_results, query,
                )

            if not audit.passed:
                logger.info(
                    "Audit failed (score=%.2f, reasons=%s), falling through to Chain C",
                    audit.score, audit.reasons,
                )
                response = await self._execute_route_c(state, query, trace_id)
                return _PendingExecution(response=response, tools_called=response.tools_called)

            merged_slots = dict(state.slots)
            for tool_name, result in (tool_results or {}).items():
                if isinstance(result, dict):
                    merged_slots.update(result)
            merged_slots.update(value_added_context.get("slots", {}))
            matched_variant, hint_branches = select_branch_variant(
                skill.branch_conditions, merged_slots,
            )
            effective_variant = skill_match.template_variant
            if matched_variant and matched_variant in skill.templates:
                effective_variant = matched_variant

            recent_text = self.ctx.window.format_for_prompt(state, n_turns=3)
            gen_result = await self.generator.generate(
                skill, effective_variant, tool_results,
                state, recent_text, state.summary,
                branch_hints=hint_branches,
                supplemental_context=value_added_context.get("prompt_text", ""),
            )

            comp = self.compliance.check(
                gen_result.get("answer", ""),
                state,
                skill=skill,
            )

            if comp.need_handoff:
                response = CopilotResponse(
                    output_type="handoff",
                    answer="您的问题需要人工专员处理，正在为您转接，请稍候。",
                    route="route_b",
                    matched_skill_id=skill_match.skill_id,
                    matched_skill_name=skill.name,
                    confidence=skill_match.confidence,
                    trace_id=trace_id,
                    compliance_passed=False,
                    compliance_issues=comp.issues,
                    tools_called=tools_called,
                    rag_references=value_added_context.get("references", []),
                    knowledge_matches=value_added_context.get("knowledge_matches", []),
                )
            else:
                response = CopilotResponse(
                    output_type="bot_reply",
                    answer=comp.corrected_answer,
                    next_step_hint=gen_result.get("next_step_hint", ""),
                    route="route_b",
                    matched_skill_id=skill_match.skill_id,
                    matched_skill_name=skill.name,
                    confidence=skill_match.confidence,
                    trace_id=trace_id,
                    compliance_passed=comp.passed,
                    compliance_issues=comp.issues,
                    tools_called=tools_called,
                    rag_references=value_added_context.get("references", []),
                    knowledge_matches=value_added_context.get("knowledge_matches", []),
                )

            if (
                response.output_type == "bot_reply"
                and self.settings.ENABLE_INTENT_STICKY
                and not self.ctx.has_slot_progress(
                    state, tool_results=tool_results, tools_called=tools_called,
                )
            ):
                ratio = self.ctx.duplicate_ratio(response.answer, state.last_agent_reply)
                if ratio >= self.ctx.dialogue.duplicate_threshold:
                    response = self._build_closing_reply(
                        state, trace_id,
                        skill_id=skill_match.skill_id,
                        skill_name=skill.name,
                    )

            return _PendingExecution(
                response=response,
                skill_id=self._intent_skill_for(state, skill_match.skill_id, audit_domain),
                domain=self._intent_domain_for(state, audit_domain),
                new_slots=skill_match.extracted_slots,
                tools_called=tools_called,
            )
        except Exception as exc:
            logger.error("Cached Chain B execution failed: %s", exc, exc_info=True)
            return _PendingExecution(
                response=self._build_fallback(
                    state, trace_id, "route_b", skill_id=skill_match.skill_id,
                )
            )

    @staticmethod
    def _merge_verified_business_response(
        state: ConversationState,
        response: CopilotResponse,
    ) -> CopilotResponse:
        prefix = f"{state.customer.name_masked or '您'}，身份核实通过。"
        answer = (response.answer or "").strip()
        if answer and not answer.startswith(prefix):
            response.answer = f"{prefix}\n\n{answer}"
        elif not answer:
            response.answer = prefix
        return response

    # ==================================================================
    # Identity Verification (核身)
    # ==================================================================

    def _start_verification(
        self,
        state: ConversationState,
        query: str,
        trace_id: str,
        pending_skill: str | None = None,
        pending_route: dict[str, Any] | None = None,
    ) -> CopilotResponse | None:
        """Initiate identity verification flow. Save original query for later."""
        cust = state.customer

        if cust.verification_step == "not_started":
            cust.pending_query = query  # remember the business question
            cust.pending_route = pending_route or {}
            cust.verification_step = "asking_name"
            return CopilotResponse(
                output_type="followup",
                answer="为了保障您的账户安全，需要先核实一下您的身份。请问您的姓名是？",
                next_step_hint="等待客户提供姓名",
                route="route_a",
                confidence=1.0,
                trace_id=trace_id,
            )
        return None

    def _handle_verification(
        self,
        state: ConversationState,
        query: str,
        trace_id: str,
    ) -> CopilotResponse | None:
        """Process ongoing verification steps with immediate per-step validation."""
        import re
        cust = state.customer
        step = cust.verification_step
        q = query.strip()

        if step == "failed":
            if q in ("重新验证", "重新核身", "重试", "再试一次"):
                cust.verification_step = "asking_name"
                cust.verification_attempts = 0
                cust.collected_name = ""
                cust.collected_phone = ""
                cust.collected_id_last4 = ""
                cust.candidate_customer_ids = []
                return CopilotResponse(
                    output_type="followup",
                    answer="好的，我们重新开始身份核实。请问您的姓名是？",
                    next_step_hint="等待客户提供姓名",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )
            return CopilotResponse(
                output_type="handoff",
                answer="身份核实未通过，为保障您的账户安全，建议由人工专员继续处理。如需重试，请输入「重新验证」。",
                route="route_a", confidence=1.0, trace_id=trace_id,
            )

        one_shot_cid = self._match_verification_payload(q)
        if one_shot_cid:
            return self._verification_passed(state, one_shot_cid, trace_id)

        # --- Handle navigation commands ---
        if q in ("上一步", "返回上一步", "回退"):
            if step == "asking_phone":
                cust.verification_step = "asking_name"
                cust.collected_name = ""
                cust.candidate_customer_ids = []
                return CopilotResponse(
                    output_type="followup",
                    answer="好的，请重新输入您的姓名。",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )
            if step == "asking_id":
                cust.verification_step = "asking_phone"
                cust.collected_phone = ""
                return CopilotResponse(
                    output_type="followup",
                    answer="好的，请重新输入您的手机号码。",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

        if q in ("跳过核身", "跳过验证", "跳过", "不验证了"):
            cust.verification_step = "not_started"
            cust.collected_name = ""
            cust.collected_phone = ""
            cust.collected_id_last4 = ""
            cust.candidate_customer_ids = []
            cust.pending_query = ""
            cust.pending_route = {}
            return CopilotResponse(
                output_type="followup",
                answer="好的，已跳过身份核实。未核身状态下仅能咨询通用问题，涉及账户信息的查询需要先完成核身。请问有什么可以帮您的？",
                route="route_a", confidence=1.0, trace_id=trace_id,
            )

        if step == "asking_name":
            name = query.strip().rstrip("。.，,")
            for prefix in ["我叫", "我是", "我的名字是", "姓名是", "名字是", "我姓"]:
                if name.startswith(prefix):
                    name = name[len(prefix):].strip()
                    break
            if len(name) < 2 or len(name) > 6:
                return CopilotResponse(
                    output_type="followup",
                    answer="抱歉没有听清，请问您的姓名是？",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

            # Immediately match name against demo verification data
            candidates = []
            for cid, vdata in get_verification_db().items():
                if (name == vdata["real_name"]
                        or name in vdata["real_name"]
                        or vdata["real_name"] in name):
                    candidates.append(cid)

            if not candidates:
                cust.verification_attempts += 1
                if cust.verification_attempts >= 3:
                    return self._verification_failed(state, trace_id)
                return CopilotResponse(
                    output_type="followup",
                    answer=(
                        f"抱歉，未查询到姓名为'{name}'的客户记录。您可以：\n"
                        "1. 重新输入姓名\n"
                        "2. 输入「跳过核身」咨询不需要核身的问题"
                    ),
                    next_step_hint="等待客户选择",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

            cust.collected_name = name
            cust.candidate_customer_ids = candidates
            cust.verification_step = "asking_phone"
            return CopilotResponse(
                output_type="followup",
                answer=f"好的，{name}。请提供您的手机号码以便核实。",
                next_step_hint="等待客户提供手机号",
                route="route_a", confidence=1.0, trace_id=trace_id,
            )

        if step == "asking_phone":
            phone_match = re.search(r"1[3-9]\d{9}", query)
            if not phone_match:
                return CopilotResponse(
                    output_type="followup",
                    answer="请提供您的11位手机号码。",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

            phone = phone_match.group()
            # Verify phone against remaining candidates
            narrowed = []
            for cid in cust.candidate_customer_ids:
                if get_verification_db()[cid]["phone"] == phone:
                    narrowed.append(cid)

            if not narrowed:
                cust.verification_attempts += 1
                if cust.verification_attempts >= 3:
                    return self._verification_failed(state, trace_id)
                # Stay on asking_phone — let user retry, go back, or exit
                return CopilotResponse(
                    output_type="followup",
                    answer=(
                        "抱歉，该手机号与姓名不匹配。您可以：\n"
                        "1. 重新输入手机号\n"
                        "2. 输入「上一步」重新输入姓名\n"
                        "3. 输入「跳过核身」咨询不需要核身的问题"
                    ),
                    next_step_hint="等待客户选择",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

            cust.collected_phone = phone
            cust.candidate_customer_ids = narrowed
            cust.verification_step = "asking_id"
            return CopilotResponse(
                output_type="followup",
                answer=f"手机号 {phone} 核实通过。最后请提供您身份证号的后四位。",
                next_step_hint="等待客户提供身份证后四位",
                route="route_a", confidence=1.0, trace_id=trace_id,
            )

        if step == "asking_id":
            id_last4 = self._extract_id_last4(query)
            if not id_last4:
                return CopilotResponse(
                    output_type="followup",
                    answer="请提供您身份证号的后四位数字。",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

            # Verify against remaining candidates
            matched_cid = None
            for cid in cust.candidate_customer_ids:
                if get_verification_db()[cid]["id_last4"] == id_last4:
                    matched_cid = cid
                    break

            if not matched_cid:
                cust.verification_attempts += 1
                if cust.verification_attempts >= 3:
                    return self._verification_failed(state, trace_id)
                return CopilotResponse(
                    output_type="followup",
                    answer=(
                        "抱歉，身份证后四位不匹配。您可以：\n"
                        "1. 重新输入身份证后四位\n"
                        "2. 输入「上一步」重新输入手机号\n"
                        "3. 输入「跳过核身」咨询不需要核身的问题"
                    ),
                    next_step_hint="等待客户选择",
                    route="route_a", confidence=1.0, trace_id=trace_id,
                )

            # === Verification passed ===
            return self._verification_passed(state, matched_cid, trace_id)

        return None

    @staticmethod
    def _extract_id_last4(query: str) -> str:
        """Extract ID-card last four digits from a short or full input."""
        import re
        full_id = re.search(r"\d{17}[\dXx]", query)
        if full_id:
            return full_id.group()[-4:].upper()
        explicit = re.search(r"(?:后四位|后4位|身份证).*?(\d{4})", query)
        if explicit:
            return explicit.group(1)
        digits = re.findall(r"\d+", query)
        if len(digits) == 1 and len(digits[0]) == 4:
            return digits[0]
        # Heuristic: if the query contains exactly one 11-digit phone and one
        # other 4-digit number, treat that 4-digit as id_last4.
        phone_matches = [d for d in digits if len(d) == 11 and d.startswith("1")]
        four_digits = [d for d in digits if len(d) == 4]
        if len(phone_matches) == 1 and len(four_digits) == 1:
            return four_digits[0]
        return ""

    @staticmethod
    def _match_verification_payload(query: str) -> str | None:
        """Match a one-shot name + phone + ID-last4 verification utterance."""
        import re
        phone_match = re.search(r"1[3-9]\d{9}", query)
        id_last4 = Orchestrator._extract_id_last4(query)
        if not phone_match or not id_last4:
            return None

        phone = phone_match.group()
        for cid, vdata in get_verification_db().items():
            if (
                vdata["real_name"] in query
                and vdata["phone"] == phone
                and vdata["id_last4"] == id_last4
            ):
                return cid
        return None

    @staticmethod
    def _strip_identity_payload(query: str, matched_cid: str) -> str:
        """Remove the identity tokens from a query that also carried business intent."""
        import re
        vdata = get_verification_db().get(matched_cid) or {}
        residual = query
        # Strip name, phone, and id4
        name = vdata.get("real_name", "")
        phone = vdata.get("phone", "")
        id4 = vdata.get("id_last4", "")
        if name:
            residual = residual.replace(name, "")
        if phone:
            residual = residual.replace(phone, "")
        if id4:
            residual = residual.replace(id4, "")
        # Strip identity connector words and punctuation
        for token in ("我叫", "我是", "姓名是", "名字是", "我姓",
                      "手机号", "电话", "身份证", "后四位", "后4位"):
            residual = residual.replace(token, "")
        residual = re.sub(r"[，,。.：:；;\s]+", " ", residual).strip()
        # If the remainder is 2+ characters of real text, return it as a business query
        return residual if len(residual) >= 2 else ""

    def _verification_passed(
        self,
        state: ConversationState,
        matched_cid: str,
        trace_id: str,
    ) -> CopilotResponse:
        """Complete verification and set customer context."""
        cust = state.customer
        vdata = get_verification_db()[matched_cid]

        cust.verified = True
        cust.verification_level = "full"
        cust.verification_step = "passed"
        cust.customer_id = matched_cid
        cust.verification_attempts = 0
        cust.candidate_customer_ids = []

        name = vdata["real_name"]
        cust.name_masked = name
        phone = vdata["phone"]
        cust.phone_masked = phone
        cust.id_last4 = vdata["id_last4"]

        self.ctx.state_mgr.update_slots(state, {
            "customer_name": cust.name_masked,
            "phone": cust.phone_masked,
            "phone_masked": cust.phone_masked,
            "id_last4": cust.id_last4,
        })

        # If there's a pending query, tell user we'll answer it right away
        if cust.pending_query:
            return CopilotResponse(
                output_type="followup",
                answer=f"{cust.name_masked}，身份核实通过，正在为您查询，请稍候...",
                route="route_a", confidence=1.0, trace_id=trace_id,
                # Mark as special — orchestrator will re-process pending_query
            )
        return CopilotResponse(
            output_type="followup",
            answer=f"{cust.name_masked}，身份核实通过。请问有什么可以帮您的？",
            route="route_a", confidence=1.0, trace_id=trace_id,
        )

    @staticmethod
    def _verification_failed(state: ConversationState, trace_id: str) -> CopilotResponse:
        """Too many failed attempts — escalate to human agent."""
        state.customer.verification_step = "failed"
        return CopilotResponse(
            output_type="handoff",
            answer="非常抱歉，多次核实未通过，为保障您的账户安全，现在为您转接人工专员处理。",
            route="route_a", confidence=1.0, trace_id=trace_id,
        )

    @staticmethod
    def _extract_verification_info(state: ConversationState, query: str) -> None:
        """Try to pre-extract name/phone/id from query (for one-shot input)."""
        import re
        cust = state.customer
        if not cust.collected_phone:
            phone_m = re.search(r"1[3-9]\d{9}", query)
            if phone_m:
                cust.collected_phone = phone_m.group()
        if not cust.collected_id_last4:
            id_m = re.search(r"(?:后四位|身份证).*?(\d{4})", query)
            if id_m:
                cust.collected_id_last4 = id_m.group(1)

    # ==================================================================
    # Greeting / farewell
    # ==================================================================

    _GREETING_KEYWORDS = [
        "你好", "您好", "喂", "嗨", "hi", "hello", "在吗", "在不在",
    ]
    _FAREWELL_KEYWORDS = [
        "再见", "拜拜", "没事了", "好的谢谢", "好的感谢", "谢谢",
        "感谢", "多谢", "辛苦了", "没有了", "不用了", "就这些", "可以了",
    ]

    def _check_greeting(
        self,
        query: str,
        state: ConversationState,
        trace_id: str,
    ) -> CopilotResponse | None:
        """Handle greetings and farewells without LLM."""
        q = query.strip().rstrip("。！？!?~")
        # Only trigger for short messages (pure greeting, not "你好我想查账单")
        if len(q) > 15:
            return None
        # Avoid eating a greeting that carries a business intent.
        # DOMAIN_KEYWORDS["会话流程"] already contains 你好/您好/嗯/好的/谢谢 etc.,
        # so we scan the *other* domains and bail if any hit.
        for dom, kws in DOMAIN_KEYWORDS.items():
            if dom == "会话流程":
                continue
            if any(kw in q for kw in kws):
                return None

        is_greeting = any(kw in q for kw in self._GREETING_KEYWORDS)
        is_farewell = any(kw in q for kw in self._FAREWELL_KEYWORDS)

        if is_greeting and state.total_turns == 0:
            return CopilotResponse(
                output_type="bot_reply",
                answer="您好，欢迎致电客服中心，请问有什么可以帮您的？",
                route="route_a",
                confidence=1.0,
                trace_id=trace_id,
            )
        if is_farewell:
            return CopilotResponse(
                output_type="bot_reply",
                answer="感谢您的来电，祝您生活愉快，再见！",
                route="route_a",
                confidence=1.0,
                trace_id=trace_id,
            )
        return None

    @staticmethod
    def _preprocess(query: str) -> str:
        """L0 preprocessing: strip and normalize whitespace."""
        return " ".join(query.split()).strip()

    # ==================================================================
    # Sticky shortcut — reuse prior skill's follow_up for continuations
    # ==================================================================

    # Skills that must NEVER inherit via stickiness. These are flow-control
    # / identity plumbing, not business intents.
    _STICKY_BLACKLIST_SKILLS: frozenset[str] = frozenset({
        "identity_readback",
        "acknowledgement",
        "greeting",
        "greeting_opening",
        "farewell",
    })
    # Domains that represent conversation plumbing rather than business.
    _STICKY_BLACKLIST_DOMAINS: frozenset[str] = frozenset({
        "会话流程",
    })

    async def _maybe_sticky_shortcut(
        self,
        state: ConversationState,
        query: str,
        trace_id: str,
    ) -> CopilotResponse | None:
        """Return a follow_up response when short continuations should stay in-skill."""
        if state.slots.get("eval_force_contextual_generation"):
            return None

        prior_skill_id = state.intent.current_skill_id
        if not prior_skill_id:
            return None

        # Flow-control / identity skills must not attract stickiness.
        if prior_skill_id in self._STICKY_BLACKLIST_SKILLS:
            return None
        if state.intent.domain in self._STICKY_BLACKLIST_DOMAINS:
            return None

        # Check if current skill has escalation branches for risk handling
        skill = self.skill_loader.get_skill(prior_skill_id)
        has_escalation = False
        if skill and hasattr(skill, 'escalation') and skill.escalation:
            has_escalation = True

        # Adjust sticky budget based on skill risk level
        original_max = self.ctx.dialogue.max_sticky_turns
        if skill:
            if skill.risk_level == "high":
                self.ctx.dialogue.max_sticky_turns = 5
            elif skill.risk_level == "medium":
                self.ctx.dialogue.max_sticky_turns = 4

        decision = self.ctx.should_stick(
            state,
            query,
            other_domain_keywords=self._other_domain_keywords(state.intent.domain),
            current_skill_has_escalation=has_escalation,
        )
        self.ctx.dialogue.max_sticky_turns = original_max
        if not decision.stick:
            return None
        if skill is None:
            return None

        # Prefer follow_up; gracefully fall back to closing-style reply if missing.
        variant = decision.template_variant
        if variant not in skill.templates:
            if "follow_up" in skill.templates:
                variant = "follow_up"
            else:
                return self._build_closing_reply(
                    state, trace_id, skill_id=prior_skill_id, skill_name=skill.name,
                )

        # Slot progress gate — if nothing changed since last turn, do not
        # re-render the same follow_up. Emit a soft closing / probing line.
        if not self.ctx.has_slot_progress(state):
            return self._build_closing_reply(
                state, trace_id, skill_id=prior_skill_id, skill_name=skill.name,
            )

        # Render follow_up via Jinja2 only (no fresh tool calls, no LLM).
        tpl = skill.get_template(variant)
        if tpl is None:
            return self._build_closing_reply(
                state, trace_id, skill_id=prior_skill_id, skill_name=skill.name,
            )

        data = dict(state.slots)
        for entry in state.tool_cache.values():
            if isinstance(entry.data, dict):
                data.update(entry.data)
        filled, is_complete = try_fill_template(tpl.script, data)
        if not is_complete:
            # Slots not ready — rather than run a full Chain B, just probe.
            return self._build_closing_reply(
                state, trace_id, skill_id=prior_skill_id, skill_name=skill.name,
            )

        answer = filled.strip()
        # Duplicate-reply guard
        ratio = self.ctx.duplicate_ratio(answer, state.last_agent_reply)
        if ratio >= self.ctx.dialogue.duplicate_threshold:
            logger.info(
                "sticky reply deduplicated (ratio=%.2f) — falling back to closing",
                ratio,
            )
            return self._build_closing_reply(
                state, trace_id, skill_id=prior_skill_id, skill_name=skill.name,
            )

        comp = self.compliance.check(answer, state, skill=skill)
        return CopilotResponse(
            output_type="bot_reply",
            answer=comp.corrected_answer,
            next_step_hint=tpl.next_step,
            route="route_a_sticky",
            matched_skill_id=prior_skill_id,
            matched_skill_name=skill.name,
            confidence=0.9,
            trace_id=trace_id,
            compliance_passed=comp.passed,
            compliance_issues=comp.issues,
            tools_called=[],
        )

    def _build_closing_reply(
        self,
        state: ConversationState,
        trace_id: str,
        *,
        skill_id: str,
        skill_name: str,
    ) -> CopilotResponse:
        """Soft probing line used when sticky wants to stay but nothing to say."""
        name = state.customer.name_masked or "您"
        return CopilotResponse(
            output_type="bot_reply",
            answer=f"{name}，关于「{skill_name}」，您还有其他想了解的吗？或者需要我协助处理其他问题？",
            next_step_hint="等待客户补充或切换话题",
            route="route_a_sticky",
            matched_skill_id=skill_id,
            matched_skill_name=skill_name,
            confidence=0.8,
            trace_id=trace_id,
            compliance_passed=True,
            compliance_issues=[],
            tools_called=[],
        )

    @staticmethod
    def _other_domain_keywords(current_domain: str | None) -> list[str]:
        """Flatten DOMAIN_KEYWORDS for all domains OTHER than current."""
        if not current_domain:
            return []
        out: list[str] = []
        for dom, kws in DOMAIN_KEYWORDS.items():
            if dom == current_domain or dom == "会话流程":
                continue
            out.extend(kws)
        return out

    def _build_fallback(
        self,
        state: ConversationState,
        trace_id: str,
        route: str,
        skill_id: Optional[str] = None,
        confidence: float = 0.0,
    ) -> CopilotResponse:
        return CopilotResponse(
            output_type="fallback",
            answer="您的问题我需要进一步了解，请稍候为您转接专员处理。",
            route=route,
            matched_skill_id=skill_id,
            confidence=confidence,
            trace_id=trace_id,
            warning="⚠️ 该回答无SOP覆盖，请坐席核实后使用",
        )

    def _finalize(
        self,
        state: ConversationState,
        query: str,
        response: CopilotResponse,
        trace_id: str,
        start: float,
        *,
        skill_id: Optional[str] = None,
        domain: Optional[str] = None,
        new_slots: Optional[dict[str, Any]] = None,
        tools_called: Optional[list[str]] = None,
        was_sticky: bool = False,
    ) -> None:
        """Post-turn: update context and set latency on the response."""
        response.latency_ms = (time.monotonic() - start) * 1000
        response.trace_id = trace_id

        self.ctx.process_turn_end(
            state, query, response.answer,
            skill_id=skill_id,
            domain=domain,
            new_slots=new_slots,
            tools_called=tools_called,
            was_sticky=was_sticky,
        )
