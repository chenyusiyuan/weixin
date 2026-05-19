# Mock 工具槽位后的 Branch 选择评估

- 生成时间：2026-04-27 17:25:24
- 数据源：`raw_test.jsonl`。
- 口径：跳过 skill 选择，使用真实 query 的 `gold_skill`；模拟已核身客户，执行 mock 工具，把工具结果和 query 抽取槽位合并后跑真实 `select_branch_variant`。
- 工具范围：`read-all`；persona 策略：`auto`。
- `expr_selected` 是生产确定性分支；`semantic_candidate` 只是 hint 分支的离线文本候选，不等价于 LLM 真实选择。

## 总览

- 真实 query：2846；评估记录：2835。
- expr selected：1103；expr not selected：1732。
- semantic candidate：confident 0；low 1540；no_select 1295。

## Skill 汇总

| skill_id | 名称 | records | expr selected | expr top | semantic top |
|---|---|---:|---:|---|---|
| `account_cancellation` | 注销账户 | 65 | 0 | - | `escalate_to_tier2` 62；`cannot_cancel_outstanding` 3 |
| `bill_date_credit_impact` | 账单日还款是否影响征信 | 9 | 0 | - | `normal_repayment_credit` 3；`repayment_day_collection_call_credit_concern` 2；`overdue_credit_reporting` 2；`existing_overdue_credit_repair` 1 |
| `bill_deduction_query` | 查询账单扣款情况 | 103 | 0 | - | `value_added_service_deduction_matched` 58；`bill_overdue` 25；`deduction_pending` 7；`deduction_failed` 6 |
| `cancel_credit_authorization` | 注销授信额度 | 11 | 11 | `self_operated_has_loan` 9；`non_self_operated` 1；`self_operated_can_cancel` 1 | `self_operated_can_cancel` 11 |
| `cancel_value_added_service` | 取消增值服务 | 10 | 0 | - | `retention_success` 9；`already_closed_no_charge` 1 |
| `card_rebinding` | 换绑银行卡 | 34 | 0 | - | `app_path_not_found` 30；`card_rebinding_failed` 2；`cannot_operate_for_customer` 2 |
| `clearance_certificate` | 开具结清证明 | 47 | 47 | `not_cleared` 30；`self_service` 17 | `agent_assist` 27；`self_service` 16；`not_cleared` 3；`system_failed` 1 |
| `close_pre_reminder` | 关闭预提醒服务 | 4 | 1 | `proceed_close` 1 | `proceed_close` 4 |
| `collection_complaint` | 投诉催收 | 187 | 152 | `high_frequency` 108；`violent_collection` 20；`expose_contacts` 19；`bad_attitude` 5 | `high_frequency` 164；`expose_contacts` 18；`bad_attitude` 5 |
| `contract_retrieval` | 调取合同 | 22 | 22 | `tier1_overdue` 22 | `tier1_overdue` 21；`tier1_active` 1 |
| `credit_inquiry` | 征信问题咨询 | 39 | 12 | `overdue_impact` 11；`reporting_rules` 1 | `credit_inquiry_general` 27；`overdue_impact` 11；`reporting_rules` 1 |
| `credit_modification` | 修改征信 | 20 | 20 | `self_operated` 19；`non_self_operated` 1 | `non_self_operated` 19；`self_operated` 1 |
| `deduction_issues` | 扣款相关问题咨询 | 17 | 0 | - | `amount_mismatch` 17 |
| `disbursement_progress` | 放款进度查询 | 10 | 0 | - | `disbursing_status` 10 |
| `early_deduction` | 未到还款日被提前扣款 | 7 | 0 | - | `pre_deduction_sms_notice` 3；`misunderstanding_due_date` 2；`no_pre_deduction_sms_received` 1；`genuine_early_deduction` 1 |
| `early_loan_clearance` | 提前清贷需求 | 287 | 0 | - | `assist_clearance_no_tag` 287 |
| `fee_consultation_tier1` | 费用咨询（一线） | 32 | 0 | - | `guarantee_fee_legality` 32 |
| `fee_consultation_tier2` | 费用咨询（二线/高阶内诉） | 8 | 0 | - | `disguised_interest_objection` 4；`customer_accepts` 3；`compliance_document_request` 1 |
| `fee_detail_query` | 查询费用明细及综合费率 | 83 | 0 | - | `tier2_rate_query_by_order_age` 66；`high_rate_objection` 6；`irr_calculation_explanation` 5；`specific_period_query` 4 |
| `fee_refund_status` | 退费未到账情况咨询 | 9 | 0 | - | `refund_completed` 9 |
| `fee_refund_tier1` | 要求退费（一线） | 25 | 0 | - | `refund_not_eligible` 25 |
| `fee_refund_tier2` | 要求退费（二线/高阶内诉） | 5 | 0 | - | `customer_accepts_proposal` 3；`membership_offset` 2 |
| `invoice_issuance` | 发票开具 | 6 | 6 | `doudou_self_service` 6 | `doudou_self_service` 6 |
| `light_card_cancel_refund` | 轻享卡取消退费 | 1 | 0 | - | `provide_vendor_contact` 1 |
| `loan_consultation` | 贷款咨询 | 42 | 0 | - | `disbursement_timeline` 42 |
| `loan_dispute_refund` | 借款争议特殊场景退费 | 6 | 0 | - | `fraud_with_police_report` 6 |
| `loan_termination` | 贷款解约 | 10 | 0 | - | `cannot_terminate` 6；`retention_success` 3；`ops_ticket_for_termination` 1 |
| `member_cancel` | 取消会员 | 42 | 0 | - | `not_needed_deferred` 19；`unknown_source_deferred` 16；`no_record` 5；`retain_fail` 2 |
| `member_consultation` | 会员咨询 | 25 | 0 | - | `benefit_change` 25 |
| `member_refund` | 退会员费用 | 32 | 0 | - | `expired_or_used` 29；`music_fitness_used` 2；`active_benefits` 1 |
| `no_quota_issue` | 无额度问题 | 21 | 0 | - | `no_quota_after_clearance` 12；`reserved_loan` 3；`ops_ticket` 2；`withdrawal_quota_zero` 2 |
| `other_certificate` | 开具其他证明 | 1 | 0 | - | `identify_order_and_certificate` 1 |
| `overdue_negotiation` | 协商还款 | 659 | 659 | `mid_overdue` 659 | `pre_overdue` 659 |
| `overpayment_refund` | 客户对公转账出错退溢余 | 10 | 0 | - | `incomplete_proof` 4；`genuine_overpayment` 2；`transfer_verified_full_match` 2；`not_our_corporate_account` 2 |
| `post_loan_verification` | 核实贷后信息 | 109 | 68 | `verify_account` 49；`verify_staff` 14；`verify_institution` 5 | `verify_account` 90；`verify_staff` 14；`verify_institution` 5 |
| `premium_card_cancel` | 取消优享卡 | 4 | 0 | - | `no_record` 2；`retain_fail` 1；`accidental_purchase` 1 |
| `premium_card_inquiry` | 优享卡咨询 | 3 | 0 | - | `purchased_inquire` 2；`not_purchased` 1 |
| `premium_card_refund` | 退优享卡费用 | 2 | 0 | - | `refund_approved` 2 |
| `quota_consultation` | 额度咨询 | 8 | 0 | - | `max_quota` 8 |
| `refund_value_added_service` | 退增值服务费 | 1 | 0 | - | `tianchuang_credit_refund` 1 |
| `repayment_method_inquiry` | 咨询还款方式 | 196 | 0 | - | `auto_deduction_detail` 105；`manual_repayment_path` 91 |
| `repayment_result_query` | 查询还款结果 | 133 | 0 | - | `repayment_processing` 94；`repayment_success` 34；`repayment_delayed` 5 |
| `repayment_status_issue` | 还款状态异常 | 351 | 0 | - | `failure_insufficient_balance_still_low` 222；`failure_bank_card_contract` 96；`failure_card_limit_has_other_card` 7；`failure_channel_corporate_payment` 7 |
| `stop_collection` | 要求停催 | 119 | 105 | `normal_stop` 93；`escalate_stop` 10；`supervisor_stop` 2 | `normal_stop` 119 |
| `stop_marketing` | 停止营销 | 10 | 0 | - | `kakaday_is_our_product` 9；`deactivated_received_marketing` 1 |
| `value_added_service_inquiry` | 增值服务咨询 | 10 | 0 | - | `explain_tianchuang_credit` 10 |

