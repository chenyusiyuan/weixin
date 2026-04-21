"""
Centralized mock data for all financial customer service tool handlers.
Profiles intentionally include simple cleartext test PII for local identity
verification, plus masked display fields for response templates.

Three primary test personas:
  - C100 张三: 逾期客户，协商还款中，VIP会员，多笔工单
  - C101 李四: 正常优质客户，高额度，提前还款需求
  - C102 王五: 新用户，额度冻结，有投诉记录
"""

# ---------------------------------------------------------------------------
# Customer profiles
# ---------------------------------------------------------------------------

CUSTOMERS: dict[str, dict] = {
    # === 张三 — 逾期客户 ===
    "C100": {
        "customer_name": "张三",
        "phone": "13812345678",
        "phone_masked": "138****5678",
        "id_number": "110101199003151234",
        "id_last4": "1234",
        "verified": False,
        "verification_level": "none",
        "registration_date": "2024-01-10",
        "account_status": "active",
        "age": 35,
        "gender": "男",
        "city": "深圳",
        "risk_tag": "medium",
    },
    # === 李四 — 正常优质客户 ===
    "C101": {
        "customer_name": "李四",
        "phone": "13900001111",
        "phone_masked": "139****1111",
        "id_number": "310110199505085678",
        "id_last4": "5678",
        "verified": False,
        "verification_level": "none",
        "registration_date": "2023-06-15",
        "account_status": "active",
        "age": 28,
        "gender": "男",
        "city": "北京",
        "risk_tag": "low",
    },
    # === 王五 — 新用户，额度冻结 ===
    "C102": {
        "customer_name": "王五",
        "phone": "18600002222",
        "phone_masked": "186****2222",
        "id_number": "510101198201019012",
        "id_last4": "9012",
        "verified": False,
        "verification_level": "none",
        "registration_date": "2026-02-20",
        "account_status": "frozen",
        "age": 42,
        "gender": "女",
        "city": "成都",
        "risk_tag": "high",
    },
}

DEFAULT_CUSTOMER_ID = "C100"

# ---------------------------------------------------------------------------
# Bills and repayment plans
# ---------------------------------------------------------------------------

