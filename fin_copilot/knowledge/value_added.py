"""Keyword retrieval for activity / value-added service SOP blocks.

The source xlsx assets are intentionally kept as weakly-structured blocks.
This retriever does not infer a unified business schema; it only matches
service aliases, ranks the matching text/image supplement blocks, and formats
the raw structured snippets for the generation prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VALUE_ADDED_SKILL_IDS: frozenset[str] = frozenset({
    "value_added_service_inquiry",
    "cancel_value_added_service",
    "refund_value_added_service",
    "light_card_cancel_refund",
})

SKILL_DEFAULT_SERVICE_ID: dict[str, str] = {
    "light_card_cancel_refund": "light_card",
}

INTENT_HINTS: dict[str, tuple[str, ...]] = {
    "inquiry": ("是什么", "什么", "介绍", "权益", "规则", "内容", "怎么回事", "为什么"),
    "cancel": ("取消", "关闭", "退订", "不要", "不需要", "解除", "停掉"),
    "refund": ("退款", "退费", "退钱", "返还", "退回来", "扣了", "扣款", "莫名扣费"),
    "bill_repayment": ("还款", "账单", "扣款", "支付", "银行卡", "分期", "期数", "到账"),
    "operation_path": ("入口", "路径", "哪里", "怎么操作", "怎么用", "怎么查看", "怎么充", "充值", "页面", "按钮"),
    "contact": ("客服", "电话", "热线", "联系", "人工"),
    "escalation": ("投诉", "升级", "工单", "主管", "反馈"),
}

IMAGE_TYPE_WEIGHTS: dict[str, dict[str, int]] = {
    "inquiry": {
        "policy_rule": 5,
        "agreement_long_text": 5,
        "reward_table": 4,
        "app_ui_path": 3,
    },
    "cancel": {
        "policy_rule": 5,
        "backend_console": 4,
        "payment_status": 3,
        "app_ui_path": 2,
    },
    "refund": {
        "policy_rule": 5,
        "backend_console": 4,
        "payment_status": 4,
        "qr_contact": 3,
    },
    "bill_repayment": {
        "payment_status": 5,
        "policy_rule": 4,
        "backend_console": 3,
        "app_ui_path": 2,
    },
    "operation_path": {
        "app_ui_path": 5,
        "backend_console": 4,
        "qr_contact": 3,
    },
    "contact": {
        "qr_contact": 5,
        "policy_rule": 3,
        "app_ui_path": 2,
    },
}

IMPORTANCE_WEIGHTS = {
    "critical": 5,
    "supplemental": 2,
    "low": 0,
}


class ValueAddedKnowledgeRetriever:
    """Retrieve structured SOP snippets for 活动/增值服务 skills."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        services_path: str = "sop/structured/value_added_text/services.json",
        text_blocks_path: str = "sop/structured/value_added_text/text_blocks.jsonl",
        image_blocks_path: str = "sop/structured/value_added_images/image_blocks.jsonl",
        max_text_blocks: int = 4,
        max_image_blocks: int = 3,
    ) -> None:
        self.root = Path(project_root)
        self.services_path = self.root / services_path
        self.text_blocks_path = self.root / text_blocks_path
        self.image_blocks_path = self.root / image_blocks_path
        self.max_text_blocks = max_text_blocks
        self.max_image_blocks = max_image_blocks
        self._loaded = False
        self._services: list[dict[str, Any]] = []
        self._service_by_id: dict[str, dict[str, Any]] = {}
        self._text_blocks: list[dict[str, Any]] = []
        self._image_blocks: list[dict[str, Any]] = []

    def enabled_for(self, skill_id: str | None, domain: str | None = None) -> bool:
        if not skill_id:
            return False
        return skill_id in VALUE_ADDED_SKILL_IDS or (
            domain == "活动" and skill_id in VALUE_ADDED_SKILL_IDS
        )

    def retrieve(self, query: str, skill_id: str | None = None) -> dict[str, Any] | None:
        """Return prompt context and branch slots for a value-added query."""
        if not self.enabled_for(skill_id):
            return None
        self._ensure_loaded()
        if not self._services:
            return None

        query = query or ""
        intent_tags = self._infer_intents(query)
        matched_services = self._match_services(query)
        if not matched_services and skill_id in SKILL_DEFAULT_SERVICE_ID:
            default_id = SKILL_DEFAULT_SERVICE_ID[skill_id]
            service = self._service_by_id.get(default_id)
            if service:
                matched_services = [{
                    "service_id": default_id,
                    "service_name": service.get("canonical_name") or default_id,
                    "aliases": [],
                    "score": 1,
                }]

        if not matched_services:
            return self._build_unmatched_context(query, skill_id, intent_tags)

        service_ids = {s["service_id"] for s in matched_services}
        text_blocks = [
            b for b in self._text_blocks
            if b.get("service_id") in service_ids
        ]
        image_blocks = [
            b for b in self._image_blocks
            if b.get("service_id") in service_ids
        ]
        text_blocks = sorted(
            text_blocks,
            key=lambda b: self._score_text_block(b, intent_tags, query),
            reverse=True,
        )[:self.max_text_blocks]
        image_blocks = sorted(
            image_blocks,
            key=lambda b: self._score_image_block(b, intent_tags),
            reverse=True,
        )[:self.max_image_blocks]

        service_names = [s["service_name"] for s in matched_services]
        matched_aliases = sorted({
            alias
            for s in matched_services
            for alias in s.get("aliases", [])
        }, key=len, reverse=True)
        prompt_text = self._format_matched_prompt(
            service_names, matched_aliases, text_blocks, image_blocks,
        )
        references = self._references_for(text_blocks, image_blocks)
        return {
            "status": "matched",
            "prompt_text": prompt_text,
            "slots": {
                "value_added_match_status": "matched",
                "value_added_matched_service_id": ",".join(sorted(service_ids)),
                "value_added_matched_service_name": "、".join(service_names),
                "value_added_suspected_non_company_product": False,
            },
            "references": references,
            "knowledge_matches": self._build_knowledge_matches(
                "matched",
                matched_services,
                suspected_non_company_product=False,
            ),
            "matched_services": matched_services,
        }

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.services_path.exists():
            data = json.loads(self.services_path.read_text(encoding="utf-8"))
            self._services = list(data.get("services", []))
            self._service_by_id = {
                str(s.get("service_id")): s for s in self._services
                if s.get("service_id")
            }
        self._text_blocks = self._load_jsonl(self.text_blocks_path)
        self._image_blocks = self._load_jsonl(self.image_blocks_path)

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    @staticmethod
    def _infer_intents(query: str) -> list[str]:
        tags = []
        for tag, keywords in INTENT_HINTS.items():
            if any(keyword in query for keyword in keywords):
                tags.append(tag)
        return tags or ["inquiry"]

    def _match_services(self, query: str) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for service in self._services:
            aliases = [
                str(alias).strip()
                for alias in service.get("aliases", [])
                if str(alias).strip()
            ]
            matched_aliases = [alias for alias in aliases if alias in query]
            if not matched_aliases:
                continue
            # Prefer exact, longer service names over broad words such as 会员.
            score = sum(max(1, len(alias)) for alias in matched_aliases)
            score += 5 * len(matched_aliases)
            canonical = str(service.get("canonical_name") or "")
            if canonical and canonical in query:
                score += 20
            hits.append({
                "service_id": service.get("service_id"),
                "service_name": canonical or service.get("service_id"),
                "aliases": matched_aliases,
                "score": score,
            })
        hits.sort(key=lambda item: (-item["score"], item["service_name"]))
        return hits[:2]

    @staticmethod
    def _score_text_block(
        block: dict[str, Any],
        intent_tags: list[str],
        query: str,
    ) -> tuple[int, int, int]:
        tags = set(block.get("intent_tags") or [])
        overlap = len(tags.intersection(intent_tags))
        title = str(block.get("title") or "")
        text = str(block.get("text") or "")
        haystack = title + "\n" + text
        score = overlap * 10
        if any(marker in query for marker in ("是什么", "什么是", "什么费用", "为什么")):
            if any(marker in haystack for marker in ("什么是", "含义", "活动介绍", "服务作用")):
                score += 35
        if "refund" not in intent_tags and any(marker in title for marker in ("退费", "退款")):
            score -= 25
        if "cancel" not in intent_tags and "取消" in title:
            score -= 15
        if any(marker in title for marker in ("开场白", "验证用户信息", "结束语", "询问用户是否还有", "客服流程图")):
            score -= 30
        query_terms = [
            term for term in (
                "还款无忧", "债务咨询顾问服务费", "话费券", "充值", "有效期",
                "客服电话", "取消", "退费", "退款", "扣款", "账单", "入口",
                "怎么还", "怎么用", "为什么", "是什么",
            )
            if term in query
        ]
        score += sum(6 for term in query_terms if term in haystack)
        text_len = len(block.get("text") or "")
        return score, min(text_len, 2400), -text_len

    @staticmethod
    def _score_image_block(block: dict[str, Any], intent_tags: list[str]) -> tuple[int, int, int]:
        tags = set(block.get("intent_tags") or [])
        overlap = len(tags.intersection(intent_tags))
        image_type = str(block.get("image_type") or "")
        type_score = max(
            IMAGE_TYPE_WEIGHTS.get(tag, {}).get(image_type, 0)
            for tag in intent_tags
        ) if intent_tags else 0
        importance_score = IMPORTANCE_WEIGHTS.get(str(block.get("importance")), 0)
        return overlap * 10 + type_score + importance_score, importance_score, type_score

    def _build_unmatched_context(
        self,
        query: str,
        skill_id: str | None,
        intent_tags: list[str],
    ) -> dict[str, Any]:
        known_names = [
            str(s.get("canonical_name") or s.get("service_id"))
            for s in self._services
            if s.get("canonical_name") or s.get("service_id")
        ]
        known_names_text = "、".join(known_names[:30])
        suspected = self._looks_like_product_query(query)
        if "cancel" in intent_tags:
            next_action = "先确认产品/服务名称和扣款方，再判断是否可在我司或合作服务流程内取消。"
        elif "refund" in intent_tags:
            next_action = "先确认扣款方、订单/权益名称和支付渠道，再判断是否进入我司退费或第三方服务商处理流程。"
        else:
            next_action = "先确认客户看到的完整产品/服务名称、页面入口、短信主体或扣款方。"
        prompt_text = "\n".join([
            "## 活动/增值服务结构化知识召回",
            "匹配状态：未命中已结构化的我司/合作增值服务清单。",
            f"疑似非我司或未纳入清单产品：{'是' if suspected else '待确认'}。",
            f"下一步：{next_action}",
            "",
            "### 匹配失败/非我司产品处理流程",
            "1. 不要直接承诺取消、退费或承认该产品属于我司；先说明当前未匹配到已收录的我司/合作增值服务。",
            "2. 引导客户补充完整产品/服务名称、扣款方、APP页面入口、订单号或短信主体；如涉及个人账单/扣款明细查询，再按账户查询流程核身。",
            "3. 若客户补充后确认是非我司产品或非合作服务，告知需联系对应服务方、商户或支付渠道处理，我司无法直接操作取消/退款。",
            "4. 若客户补充后命中我司/合作增值服务名称，重新进入活动/增值服务匹配，按对应服务 SOP 回答。",
            "",
            f"已收录服务清单：{known_names_text}",
        ])
        return {
            "status": "unmatched",
            "prompt_text": prompt_text,
            "slots": {
                "value_added_match_status": "unmatched",
                "value_added_matched_service_id": "",
                "value_added_matched_service_name": "",
                "value_added_suspected_non_company_product": suspected,
            },
            "references": [],
            "knowledge_matches": self._build_knowledge_matches(
                "unmatched",
                [],
                suspected_non_company_product=suspected,
            ),
            "matched_services": [],
        }

    @staticmethod
    def _looks_like_product_query(query: str) -> bool:
        product_markers = (
            "产品", "服务", "卡", "会员", "VIP", "保险", "权益", "券", "包",
            "活动", "扣款", "扣费", "订单", "续费", "服务费",
        )
        explicit_non_company = (
            "不是你们", "不是我司", "非我司", "别的平台", "其他平台",
            "第三方", "外部", "商户", "支付渠道",
        )
        return any(marker in query for marker in product_markers + explicit_non_company)

    @staticmethod
    def _build_knowledge_matches(
        match_status: str,
        matched_services: list[dict[str, Any]],
        *,
        suspected_non_company_product: bool,
    ) -> list[dict[str, Any]]:
        if not matched_services:
            return [{
                "domain": "活动",
                "category": "增值服务",
                "service_id": "",
                "service_name": "",
                "match_status": match_status,
                "suspected_non_company_product": suspected_non_company_product,
            }]
        return [
            {
                "domain": "活动",
                "category": "增值服务",
                "service_id": service.get("service_id") or "",
                "service_name": service.get("service_name") or "",
                "match_status": match_status,
                "suspected_non_company_product": suspected_non_company_product,
                "matched_aliases": service.get("aliases") or [],
            }
            for service in matched_services
        ]

    @staticmethod
    def _format_matched_prompt(
        service_names: list[str],
        aliases: list[str],
        text_blocks: list[dict[str, Any]],
        image_blocks: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = [
            "## 活动/增值服务结构化知识召回",
            "匹配状态：已命中已结构化服务。",
            f"匹配服务：{'、'.join(service_names)}",
        ]
        if aliases:
            lines.append(f"命中关键词：{'、'.join(aliases[:8])}")
        lines.extend([
            "使用要求：优先依据以下结构化来源回答；不要补充来源中没有的金额、时效或承诺。",
            "",
            "### 文本知识块",
        ])
        if text_blocks:
            for idx, block in enumerate(text_blocks, start=1):
                text = block.get("display_text") or block.get("text") or ""
                lines.append(f"[文本{idx}]\n{_truncate(text, 1800)}")
        else:
            lines.append("（无匹配文本块）")

        lines.append("\n### 图片补充块（多模态理解结果，非 OCR）")
        if image_blocks:
            for idx, block in enumerate(image_blocks, start=1):
                image_id = block.get("image_id") or f"image_{idx}"
                image_path = block.get("image_path") or ""
                text = block.get("display_text") or block.get("text") or ""
                lines.append(f"[图片{idx} {image_id} | {image_path}]\n{_truncate(text, 1000)}")
        else:
            lines.append("（无匹配图片补充块）")
        return "\n".join(lines)

    @staticmethod
    def _references_for(
        text_blocks: list[dict[str, Any]],
        image_blocks: list[dict[str, Any]],
    ) -> list[str]:
        refs: list[str] = []
        seen: set[str] = set()
        for block in [*text_blocks, *image_blocks]:
            source = block.get("source_file") or ""
            sheet = block.get("sheet") or ""
            image_path = block.get("image_path") or ""
            ref = " / ".join(part for part in [source, sheet, image_path] if part)
            if ref and ref not in seen:
                refs.append(ref)
                seen.add(ref)
        return refs


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n……（已截断，仅保留匹配片段）"
