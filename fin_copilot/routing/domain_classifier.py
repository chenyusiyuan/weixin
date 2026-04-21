"""L1 Domain classifier — keyword scoring across 10 business domains plus conversation flow."""

from __future__ import annotations

from fin_copilot.models.conversation import ConversationState


# Domain names MUST match registry.json exactly (short names, no "问题" suffix)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "会话流程": [
        "喂", "你好", "您好", "早上好", "晚上好",
        "嗯", "对对", "好的", "可以", "明白",
        "我叫", "我是", "建设银行", "工商银行", "农业银行", "中国银行",
        "招商银行", "交通银行", "邮政银行", "身份证",
        "能听到吗", "听得到吗", "喂喂", "在吗", "信号",
        "没别的了", "没其他问题", "谢谢", "再见", "拜拜", "挂了",
    ],
    "会员": [
        "会员", "开通会员", "退会员", "会员权益", "VIP", "尊享会员",
        "会员费", "会员服务",
    ],
    "额度": [
        "额度", "提额", "没有额度", "可以贷多少", "借款额度", "可用额度",
        "额度冻结", "额度是多少", "额度为0",
    ],
    "还款": [
        "还款", "还钱", "账单", "欠款", "扣款", "还款日", "还款方式",
        "还款结果", "换绑银行卡", "换卡", "提前还款", "结清",
        "还款失败", "扣款失败", "怎么还款", "还款途径",
    ],
    "贷款": [
        "贷款", "借款", "放款", "审批进度", "借钱", "解约",
        "异地放款", "放款进度", "申请贷款",
    ],
    "费用": [
        "费用", "手续费", "利息", "退款", "扣费", "担保费", "退费",
        "费率", "溢余", "费用明细", "利率", "服务费",
    ],
    "活动": [
        "活动", "优惠", "营销", "增值服务", "轻享卡", "停止营销",
        "推销", "别打电话", "不要推销",
    ],
    "业务办理": [
        "结清证明", "征信", "合同", "发票", "注销授信", "开具证明",
        "征信修改", "征信记录",
    ],
    "账户": [
        "账户", "注销", "冻结", "登录", "注销账号", "删除账号",
        "账号", "已注销",
    ],
    "逾期": [
        "逾期", "催收", "协商", "减免", "延期还款", "协商还款", "停催",
        "投诉催收", "还不上", "没钱还", "二次分期", "还款困难", "过段时间再还",
        "晚点还", "缓几天还", "延后还款",
    ],
    "优享卡": [
        "优享卡", "优享",
    ],
}

DEFAULT_DOMAIN = "还款"


class DomainClassifier:
    """Keyword-based domain classifier for L1 routing."""

    def classify(self, query: str, state: ConversationState) -> str:
        """Score each domain by keyword matches; return the best match."""
        scores: dict[str, int] = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query)
            if score > 0:
                scores[domain] = score

        if not scores:
            # No keyword match — carry forward previous domain
            return state.intent.domain or DEFAULT_DOMAIN

        max_score = max(scores.values())
        top_domains = [d for d, s in scores.items() if s == max_score]

        # Tie-break: prefer current domain if it's in the tie
        if state.intent.domain and state.intent.domain in top_domains:
            return state.intent.domain

        return top_domains[0]
