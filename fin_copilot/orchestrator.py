"""Main orchestrator — dispatches requests through Chain A / B / C."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Optional

from fin_copilot.agents.compliant_generator import CompliantGenerator
from fin_copilot.agents.confidence_auditor import ConfidenceAuditor
from fin_copilot.agents.longtail_reasoner import LongtailReasoner
from fin_copilot.compliance.rule_checker import RuleComplianceChecker
from fin_copilot.context.context_manager import ContextManager
from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.response import CopilotResponse
from fin_copilot.models.skill import SkillMatch
from fin_copilot.routing.domain_classifier import DomainClassifier
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
from tools.mock_data import VERIFICATION_DB  # noqa: E402

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.ctx = context_mgr
        self.rule_engine = rule_engine
        self.domain_clf = domain_classifier
        self.skill_router = skill_router
        self.skill_loader = skill_loader
        self.auditor = confidence_auditor
        self.generator = compliant_generator
        self.compliance = compliance_checker
        self.longtail = longtail_reasoner

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

        # Pre-turn processing (risk flags + slot extraction)
        self.ctx.process_turn_start(state, query)

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
        # Chain A: Rule short-circuit
        # ----------------------------------------------------------
        rule_match = self.rule_engine.match(query, state)
        if rule_match is not None:
            skill = rule_match.skill
            requires_identity = self._skill_requires_identity(skill, query)

            # If the skill will touch account-level data and user not verified
            # → start verification.
            if requires_identity and not state.customer.verified:
                verify_resp = self._start_verification(state, query, trace_id)
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
        domain = self.domain_clf.classify(query, state)
        window_text = self.ctx.window.format_for_prompt(state)
        summary = state.summary

        skill_match = await self.skill_router.route(
            query, domain, state, window_text, summary,
        )

        # Fallback if no match or very low confidence
        if skill_match.skill_id == "none" or skill_match.confidence < 0.3:
            response = await self._execute_route_c(state, query, trace_id)
            self._finalize(state, query, response, trace_id, start)
            return response

        skill = self.skill_loader.get_skill(skill_match.skill_id)
        if skill is None:
            response = await self._execute_route_c(state, query, trace_id)
            self._finalize(state, query, response, trace_id, start)
            return response

        # Route B should verify only after a concrete tool-backed skill is chosen.
        # Otherwise the user can be dragged into identity verification before we
        # even know whether the utterance is a generic long-tail question or a
        # deterministic account query.
        if (
            self._skill_requires_identity(skill, query)
            and not state.customer.verified
            and state.customer.verification_step == "not_started"
        ):
            verify_resp = self._start_verification(state, query, trace_id)
            if verify_resp is not None:
                self._finalize(state, query, verify_resp, trace_id, start)
                return verify_resp

        # Merge extracted slots from routing
        if skill_match.extracted_slots:
            self.ctx.state_mgr.update_slots(state, skill_match.extracted_slots)

        # Tool execution
        if not state.customer.verified and not self._skill_requires_identity(skill, query):
            tools_needed = []
        else:
            tools_needed = skill_match.tools_needed or skill.get_required_tools()
        tool_results, tools_called = await self._execute_tools(state, tools_needed)

        # Agent B: Confidence audit
        audit = self.auditor.audit(
            skill_match, skill, state, domain, tool_results, query,
        )

        if not audit.passed:
            response = self._build_fallback(
                state, trace_id, "route_b",
                skill_id=skill_match.skill_id,
                confidence=audit.score,
            )
            self._finalize(state, query, response, trace_id, start)
            return response

        # Agent A: Compliant generation
        # Branch DSL: evaluate expr against slots and pick a deterministic variant
        # when one matches. Indeterminate/hint-only branches are passed through
        # to the generator as soft hints.
        merged_slots = dict(state.slots)
        for tool_name, result in (tool_results or {}).items():
            if isinstance(result, dict):
                merged_slots.update(result)
        matched_variant, hint_branches = select_branch_variant(
            skill.branch_conditions, merged_slots,
        )
        effective_variant = skill_match.template_variant
        if matched_variant and matched_variant in skill.templates:
            effective_variant = matched_variant

        recent_text = self.ctx.window.format_for_prompt(state, n_turns=3)
        gen_result = await self.generator.generate(
            skill, effective_variant, tool_results,
            state, recent_text, summary,
            branch_hints=hint_branches,
        )

        # Post-compliance check
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
            )

        self._finalize(
            state, query, response, trace_id, start,
            skill_id=skill_match.skill_id, domain=domain,
            new_slots=skill_match.extracted_slots, tools_called=tools_called,
        )
        return response

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

        # Jinja2 direct fill (zero LLM)
        gen_result = await self.generator.generate(
            skill, rule_match.template_variant, tool_results,
            state, "", "",
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
            verify_resp = self._start_verification(state, query, trace_id)
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
    # Identity Verification (核身)
    # ==================================================================

    def _start_verification(
        self,
        state: ConversationState,
        query: str,
        trace_id: str,
        pending_skill: str | None = None,
    ) -> CopilotResponse | None:
        """Initiate identity verification flow. Save original query for later."""
        cust = state.customer

        if cust.verification_step == "not_started":
            cust.pending_query = query  # remember the business question
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
            return CopilotResponse(
                output_type="handoff",
                answer="身份核实未通过，为保障您的账户安全，建议由人工专员继续处理。",
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

            # Immediately match name against VERIFICATION_DB
            candidates = []
            for cid, vdata in VERIFICATION_DB.items():
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
                if VERIFICATION_DB[cid]["phone"] == phone:
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
            masked_phone = phone[:3] + "****" + phone[-4:]
            return CopilotResponse(
                output_type="followup",
                answer=f"手机号 {masked_phone} 核实通过。最后请提供您身份证号的后四位。",
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
                if VERIFICATION_DB[cid]["id_last4"] == id_last4:
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
        explicit = re.search(r"(?:后四位|身份证).*?(\d{4})", query)
        if explicit:
            return explicit.group(1)
        digits = re.findall(r"\d+", query)
        if len(digits) == 1 and len(digits[0]) == 4:
            return digits[0]
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
        for cid, vdata in VERIFICATION_DB.items():
            if (
                vdata["real_name"] in query
                and vdata["phone"] == phone
                and vdata["id_last4"] == id_last4
            ):
                return cid
        return None

    def _verification_passed(
        self,
        state: ConversationState,
        matched_cid: str,
        trace_id: str,
    ) -> CopilotResponse:
        """Complete verification and set customer context."""
        cust = state.customer
        vdata = VERIFICATION_DB[matched_cid]

        cust.verified = True
        cust.verification_level = "full"
        cust.verification_step = "passed"
        cust.customer_id = matched_cid
        cust.verification_attempts = 0
        cust.candidate_customer_ids = []

        name = vdata["real_name"]
        cust.name_masked = name[0] + "*" + name[-1] if len(name) >= 3 else name[0] + "*"
        phone = vdata["phone"]
        cust.phone_masked = phone[:3] + "****" + phone[-4:]
        cust.id_last4 = vdata["id_last4"]

        self.ctx.state_mgr.update_slots(state, {
            "customer_name": cust.name_masked,
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
        "再见", "拜拜", "没事了", "好的谢谢", "谢谢", "没有了",
        "不用了", "就这些", "可以了",
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
        )
