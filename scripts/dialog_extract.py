"""Extract the first customer utterance with real business content.

Real-world call dialogs start with noise: '喂', '你好', name readback
('李春花'), bank name ('建设银行'), etc. Feeding these to a classifier
yields garbage-in / garbage-out.

Two extractors here:
  * extract_first_meaningful — drops greetings/filler/identity-readback
  * extract_first_business_intent — also drops 会话流程 signal (greeting,
    acknowledgement, closing, channel_check) so the remaining line is
    guaranteed to carry business semantics
"""

from __future__ import annotations

import re

# Greetings and filler that carry no business signal
_GREETING_PATTERNS = [
    r"^喂+[，,。]*$",
    r"^[嗯呃啊哎]+[，,。]*$",
    r"^你好[，,。]*$",
    r"^早上好[，,。]*$",
    r"^晚上好[，,。]*$",
    r"^能听到吗[？?]?$",
    r"^听得到[。.]?$",
    r"^[嗯对是好的可以]{1,4}[。.]?$",
    r"^我说[完了吗]*[。.?？]?$",
    r"^麻烦[你您]了?[。.]?$",
    r"^谢谢[。.]?$",
]

# Verification readback: short personal info answers
_IDENTITY_PATTERNS = [
    r"^[\u4e00-\u9fff]{2,4}[。.]?$",                  # 2-4 char name
    r"^[\u4e00-\u9fff]{2,4}[先生女士]?[。.]?$",
    r"^.{0,6}银行[。.]?$",                              # XX 银行
    r"^(建设|工商|农业|中国|招商|交通|邮政|光大|浦发|民生|兴业|华夏)(银行)?[。.]?$",
    r"^1[3-9]\d{9}[。.]?$",                            # phone number
    r"^\d{15,18}[xX]?[。.]?$",                         # ID number
    r"^是的[。.]?$",
    r"^对的?[。.]?$",
]

# Content that matches 会话流程 skills (greeting / identity / ack / channel_check / closing)
# Used by extract_first_business_intent to skip past them
_SESSION_FLOW_MARKERS = {
    # greeting_opening / channel_check
    "喂", "您好", "你好", "早上好", "晚上好",
    "能听到", "听得到", "在吗",
    # identity_readback: bank names
    "建设银行", "工商银行", "农业银行", "中国银行", "招商银行",
    "交通银行", "邮政银行", "光大银行", "浦发银行", "民生银行",
    # acknowledgement (short ack tokens handled by noise filter too)
    # closing
    "没别的了", "没其他问题", "就这样", "先这样", "拜拜", "再见", "挂了",
}

# Markers that strongly indicate business intent
_BUSINESS_INTENT_MARKERS = {
    # 还款/账单
    "还款", "账单", "欠款", "扣款", "还钱", "结清", "提前还",
    "还不上", "延期", "分期",
    # 逾期/催收
    "逾期", "催收", "协商", "减免", "停催", "投诉",
    # 费用/退款
    "费用", "利息", "手续费", "担保费", "退费", "退款", "费率",
    "溢余",
    # 贷款/额度
    "贷款", "借款", "放款", "额度", "借钱", "解约", "提额",
    # 会员/活动/优享
    "会员", "优惠", "营销", "增值服务", "轻享卡", "优享卡",
    # 业务办理
    "结清证明", "征信", "合同", "发票", "证明",
    # 账户
    "注销账户", "账号注销", "删除账号", "注销",
    # action markers
    "怎么", "为什么", "什么时候", "能不能", "可不可以", "需要",
    "申请", "办理", "开通", "取消", "查询", "反映",
}

MIN_CHARS = 6  # minimum length (after stripping punctuation) to consider "substantive"


def _is_noise(text: str) -> bool:
    """Return True if text is greeting, filler, or identity readback."""
    t = text.strip()
    if not t:
        return True
    for pat in _GREETING_PATTERNS + _IDENTITY_PATTERNS:
        if re.match(pat, t):
            return True
    # Strip punctuation and spaces to measure real content length
    stripped = re.sub(r"[\s，,。.?？!！…]", "", t)
    if len(stripped) < MIN_CHARS:
        return True
    return False


def _looks_like_session_flow(text: str) -> bool:
    """True if text reads primarily as greeting/identity/ack/channel/closing."""
    t = text.strip()
    if not t:
        return True
    # Contains any session-flow marker AND no business marker
    has_flow = any(m in t for m in _SESSION_FLOW_MARKERS)
    has_biz = any(m in t for m in _BUSINESS_INTENT_MARKERS)
    return has_flow and not has_biz


def _has_business_intent(text: str) -> bool:
    return any(m in text for m in _BUSINESS_INTENT_MARKERS)


def iter_customer_lines(dialog: str):
    """Yield each customer line from a `[坐席]/[客户]`-formatted dialog."""
    for raw in dialog.split("\n"):
        line = raw.strip()
        if line.startswith("[客户]"):
            yield line.replace("[客户]", "", 1).strip()


def extract_first_meaningful(dialog: str, k: int = 1) -> str:
    """Return up to `k` customer lines (concatenated) that pass the noise
    filter. Falls back to the first customer line if nothing substantive is
    found."""
    picks: list[str] = []
    first_any: str = ""
    for line in iter_customer_lines(dialog):
        if not line:
            continue
        if not first_any:
            first_any = line
        if _is_noise(line):
            continue
        picks.append(line)
        if len(picks) >= k:
            break
    if picks:
        return " ".join(picks)
    return first_any


def extract_first_business_intent(dialog: str, k: int = 1) -> str:
    """Return up to `k` customer lines that carry clear business intent.

    A line qualifies if it:
      - passes the noise filter (not greeting/filler/identity)
      - does NOT look like pure session-flow (greeting/ack/closing/bank readback)
      - contains at least one business-intent marker, OR is substantive
        (≥ 12 chars) without session-flow signals

    Falls back to `extract_first_meaningful(dialog, k)` if no business line is
    found — keeps eval runnable even on atypical transcripts.
    """
    picks: list[str] = []
    for line in iter_customer_lines(dialog):
        if not line or _is_noise(line):
            continue
        if _looks_like_session_flow(line):
            continue
        # prefer lines with explicit business markers; long ones still OK
        stripped = re.sub(r"[\s，,。.?？!！…]", "", line)
        if _has_business_intent(line) or len(stripped) >= 12:
            picks.append(line)
            if len(picks) >= k:
                break
    if picks:
        return " ".join(picks)
    return extract_first_meaningful(dialog, k=k)