BILLS: dict[str, dict] = {
    # 张三 — 逾期45天，一笔扣款失败
    "C100": {
        "bill_amount": 8500.00,
        "overdue_amount": 8500.00,
        "overdue_days": 45,
        "next_repayment_date": "2026-04-25",
        "repayment_status": "overdue",
        "monthly_payment": 850.00,
        "total_periods": 12,
        "remaining_periods": 7,
        "current_period": 5,
        "fee_detail": {
            "principal": 7200.00,
            "interest": 680.00,
            "guarantee_fee": 350.00,
            "service_fee": 120.00,
            "overdue_fee": 150.00,
        },
        "deduction_records": [
            {"date": "2026-01-25", "amount": 850.00, "status": "success"},
            {"date": "2026-02-25", "amount": 850.00, "status": "success"},
            {"date": "2026-03-25", "amount": 850.00, "status": "failed", "reason": "余额不足"},
            {"date": "2026-04-05", "amount": 850.00, "status": "failed", "reason": "余额不足"},
            {"date": "2026-04-10", "amount": 850.00, "status": "failed", "reason": "银行拒绝"},
        ],
        "repayment_history": [
            {"period": 1, "date": "2025-12-25", "amount": 850.00, "status": "on_time"},
            {"period": 2, "date": "2026-01-25", "amount": 850.00, "status": "on_time"},
            {"period": 3, "date": "2026-02-25", "amount": 850.00, "status": "on_time"},
            {"period": 4, "date": "2026-03-25", "amount": 850.00, "status": "overdue"},
            {"period": 5, "date": None, "amount": 850.00, "status": "pending"},
        ],
    },
    # 李四 — 正常还款，无逾期
    "C101": {
        "bill_amount": 3600.00,
        "overdue_amount": 0.00,
        "overdue_days": 0,
        "next_repayment_date": "2026-05-15",
        "repayment_status": "normal",
        "monthly_payment": 3600.00,
        "total_periods": 24,
        "remaining_periods": 16,
        "current_period": 8,
        "fee_detail": {
            "principal": 3000.00,
            "interest": 360.00,
            "guarantee_fee": 150.00,
            "service_fee": 90.00,
            "overdue_fee": 0.00,
        },
        "deduction_records": [
            {"date": "2026-04-15", "amount": 3600.00, "status": "success"},
            {"date": "2026-03-15", "amount": 3600.00, "status": "success"},
            {"date": "2026-02-15", "amount": 3600.00, "status": "success"},
        ],
        "repayment_history": [
            {"period": i, "date": f"2025-{10+i:02d}-15" if i <= 3 else f"2026-{i-3:02d}-15",
             "amount": 3600.00, "status": "on_time"}
            for i in range(1, 9)
        ],
        "early_settlement_amount": 52800.00,
        "early_settlement_discount": 1200.00,
    },
    # 王五 — 有一笔小额逾期
    "C102": {
        "bill_amount": 1500.00,
        "overdue_amount": 1500.00,
        "overdue_days": 12,
        "next_repayment_date": "2026-04-20",
        "repayment_status": "overdue",
        "monthly_payment": 500.00,
        "total_periods": 6,
        "remaining_periods": 4,
        "current_period": 2,
        "fee_detail": {
            "principal": 1300.00,
            "interest": 120.00,
            "guarantee_fee": 50.00,
            "service_fee": 30.00,
            "overdue_fee": 15.00,
        },
        "deduction_records": [
            {"date": "2026-03-20", "amount": 500.00, "status": "success"},
            {"date": "2026-04-08", "amount": 500.00, "status": "failed", "reason": "银行卡已冻结"},
        ],
        "repayment_history": [
            {"period": 1, "date": "2026-03-20", "amount": 500.00, "status": "on_time"},
            {"period": 2, "date": None, "amount": 500.00, "status": "overdue"},
        ],
    },
}

# ---------------------------------------------------------------------------
# Loan service info
# ---------------------------------------------------------------------------