## 抽样明细

### `account_cancellation` 注销账户
- records：65；expr selected：0；not selected：65。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想关闭授信额度并注销账户。 | C100 | `-` | `escalate_to_tier2`/no_select | 0.046 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想注销账户，但人脸识别总是失败，这是什么原因？ | C100 | `-` | `escalate_to_tier2`/no_select | 0.046 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `bill_date_credit_impact` 账单日还款是否影响征信
- records：9；expr selected：0；not selected：9。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想咨询豆豆钱逾期一天是否会影响信用记录。 | C100 | `-` | `existing_overdue_credit_repair`/no_select | 0.011 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我今天需要还款4006元，但明天才能还款，是否可以？ | C100 | `-` | `normal_repayment_credit`/no_select | 0.034 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `bill_deduction_query` 查询账单扣款情况
- records：103；expr selected：0；not selected：103。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 今天早上众安保险怎么又从我这边扣款了？扣了274元。 | C100 | `-` | `deduction_pending`/no_select | 0.014 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我今天有一笔你们平台的账单，请帮我查看一下。 | C100 | `-` | `bill_overdue`/no_select | 0.018 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `cancel_credit_authorization` 注销授信额度
- records：11；expr selected：11；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想提前关闭你们平台的授信额度。 | C100 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.258 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我早上在你们的APP里有一个网络贷款的申请，但你们的APP把我推给了一家第三方中介公司，他们早上给我打了几个电话进行线上分析。我现在要求收回我在APP的所有个人... | C100 | `non_self_operated` | `self_operated_can_cancel`/low_confidence | 0.253 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "non_self_operated"}` |
| 我想请你帮我关闭征信上的账号，因为我要贷款买房，需要查询征信。 | C100 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.258 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我要撤回个人信息处理的授权。 | C100 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.259 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我想在豆豆钱平台注销授信额度。 | C100 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.261 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 帮我关闭所有的授信额度。 | C100 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.258 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |

### `cancel_value_added_service` 取消增值服务
- records：10；expr selected：0；not selected：10。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想问一下，你们这个平台有没有一个可以赚钱的卡，能取消吗？ | C100 | `-` | `retention_success`/no_select | 0.011 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 我在平台上看到开了两个卡，一个是金钱卡，另一个是某种卡，金额分别是70多元和500-700多元。我想取消这些卡的续费。 | C100 | `-` | `retention_success`/no_select | 0.011 | `{"overdue_days": 45, "repayment_status": "overdue"}` |

### `card_rebinding` 换绑银行卡
- records：34；expr selected：0；not selected：34。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我刚才还款时，换卡还款操作不了，出现了问题。 | C100 | `-` | `card_rebinding_failed`/no_select | 0.007 | `{}` |
| 我想修改还款银行卡，请问如何操作？ | C100 | `-` | `app_path_not_found`/no_select | 0.026 | `{}` |

### `clearance_certificate` 开具结清证明
- records：47；expr selected：47；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我在微信卡卡贷借款，已经结清了，工作人员让我打这个电话开具结清证明。 | C100 | `self_service` | `self_service`/low_confidence | 0.226 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在平台有一笔借款已经还清，想要开具结清证明。 | C100 | `self_service` | `self_service`/low_confidence | 0.226 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我现在能开具结清证明了吗 | C100 | `not_cleared` | `agent_assist`/low_confidence | 0.166 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 请给我发送结清证明，我今天已经结清了。 | C100 | `self_service` | `self_service`/low_confidence | 0.222 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我已经还清了钱塘钱的贷款，他们让我打这个电话来拿结清证明。 | C100 | `self_service` | `self_service`/low_confidence | 0.222 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我已经结清欠款并还款了，为什么还打电话？结清证明至今没有开具给我。 | C100 | `not_cleared` | `agent_assist`/low_confidence | 0.165 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `close_pre_reminder` 关闭预提醒服务
- records：4；expr selected：1；not selected：3。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 请在我还款前，先不要给我打电话。 | C100 | `proceed_close` | `proceed_close`/low_confidence | 0.225 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 在还款日之前，为什么会有电话打来？ | C100 | `-` | `proceed_close`/low_confidence | 0.225 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我从未逾期，但你们一天内不停地打电话提醒我周末还款日，一天打800个电话，能否关掉这个电话提醒？ | C100 | `-` | `proceed_close`/low_confidence | 0.229 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `collection_complaint` 投诉催收
- records：187；expr selected：152；not selected：35。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的账单已经处理完了，为什么还在打电话？ | C100 | `high_frequency` | `high_frequency`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "frequency"}` |
| 我今天1:50左右，也遇到了同样的情况，电话响一声就挂断了 | C100 | `high_frequency` | `high_frequency`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "frequency"}` |
| 你们的电话催收天天打，已经影响到我的生活了。 | C100 | `high_frequency` | `high_frequency`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "frequency"}` |
| 我的贷款处于逾期状态，前两天有人联系我自称是法院人员，通过电话和微信发送短信，我昨天已投诉，现在处理情况如何？ | C100 | `violent_collection` | `high_frequency`/low_confidence | 0.169 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "violence"}` |
| 为什么平台在催我还款，但我已经没有借款了？ | C100 | `-` | `high_frequency`/low_confidence | 0.154 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想反馈豆豆钱的催收问题。 | C100 | `-` | `high_frequency`/low_confidence | 0.154 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `contract_retrieval` 调取合同
- records：22；expr selected：22；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想查询我的紧急联系人信息 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.191 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我需要将我在豆豆钱平台的所有借款合同以邮箱形式发送给我。 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.190 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想查看我在豆豆钱的借款合同，但我查询不到 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 为什么在借款平台上现在看不到还款期数和借款合同等信息 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.190 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想查询我的借款合同何时能发送给我 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.190 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在你们APP的借款，想问一下是否有合同提供？我在APP上没有查到合同，在哪里能看到？ | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.200 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `credit_inquiry` 征信问题咨询
- records：39；expr selected：12；not selected：27。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的征信报告显示上海维信汇智（你们公司）有一笔约300元的逾期记录，我想消除这个逾期记录，但找不到还款渠道。 | C100 | `overdue_impact` | `overdue_impact`/low_confidence | 0.193 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "overdue_impact"}` |
| 如何处理因还款日期问题导致的逾期记录？ | C100 | `overdue_impact` | `overdue_impact`/low_confidence | 0.190 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "overdue_impact"}` |
| 我想咨询如何处理征信上报和征信费用的问题 | C100 | `reporting_rules` | `reporting_rules`/low_confidence | 0.192 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "reporting_rules"}` |
| 我想问一下，这个平台逾期几天才上征信？ | C100 | `overdue_impact` | `overdue_impact`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "overdue_impact"}` |
| 咨询朋友在贵公司借款后延期，是否会向他人发送信息或拨打电话。 | C100 | `-` | `credit_inquiry_general`/low_confidence | 0.131 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我有一笔欠款已经二次分期，但收到了代偿短信。 | C100 | `-` | `credit_inquiry_general`/low_confidence | 0.131 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `credit_modification` 修改征信
- records：20；expr selected：20；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的钱包逾期了，我想一次性还清，但我的征信报告显示是关注状态，我想解除关注状态。 | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.205 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我在2025年2月6日有一笔在你们平台的借贷，额度28000元，一直在还款，现已还10期，从未逾期。但有其他平台打电话和发短信说我逾期了，声称你们平台从其他平台... | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.207 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我之前在你们平台有逾期，现已全部还清，但征信报告显示有国润财险的代偿记录，需要处理。 | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.209 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我的征信报告上有一个代偿记录，金额一百多块钱，是在疫情期间产生的，当时我不懂什么是代偿，你们也没有联系我。现在因为这个代偿记录影响了孩子购买学区房，能否帮我处理... | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.211 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 帮我查询一笔已还清的借款，并更新征信记录。 | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.206 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我在征信上看到有维护金融的代偿记录，所以我想协商处理这个代偿问题。 | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.209 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |

### `deduction_issues` 扣款相关问题咨询
- records：17；expr selected：0；not selected：17。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想咨询一下，我的优惠券会自动扣款吗？ | C100 | `-` | `amount_mismatch`/no_select | 0.059 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想确认今天是我的还款日，并且今天24点之前还款是否都不算逾期。 | C100 | `-` | `amount_mismatch`/no_select | 0.051 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `disbursement_progress` 放款进度查询
- records：10；expr selected：0；not selected：10。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的App上微信卡卡贷有2400元、2万元、4500万元、500元，但我点击普通通道后显示放款失败。 | C100 | `-` | `disbursing_status`/no_select | 0.046 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我今天收到的这笔贷款，现在怎么看不见 | C100 | `-` | `disbursing_status`/no_select | 0.046 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `early_deduction` 未到还款日被提前扣款
- records：7；expr selected：0；not selected：7。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想问一下，我的银行卡今天被豆豆钱扣款了，但我的账单日是7号，为什么会提前扣款？ | C100 | `-` | `misunderstanding_due_date`/no_select | 0.032 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 12号你们已经扣款了，我不理解为什么扣款。 | C100 | `-` | `pre_deduction_sms_notice`/no_select | 0.014 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `early_loan_clearance` 提前清贷需求
- records：287；expr selected：0；not selected：287。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想提前还款。 | C101 | `-` | `assist_clearance_no_tag`/low_confidence | 0.141 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我想提前还款，并要求减免费用。 | C101 | `-` | `assist_clearance_no_tag`/low_confidence | 0.141 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_consultation_tier1` 费用咨询（一线）
- records：32；expr selected：0；not selected：32。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我以前在你们平台借过钱，现在借不了钱了，为什么还在扣费？ | C100 | `-` | `guarantee_fee_legality`/no_select | 0.095 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想咨询一下，我昨天借款之后，被扣了1880元。 | C100 | `-` | `guarantee_fee_legality`/no_select | 0.095 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `fee_consultation_tier2` 费用咨询（二线/高阶内诉）
- records：8；expr selected：0；not selected：8。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我现在要全额还款，但你们的担保费不合理，我已经投诉了，你们到现在没给我回电话。 | C100 | `-` | `disguised_interest_objection`/no_select | 0.007 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我要协商平台利息较高的问题，请帮我计算一下利息。 | C100 | `-` | `customer_accepts`/no_select | 0.008 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `fee_detail_query` 查询费用明细及综合费率
- records：83；expr selected：0；not selected：83。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 为什么我的账户里有一个叫东富的条目？ | C100 | `-` | `tier2_rate_query_by_order_age`/no_select | 0.011 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想查询今天是否有还款账单。 | C100 | `-` | `tier2_rate_query_by_order_age`/no_select | 0.011 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `fee_refund_status` 退费未到账情况咨询
- records：9；expr selected：0；not selected：9。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我之前还款的钱是朋友帮我支付的，客服说会退给我，为什么到现在还没到账？ | C101 | `-` | `refund_completed`/no_select | 0.056 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我前两天反映的退款事宜，至今为何仍未处理完成？ | C101 | `-` | `refund_completed`/no_select | 0.065 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_refund_tier1` 要求退费（一线）
- records：25；expr selected：0；not selected：25。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想问一下，你们这边能给帮忙减免一下利息吗？ | C100 | `-` | `refund_not_eligible`/low_confidence | 0.137 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想对本次账单做一个减免。 | C100 | `-` | `refund_not_eligible`/low_confidence | 0.138 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `fee_refund_tier2` 要求退费（二线/高阶内诉）
- records：5；expr selected：0；not selected：5。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我联系了您提供的电话，对方表示无法退款，请问该如何处理？ | C100 | `-` | `customer_accepts_proposal`/no_select | 0.037 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我多次致电客服，要求退还利息和担保费，因为费用过高。客服承诺1-2个工作日会有专人回电，但至今未收到回复，且总是讨论还款问题。我询问退费事宜，客服表示不清楚。 | C100 | `-` | `membership_offset`/no_select | 0.033 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `invoice_issuance` 发票开具
- records：6；expr selected：6；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我有两笔借款，其中一笔是最后一期。我向平台索要发票，但平台表示无法开具。此外，我想有条件地申请延期还款。 | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.233 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 客户之前在豆豆钱借款，最近要求开具发票，收到两份发票，分别是陕西盛信泰华融资担保有限公司和维氏融资担保有限公司开具的，询问这两家公司开具的是利息发票还是担保费发... | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.230 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 我之前联系过你们，要求你们给我开发票。 | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.233 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 我在12月03日收到一张维氏融资担保有限公司开具的发票 | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.230 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 我有两个诉求：第一个是前期与平台合作已还清款项，但发票至今未开具。 | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.232 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 请帮我打印账单 | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.225 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |

### `light_card_cancel_refund` 轻享卡取消退费
- records：1；expr selected：0；not selected：1。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我要取消清享卡会员。 | C100 | `-` | `provide_vendor_contact`/no_select | 0.071 | `{"overdue_days": 45, "repayment_status": "overdue"}` |

### `loan_consultation` 贷款咨询
- records：42；expr selected：0；not selected：42。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我有可用额度119000元，需要立即申请借款，但申请时为什么会跳转到其他APP？ | C100 | `-` | `disbursement_timeline`/no_select | 0.056 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想咨询在你们平台是否可以再次借款 | C100 | `-` | `disbursement_timeline`/no_select | 0.056 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `loan_dispute_refund` 借款争议特殊场景退费
- records：6；expr selected：0；not selected：6。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 为什么我的手机号总是收到卡卡贷融的催收信息，借款人不是我 | C100 | `-` | `fraud_with_police_report`/no_select | 0.089 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我有一笔账单，当时点错了，我不需要，可以退还吗？ | C100 | `-` | `fraud_with_police_report`/no_select | 0.084 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `loan_termination` 贷款解约
- records：10；expr selected：0；not selected：10。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 关于豆豆钱借款，昨天在不知情的情况下直接到账了，我想把借款退回去。 | C100 | `-` | `retention_success`/no_select | 0.042 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在安逸花平台不小心申请了一笔100元的贷款，请问如何取消？ | C100 | `-` | `cannot_terminate`/no_select | 0.048 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `member_cancel` 取消会员
- records：42；expr selected：0；not selected：42。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我刚才给你们打过电话，因为下午四点多你们扣了我1800多元的会员费，我要取消会员。这是第二次发生类似情况，上次也自动扣过我的会员费。 | C100 | `-` | `unknown_source_deferred`/no_select | 0.022 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 麻烦取消我的会员，因为一直在扣款59元一个月。 | C100 | `-` | `unknown_source_deferred`/no_select | 0.022 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `member_consultation` 会员咨询
- records：25；expr selected：0；not selected：25。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 请帮我查看一下我的会员，为什么我没有续过费用，但每个月都扣款，每个月都扣？ | C100 | `-` | `benefit_change`/no_select | 0.032 | `{}` |
| 请帮我查询豆豆钱的会员费是多少钱。 | C100 | `-` | `benefit_change`/no_select | 0.033 | `{}` |

### `member_refund` 退会员费用
- records：32；expr selected：0；not selected：32。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 豆豆钱的会员为什么总是自动扣费 | C100 | `-` | `expired_or_used`/no_select | 0.038 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 你们是不是给我开通了几个会员并扣了我的钱？请查看一下。 | C100 | `-` | `expired_or_used`/no_select | 0.038 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `no_quota_issue` 无额度问题
- records：21；expr selected：0；not selected：21。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的额度早上还有50000，现在打开一看额度没有了，这是怎么回事？ | C100 | `-` | `no_quota_after_clearance`/no_select | 0.021 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我的额度是多少钱，现在被冻结了 | C102 | `-` | `ops_ticket`/no_select | 0.018 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |

### `other_certificate` 开具其他证明
- records：1；expr selected：0；not selected：1。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我有逾期，但上笔逾期时已向你们发送相关证明，刚才有人联系我，让我再联系你们，说上次发的证明已无效。 | C100 | `-` | `identify_order_and_certificate`/low_confidence | 0.176 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `overdue_negotiation` 协商还款
- records：659；expr selected：659；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 因为减免政策要有的。 | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.175 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想协商还款。 | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.175 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我这边钱还没到，我想打电话沟通一下，看看能不能办理延期还款。 | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.179 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我最近暂时还不上款，你们有什么政策能帮助我吗？ | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.174 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我目前还款压力太大，可能无法按时还款。 | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.175 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在你们这边有一笔欠款，我想协商还款，应该找谁？ | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.175 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `overpayment_refund` 客户对公转账出错退溢余
- records：10；expr selected：0；not selected：10。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 多扣的钱需要人工核实后退还 | C100 | `-` | `genuine_overpayment`/no_select | 0.014 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想查询我昨天按照你们提供的减免方案一次性转账后，款项是否已经入账，因为我的账单显示仍未还清。 | C100 | `-` | `incomplete_proof`/no_select | 0.018 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `post_loan_verification` 核实贷后信息
- records：109；expr selected：68；not selected：41。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 昨天有一个人用私人号码联系我，让我本金八折还款，我想确认他是否是你们的工作人员。 | C100 | `verify_staff` | `verify_staff`/low_confidence | 0.167 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "verification_type": "staff_id"}` |
| 我之前在你们平台有几千块钱逾期一直没还，刚刚多元调解中心给我打电话，说你们委托他来协商还款，我想问一下是否有这个事情。他给了我一个账户，叫维氏融资担保有限公司，... | C100 | `verify_account` | `verify_account`/low_confidence | 0.151 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "verification_type": "account"}` |
| 我想查询房管账号，核实还款账号。 | C100 | `verify_account` | `verify_account`/low_confidence | 0.162 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "verification_type": "account"}` |
| 今天有一笔可以减免的款项，需要核对对公账号是否正确。 | C100 | `verify_account` | `verify_account`/low_confidence | 0.169 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "verification_type": "account"}` |
| 我刚刚打电话联系过，是关于代偿的问题。 | C100 | `-` | `verify_account`/low_confidence | 0.145 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想核实代付协商方案是否真实：本金42700元，现在只需还34160元，还完后是否可以开具结清证明。 | C100 | `-` | `verify_account`/low_confidence | 0.148 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `premium_card_cancel` 取消优享卡
- records：4；expr selected：0；not selected：4。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我刚刚在借款时点击了优享卡，它显示要扣费500多元且每月自动续费，自动续费已开通。现在放款失败，但协议已开通，我想取消它。 | C100 | `-` | `retain_fail`/no_select | 0.027 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 我刚刚打开我的账户，发现上面有一个优享卡，30天后到期将扣款1645元，这个价格太高了，能给我取消吗？ | C100 | `-` | `no_record`/no_select | 0.026 | `{"overdue_days": 45, "repayment_status": "overdue"}` |

### `premium_card_inquiry` 优享卡咨询
- records：3；expr selected：0；not selected：3。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想咨询一下，我打开豆豆钱APP，看到有优享卡权益提示要付1000多块钱，这是什么意思？ | C100 | `-` | `not_purchased`/no_select | 0.045 | `{}` |
| 我有一笔贷款，但发现有一个优享卡，这是什么？ | C100 | `-` | `purchased_inquire`/no_select | 0.026 | `{}` |

### `premium_card_refund` 退优享卡费用
- records：2；expr selected：0；not selected：2。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 前两天办理了贷款，贷款金额为50000元。今天发现优享卡扣款2917元，我根本没有使用这个会员，为什么会扣款并要求退款？ | C100 | `-` | `refund_approved`/no_select | 0.017 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 我刚才借了一笔款，为什么优享卡费用1938元，要求立即退还给我 | C100 | `-` | `refund_approved`/no_select | 0.017 | `{"overdue_days": 45, "repayment_status": "overdue"}` |

### `quota_consultation` 额度咨询
- records：8；expr selected：0；not selected：8。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我现在看到有额度但无法提现，过几天我会使用，你们可以开通额度吗？ | C100 | `-` | `max_quota`/no_select | 0.016 | `{"loan_status": "active"}` |
| 我想咨询一下，按照我目前的情况，豆豆钱的额度大概能有多少。 | C100 | `-` | `max_quota`/no_select | 0.016 | `{"loan_status": "active"}` |

### `refund_value_added_service` 退增值服务费
- records：1；expr selected：0；not selected：1。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 这个保险续保了，怎么退？ | C100 | `-` | `tianchuang_credit_refund`/no_select | 0.059 | `{"overdue_days": 45, "repayment_status": "overdue"}` |

### `repayment_method_inquiry` 咨询还款方式
- records：196；expr selected：0；not selected：196。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的还款今天到期，你们一直用短信和电话提醒我，但我银行卡里有钱，准备主动还款时，系统显示还款日未到。 | C100 | `-` | `auto_deduction_detail`/no_select | 0.060 | `{}` |
| 请将验证码发给我，我要在微信金科公众平台还款。 | C100 | `-` | `manual_repayment_path`/no_select | 0.009 | `{}` |

### `repayment_result_query` 查询还款结果
- records：133；expr selected：0；not selected：133。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的钱上显示还有多少钱没还，今天已经还了5200元。 | C100 | `-` | `repayment_processing`/no_select | 0.009 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我已经扣款成功了，为什么平台上还是显示未到还款日？ | C100 | `-` | `repayment_success`/no_select | 0.048 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |

### `repayment_status_issue` 还款状态异常
- records：351；expr selected：0；not selected：351。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我已经提前还款了，但系统一直显示还款中，还在继续扣款。 | C100 | `-` | `failure_insufficient_balance_still_low`/no_select | 0.037 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想还款，但一直还款失败，刚才客服说我绑定的银行卡可能失效了，请帮我处理。 | C102 | `-` | `failure_card_limit_has_other_card`/no_select | 0.049 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |

### `stop_collection` 要求停催
- records：119；expr selected：105；not selected：14。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 请停止催收，包括发送短信和威胁。 | C100 | `normal_stop` | `normal_stop`/low_confidence | 0.221 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 我想请问，我上次还了一笔款，前几天催收是否可以暂停几天？ | C100 | `normal_stop` | `normal_stop`/low_confidence | 0.221 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 我想暂停催收，因为最近资金困难。 | C100 | `normal_stop` | `normal_stop`/low_confidence | 0.221 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 我之前办理的缓催今天到期了，我想再申请十天。 | C100 | `normal_stop` | `normal_stop`/low_confidence | 0.221 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 我想屏蔽我的紧急联系人和通讯录里的联系人。 | C100 | `-` | `normal_stop`/low_confidence | 0.207 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "third_party"}` |
| 我有一笔豆豆钱逾期了，催收电话很多，还发信息到联系人那边，希望帮我暂停一段时间。 | C100 | `-` | `normal_stop`/low_confidence | 0.206 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "third_party"}` |

### `stop_marketing` 停止营销
- records：10；expr selected：0；not selected：10。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我之前在你们公司有贷款，现在已经基本全部还清了，但还清后过了一段时间，你们公司一直发短信给我，说点击app最快五分钟放款，这是什么？ | C100 | `-` | `kakaday_is_our_product`/no_select | 0.048 | `{}` |
| 我要求你们帮我屏蔽掉我的联系人，因为现在还有人能收到短信。 | C100 | `-` | `kakaday_is_our_product`/no_select | 0.034 | `{}` |

### `value_added_service_inquiry` 增值服务咨询
- records：10；expr selected：0；not selected：10。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想查询我之前借款中是否包含还款无忧服务费 | C100 | `-` | `explain_tianchuang_credit`/no_select | 0.043 | `{}` |
| 我在豆豆钱借了一笔网贷，有一个月享卡的费用1700多元，这是什么费用？ | C100 | `-` | `explain_tianchuang_credit`/no_select | 0.043 | `{}` |