LOANS: dict[str, dict] = {
    # 张三 — 两笔在贷，一笔豆豆钱一笔信用贷
    "C100": {
        "loan_amount": 50000.00,
        "loan_term": 12,
        "loan_status": "active",
        "disbursement_status": "completed",
        "disbursement_progress": "已放款至尾号5678的建设银行账户",
        "contract_id": "LN2024011000001",
        "loan_date": "2024-01-10",
        "outstanding_loans_count": 2,
        "loan_product": "豆豆钱",
        "annual_rate": "13.2%",
        "loans_detail": [
            {
                "contract_id": "LN2024011000001",
                "product": "豆豆钱",
                "amount": 50000.00,
                "remaining": 35000.00,
                "status": "overdue",
                "overdue_days": 45,
            },
            {
                "contract_id": "LN2025060100002",
                "product": "信用贷",
                "amount": 20000.00,
                "remaining": 15000.00,
                "status": "active",
                "overdue_days": 0,
            },
        ],
    },
    # 李四 — 一笔大额贷款，正常还款
    "C101": {
        "loan_amount": 80000.00,
        "loan_term": 24,
        "loan_status": "active",
        "disbursement_status": "completed",
        "disbursement_progress": "已放款至尾号1111的招商银行账户",
        "contract_id": "LN2023061500003",
        "loan_date": "2023-06-15",
        "outstanding_loans_count": 1,
        "loan_product": "豆豆钱",
        "annual_rate": "10.8%",
        "loans_detail": [
            {
                "contract_id": "LN2023061500003",
                "product": "豆豆钱",
                "amount": 80000.00,
                "remaining": 52800.00,
                "status": "active",
                "overdue_days": 0,
            },
        ],
    },
    # 王五 — 一笔小额借款
    "C102": {
        "loan_amount": 3000.00,
        "loan_term": 6,
        "loan_status": "active",
        "disbursement_status": "completed",
        "disbursement_progress": "已放款至尾号2222的工商银行账户",
        "contract_id": "LN2026022000004",
        "loan_date": "2026-02-20",
        "outstanding_loans_count": 1,
        "loan_product": "豆豆钱",
        "annual_rate": "14.4%",
        "loans_detail": [
            {
                "contract_id": "LN2026022000004",
                "product": "豆豆钱",
                "amount": 3000.00,
                "remaining": 2000.00,
                "status": "overdue",
                "overdue_days": 12,
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# Membership service info
# ---------------------------------------------------------------------------

MEMBERSHIPS: dict[str, dict] = {
    # 张三 — VIP会员，已使用权益
    "C100": {
        "member_status": "active",
        "member_type": "VIP尊享会员",
        "member_start_date": "2025-10-01",
        "member_expire_date": "2026-10-01",
        "member_fee": 99.00,
        "privileges": ["借款优惠券", "视频会员月卡", "音乐会员月卡", "10元话费券"],
        "privileges_used": True,
        "used_privileges": ["视频会员月卡", "音乐会员月卡"],
        "unused_privileges": ["借款优惠券", "10元话费券"],
        "cancel_eligible": True,
        "refund_eligible": False,
        "refund_reason": "已使用部分权益，不满足退费条件",
        "auto_renew": True,
    },
    # 李四 — 普通会员，已过期
    "C101": {
        "member_status": "expired",
        "member_type": "普通会员",
        "member_start_date": "2025-06-01",
        "member_expire_date": "2026-06-01",
        "member_fee": 49.00,
        "privileges": ["借款优惠券"],
        "privileges_used": False,
        "used_privileges": [],
        "unused_privileges": ["借款优惠券"],
        "cancel_eligible": False,
        "refund_eligible": True,
        "refund_reason": "未使用任何权益，可申请退费",
        "refund_amount": 49.00,
        "auto_renew": False,
    },
    # 王五 — 无会员
    "C102": {
        "member_status": "none",
        "member_type": None,
        "member_start_date": None,
        "member_expire_date": None,
        "member_fee": 0.00,
        "privileges": [],
        "privileges_used": False,
        "used_privileges": [],
        "unused_privileges": [],
        "cancel_eligible": False,
        "refund_eligible": False,
        "auto_renew": False,
    },
}

# ---------------------------------------------------------------------------
# Quota service info
# ---------------------------------------------------------------------------

QUOTAS: dict[str, dict] = {
    # 张三 — 有额度但因逾期部分冻结
    "C100": {
        "total_quota": 80000.00,
        "available_quota": 0.00,
        "used_quota": 50000.00,
        "frozen_quota": 30000.00,
        "quota_status": "partially_frozen",
        "assessment_result": "因逾期冻结可用额度，结清后可恢复",
        "last_assessment_date": "2026-04-01",
        "freeze_reason": "逾期超30天",
        "restore_condition": "结清当前逾期账单后，额度将在1-3个工作日内恢复",
    },
    # 李四 — 高额度优质客户
    "C101": {
        "total_quota": 150000.00,
        "available_quota": 70000.00,
        "used_quota": 80000.00,
        "frozen_quota": 0.00,
        "quota_status": "normal",
        "assessment_result": "信用评估优秀，可申请提额",
        "last_assessment_date": "2026-04-05",
        "can_increase": True,
        "increase_range": "预计可提额至200000元",
    },
    # 王五 — 额度冻结
    "C102": {
        "total_quota": 5000.00,
        "available_quota": 0.00,
        "used_quota": 3000.00,
        "frozen_quota": 2000.00,
        "quota_status": "frozen",
        "assessment_result": "账户风险评估未通过，额度已全部冻结",
        "last_assessment_date": "2026-03-25",
        "freeze_reason": "新用户+逾期，触发风控",
        "restore_condition": "需结清逾期并保持正常还款3个月",
    },
}

# ---------------------------------------------------------------------------
# Tickets (工单记录)
# ---------------------------------------------------------------------------

TICKETS: dict[str, list[dict]] = {
    # 张三 — 多笔工单：协商还款 + 费用咨询 + 催收投诉
    "C100": [
        {
            "ticket_id": "TK20260409001",
            "type": "逾期协商",
            "status": "processing",
            "created_at": "2026-04-09T10:30:00",
            "summary": "客户申请逾期协商还款方案，希望分6期还清",
            "handler": "贷后专员A组",
            "expected_callback": "2026-04-11",
        },
        {
            "ticket_id": "TK20260405002",
            "type": "费用争议",
            "status": "resolved",
            "created_at": "2026-04-05T14:20:00",
            "resolved_at": "2026-04-07T09:00:00",
            "summary": "客户咨询担保费和逾期费的计算方式",
            "resolution": "已向客户说明费用明细，客户表示理解",
        },
        {
            "ticket_id": "TK20260401003",
            "type": "催收投诉",
            "status": "resolved",
            "created_at": "2026-04-01T08:45:00",
            "resolved_at": "2026-04-03T16:00:00",
            "summary": "客户反映催收电话频繁影响工作",
            "resolution": "已添加催收备注，调整催收频率",
        },
    ],
    # 李四 — 提前还款咨询
    "C101": [
        {
            "ticket_id": "TK20260410004",
            "type": "提前还款",
            "status": "processing",
            "created_at": "2026-04-10T11:00:00",
            "summary": "客户咨询提前全额结清方案及违约金",
            "handler": "还款专员",
            "expected_callback": "2026-04-12",
        },
        {
            "ticket_id": "TK20260320005",
            "type": "额度提升",
            "status": "resolved",
            "created_at": "2026-03-20T09:30:00",
            "resolved_at": "2026-03-22T10:00:00",
            "summary": "客户申请提升借款额度",
            "resolution": "审批通过，额度从120000提升至150000",
        },
    ],
    # 王五 — 投诉 + 账户冻结咨询
    "C102": [
        {
            "ticket_id": "TK20260411006",
            "type": "账户冻结",
            "status": "processing",
            "created_at": "2026-04-11T15:00:00",
            "summary": "客户咨询账户被冻结的原因及解冻条件",
            "handler": "风控专员",
            "expected_callback": "2026-04-14",
        },
        {
            "ticket_id": "TK20260408007",
            "type": "费用投诉",
            "status": "processing",
            "created_at": "2026-04-08T10:15:00",
            "summary": "客户对担保费收取有异议，认为未事先告知",
            "handler": "投诉处理专员",
            "expected_callback": "2026-04-13",
        },
        {
            "ticket_id": "TK20260330008",
            "type": "银行卡问题",
            "status": "resolved",
            "created_at": "2026-03-30T13:40:00",
            "resolved_at": "2026-04-01T09:00:00",
            "summary": "客户反映绑定的银行卡已冻结无法扣款",
            "resolution": "指导客户更换还款银行卡",
        },
    ],
}

# Counter for generating new ticket IDs (simulates a sequence)
_ticket_counter: int = 8

# ---------------------------------------------------------------------------
# Identity verification data (for 核身 / KYC)
# ---------------------------------------------------------------------------

VERIFICATION_DB: dict[str, dict] = {
    "C100": {
        "real_name": "张三",
        "phone": "13812345678",
        "id_last4": "1234",
    },
    "C101": {
        "real_name": "李四",
        "phone": "13900001111",
        "id_last4": "5678",
    },
    "C102": {
        "real_name": "王五",
        "phone": "18600002222",
        "id_last4": "9012",
    },
}

# Quick lookup: phone -> customer_id
PHONE_TO_CUSTOMER: dict[str, str] = {
    v["phone"]: cid for cid, v in VERIFICATION_DB.items()
}

# ---------------------------------------------------------------------------
# Call history (进线记录)
# ---------------------------------------------------------------------------

CALL_HISTORY: dict[str, list[dict]] = {
    "C100": [
        {
            "call_id": "CALL20260409001",
            "time": "2026-04-09T10:30:00",
            "channel": "在线",
            "agent_name": "坐席A",
            "scenario": "逾期协商",
            "summary": "客户申请延期还款至下月 10 号",
        },
        {
            "call_id": "CALL20260405002",
            "time": "2026-04-05T14:20:00",
            "channel": "热线",
            "agent_name": "坐席B",
            "scenario": "费用咨询",
            "summary": "咨询担保费计算方式",
        },
        {
            "call_id": "CALL20260401003",
            "time": "2026-04-01T08:45:00",
            "channel": "热线",
            "agent_name": "坐席C",
            "scenario": "催收投诉",
            "summary": "反映催收电话过于频繁",
        },
    ],
    "C101": [
        {
            "call_id": "CALL20260410004",
            "time": "2026-04-10T11:00:00",
            "channel": "在线",
            "agent_name": "坐席D",
            "scenario": "提前还款",
            "summary": "咨询提前全额结清方案",
        },
    ],
    "C102": [
        {
            "call_id": "CALL20260411005",
            "time": "2026-04-11T15:00:00",
            "channel": "热线",
            "agent_name": "坐席E",
            "scenario": "账户冻结咨询",
            "summary": "询问账户冻结原因",
        },
        {
            "call_id": "CALL20260408006",
            "time": "2026-04-08T10:15:00",
            "channel": "在线",
            "agent_name": "坐席F",
            "scenario": "费用投诉",
            "summary": "对担保费收取有异议",
        },
    ],
}

# ---------------------------------------------------------------------------
# SMS history (短信记录)
# ---------------------------------------------------------------------------

SMS_HISTORY: dict[str, list[dict]] = {
    "C100": [
        {"sms_id": "SMS20260410A", "time": "2026-04-10T09:00:00", "type": "催收", "content": "【豆豆钱】您有一笔账单已逾期 45 天,请及时还款..."},
        {"sms_id": "SMS20260409A", "time": "2026-04-09T09:00:00", "type": "催收", "content": "【豆豆钱】您有一笔账单已逾期..."},
        {"sms_id": "SMS20260325A", "time": "2026-03-25T08:00:00", "type": "扣款提醒", "content": "【豆豆钱】本月账单 850 元将于今日自动扣款..."},
    ],
    "C101": [
        {"sms_id": "SMS20260415A", "time": "2026-04-15T08:00:00", "type": "扣款成功", "content": "【豆豆钱】本月账单 3600 元已扣款成功..."},
    ],
    "C102": [
        {"sms_id": "SMS20260408B", "time": "2026-04-08T14:00:00", "type": "扣款失败", "content": "【豆豆钱】扣款失败,请及时处理..."},
        {"sms_id": "SMS20260320B", "time": "2026-03-20T09:00:00", "type": "扣款成功", "content": "【豆豆钱】本月账单 500 元已扣款成功..."},
    ],
}

# ---------------------------------------------------------------------------
# Stop-collection history (停催记录)
# ---------------------------------------------------------------------------

STOP_COLLECTION_HISTORY: dict[str, list[dict]] = {
    "C100": [
        {
            "request_id": "STOP20260401001",
            "request_time": "2026-04-01T09:00:00",
            "request_type": "客户本人停催",
            "status": "已受理",
            "phone": "13812345678",
            "reason": "客户投诉催收频率过高",
            "valid_until": "2026-04-10",
        },
    ],
    "C101": [],
    "C102": [],
}

# ---------------------------------------------------------------------------
# Refund history (退费记录)
# ---------------------------------------------------------------------------

REFUND_HISTORY: dict[str, list[dict]] = {
    "C100": [],
    "C101": [
        {
            "refund_id": "RF20260228001",
            "apply_time": "2026-02-28T10:00:00",
            "refund_type": "会员退费",
            "amount": 49.00,
            "status": "已到账",
            "completed_time": "2026-03-02T14:00:00",
            "operator": "xiedan51389",
        },
    ],
    "C102": [
        {
            "refund_id": "RF20260402001",
            "apply_time": "2026-04-02T11:00:00",
            "refund_type": "溢余退款",
            "amount": 120.00,
            "status": "处理中",
            "operator": None,
        },
    ],
}
