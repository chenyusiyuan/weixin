# Mock 工具槽位后的 Branch 选择评估

- 生成时间：2026-04-27 17:25:05
- 数据源：`raw_test.jsonl`。
- 口径：跳过 skill 选择，使用真实 query 的 `gold_skill`；模拟已核身客户，执行 mock 工具，把工具结果和 query 抽取槽位合并后跑真实 `select_branch_variant`。
- 工具范围：`read-all`；persona 策略：`all`。
- `expr_selected` 是生产确定性分支；`semantic_candidate` 只是 hint 分支的离线文本候选，不等价于 LLM 真实选择。

## 总览

- 真实 query：2846；评估记录：8505。
- expr selected：3310；expr not selected：5195。
- semantic candidate：confident 0；low 4621；no_select 3884。

## Skill 汇总

| skill_id | 名称 | records | expr selected | expr top | semantic top |
|---|---|---:|---:|---|---|
| `account_cancellation` | 注销账户 | 195 | 0 | - | `escalate_to_tier2` 161；`doudouqian_self_service` 25；`cannot_cancel_outstanding` 9 |
| `bill_date_credit_impact` | 账单日还款是否影响征信 | 27 | 0 | - | `normal_repayment_credit` 15；`sufficient_balance_not_deducted_credit_concern` 3；`repayment_day_collection_call_credit_concern` 3；`overdue_credit_reporting` 3 |
| `bill_deduction_query` | 查询账单扣款情况 | 309 | 0 | - | `value_added_service_deduction_matched` 147；`bill_overdue` 59；`deduction_failed` 53；`no_internal_deduction_record` 18 |
| `cancel_credit_authorization` | 注销授信额度 | 33 | 33 | `self_operated_has_loan` 27；`non_self_operated` 3；`self_operated_can_cancel` 3 | `self_operated_can_cancel` 33 |
| `cancel_value_added_service` | 取消增值服务 | 30 | 0 | - | `pending_deduction_dispute` 10；`retention_success` 9；`cancel_before_charge` 6；`already_closed_no_charge` 5 |
| `card_rebinding` | 换绑银行卡 | 102 | 0 | - | `app_path_not_found` 90；`card_rebinding_failed` 6；`cannot_operate_for_customer` 6 |
| `clearance_certificate` | 开具结清证明 | 141 | 141 | `not_cleared` 90；`self_service` 51 | `not_cleared` 57；`self_service` 49；`agent_assist` 29；`official_issuance` 4 |
| `close_pre_reminder` | 关闭预提醒服务 | 12 | 3 | `proceed_close` 3 | `proceed_close` 12 |
| `collection_complaint` | 投诉催收 | 561 | 456 | `high_frequency` 324；`violent_collection` 60；`expose_contacts` 57；`bad_attitude` 15 | `high_frequency` 443；`expose_contacts` 98；`bad_attitude` 15；`violent_collection` 5 |
| `contract_retrieval` | 调取合同 | 66 | 66 | `tier1_overdue` 44；`tier1_active` 22 | `tier1_overdue` 63；`tier1_active` 3 |
| `credit_inquiry` | 征信问题咨询 | 117 | 36 | `overdue_impact` 33；`reporting_rules` 3 | `credit_inquiry_general` 65；`overdue_impact` 27；`credit_score` 23；`reporting_rules` 2 |
| `credit_modification` | 修改征信 | 60 | 60 | `self_operated` 57；`non_self_operated` 3 | `non_self_operated` 48；`self_operated` 12 |
| `deduction_issues` | 扣款相关问题咨询 | 51 | 0 | - | `amount_mismatch` 33；`next_deduction_date` 17；`duplicate_deduction` 1 |
| `disbursement_progress` | 放款进度查询 | 30 | 0 | - | `disbursing_status` 13；`delayed_disbursement` 8；`partner_disbursement` 7；`failed_disbursement` 2 |
| `early_deduction` | 未到还款日被提前扣款 | 21 | 0 | - | `misunderstanding_due_date` 6；`pre_deduction_sms_notice` 5；`product_rule_deduction` 4；`genuine_early_deduction` 3 |
| `early_loan_clearance` | 提前清贷需求 | 861 | 0 | - | `assist_clearance_no_tag` 861 |
| `fee_consultation_tier1` | 费用咨询（一线） | 96 | 0 | - | `guarantee_fee_legality` 96 |
| `fee_consultation_tier2` | 费用咨询（二线/高阶内诉） | 24 | 0 | - | `disguised_interest_objection` 12；`customer_accepts` 9；`compliance_document_request` 3 |
| `fee_detail_query` | 查询费用明细及综合费率 | 249 | 0 | - | `tier2_rate_query_by_order_age` 212；`irr_calculation_explanation` 12；`high_rate_objection` 12；`specific_period_query` 8 |
| `fee_refund_status` | 退费未到账情况咨询 | 27 | 0 | - | `refund_completed` 25；`refund_remitted` 1；`refund_processing` 1 |
| `fee_refund_tier1` | 要求退费（一线） | 75 | 0 | - | `refund_not_eligible` 75 |
| `fee_refund_tier2` | 要求退费（二线/高阶内诉） | 15 | 0 | - | `membership_offset` 7；`customer_accepts_proposal` 6；`full_guarantee_fee_refund_objection` 1；`guarantee_fee_or_over_24_negotiation` 1 |
| `invoice_issuance` | 发票开具 | 18 | 18 | `doudou_self_service` 18 | `doudou_self_service` 18 |
| `light_card_cancel_refund` | 轻享卡取消退费 | 3 | 0 | - | `provide_vendor_contact` 2；`guide_self_cancel_renewal` 1 |
| `loan_consultation` | 贷款咨询 | 126 | 0 | - | `disbursement_timeline` 123；`loan_nature_and_lender_explanation` 2；`approved_disbursement_timeline` 1 |
| `loan_dispute_refund` | 借款争议特殊场景退费 | 18 | 0 | - | `fraud_with_police_report` 18 |
| `loan_termination` | 贷款解约 | 30 | 0 | - | `cannot_terminate` 25；`retention_success` 3；`ops_ticket_for_termination` 2 |
| `member_cancel` | 取消会员 | 126 | 0 | - | `unknown_source_deferred` 48；`not_needed_deferred` 39；`no_record` 33；`retain_fail` 6 |
| `member_consultation` | 会员咨询 | 75 | 0 | - | `benefit_change` 35；`compliance_question` 22；`legality_question` 17；`quota_increase_fail` 1 |
| `member_refund` | 退会员费用 | 96 | 0 | - | `active_benefits` 43；`expired_or_used` 29；`music_fitness_used` 23；`escalate_to_supervisor` 1 |
| `no_quota_issue` | 无额度问题 | 63 | 0 | - | `marketing_invited_no_quota` 24；`no_quota_after_clearance` 16；`ops_ticket` 9；`reserved_loan` 6 |
| `other_certificate` | 开具其他证明 | 3 | 0 | - | `identify_order_and_certificate` 3 |
| `overdue_negotiation` | 协商还款 | 1977 | 1977 | `mid_overdue` 659；`pre_overdue` 659；`early_overdue` 659 | `early_overdue` 1263；`pre_overdue` 698；`mid_overdue` 16 |
| `overpayment_refund` | 客户对公转账出错退溢余 | 30 | 0 | - | `transfer_verified_full_match` 8；`incomplete_proof` 7；`genuine_overpayment` 6；`not_our_corporate_account` 5 |
| `post_loan_verification` | 核实贷后信息 | 327 | 204 | `verify_account` 147；`verify_staff` 42；`verify_institution` 15 | `verify_account` 255；`verify_staff` 50；`verify_institution` 22 |
| `premium_card_cancel` | 取消优享卡 | 12 | 0 | - | `no_record` 6；`retain_fail` 3；`accidental_purchase` 3 |
| `premium_card_inquiry` | 优享卡咨询 | 9 | 0 | - | `not_purchased` 5；`purchased_inquire` 4 |
| `premium_card_refund` | 退优享卡费用 | 6 | 0 | - | `refund_approved` 4；`no_risk_refusal` 2 |
| `quota_consultation` | 额度咨询 | 24 | 0 | - | `max_quota` 24 |
| `refund_value_added_service` | 退增值服务费 | 3 | 0 | - | `zhonghui_insurance_refund` 2；`tianchuang_credit_refund` 1 |
| `repayment_method_inquiry` | 咨询还款方式 | 588 | 0 | - | `auto_deduction_detail` 294；`manual_repayment_path` 294 |
| `repayment_result_query` | 查询还款结果 | 399 | 0 | - | `repayment_processing` 282；`repayment_success` 102；`repayment_delayed` 15 |
| `repayment_status_issue` | 还款状态异常 | 1053 | 0 | - | `failure_insufficient_balance_still_low` 328；`failure_bank_card_contract` 320；`failure_limit_corporate_payment` 138；`failure_channel_corporate_payment` 115 |
| `stop_collection` | 要求停催 | 357 | 316 | `normal_stop` 278；`escalate_stop` 30；`supervisor_stop` 6；`ai_collection_early` 2 | `normal_stop` 264；`escalate_stop` 93 |
| `stop_marketing` | 停止营销 | 30 | 0 | - | `kakaday_is_our_product` 25；`unregistered_received_marketing` 3；`deactivated_received_marketing` 2 |
| `value_added_service_inquiry` | 增值服务咨询 | 30 | 0 | - | `explain_tianchuang_credit` 30 |

## 抽样明细

### `account_cancellation` 注销账户
- records：195；expr selected：0；not selected：195。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想关闭授信额度并注销账户。 | C100 | `-` | `escalate_to_tier2`/no_select | 0.046 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想关闭授信额度并注销账户。 | C101 | `-` | `doudouqian_self_service`/no_select | 0.037 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `bill_date_credit_impact` 账单日还款是否影响征信
- records：27；expr selected：0；not selected：27。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想咨询豆豆钱逾期一天是否会影响信用记录。 | C100 | `-` | `existing_overdue_credit_repair`/no_select | 0.011 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想咨询豆豆钱逾期一天是否会影响信用记录。 | C101 | `-` | `normal_repayment_credit`/no_select | 0.041 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `bill_deduction_query` 查询账单扣款情况
- records：309；expr selected：0；not selected：309。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 今天早上众安保险怎么又从我这边扣款了？扣了274元。 | C100 | `-` | `deduction_pending`/no_select | 0.014 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 今天早上众安保险怎么又从我这边扣款了？扣了274元。 | C101 | `-` | `deduction_failed`/no_select | 0.020 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `cancel_credit_authorization` 注销授信额度
- records：33；expr selected：33；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想提前关闭你们平台的授信额度。 | C100 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.258 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我想提前关闭你们平台的授信额度。 | C101 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.262 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "institution_type": "self_operated"}` |
| 我想提前关闭你们平台的授信额度。 | C102 | `self_operated_has_loan` | `self_operated_can_cancel`/low_confidence | 0.261 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我早上在你们的APP里有一个网络贷款的申请，但你们的APP把我推给了一家第三方中介公司，他们早上给我打了几个电话进行线上分析。我现在要求收回我在APP的所有个人... | C100 | `non_self_operated` | `self_operated_can_cancel`/low_confidence | 0.253 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "non_self_operated"}` |
| 我早上在你们的APP里有一个网络贷款的申请，但你们的APP把我推给了一家第三方中介公司，他们早上给我打了几个电话进行线上分析。我现在要求收回我在APP的所有个人... | C101 | `non_self_operated` | `self_operated_can_cancel`/low_confidence | 0.257 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "institution_type": "non_self_operated"}` |
| 我早上在你们的APP里有一个网络贷款的申请，但你们的APP把我推给了一家第三方中介公司，他们早上给我打了几个电话进行线上分析。我现在要求收回我在APP的所有个人... | C102 | `non_self_operated` | `self_operated_can_cancel`/low_confidence | 0.259 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "institution_type": "non_self_operated"}` |

### `cancel_value_added_service` 取消增值服务
- records：30；expr selected：0；not selected：30。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想问一下，你们这个平台有没有一个可以赚钱的卡，能取消吗？ | C100 | `-` | `retention_success`/no_select | 0.011 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 我想问一下，你们这个平台有没有一个可以赚钱的卡，能取消吗？ | C101 | `-` | `pending_deduction_dispute`/no_select | 0.033 | `{"overdue_days": 0, "repayment_status": "normal"}` |

### `card_rebinding` 换绑银行卡
- records：102；expr selected：0；not selected：102。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我刚才还款时，换卡还款操作不了，出现了问题。 | C100 | `-` | `card_rebinding_failed`/no_select | 0.007 | `{}` |
| 我刚才还款时，换卡还款操作不了，出现了问题。 | C101 | `-` | `card_rebinding_failed`/no_select | 0.007 | `{}` |

### `clearance_certificate` 开具结清证明
- records：141；expr selected：141；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我在微信卡卡贷借款，已经结清了，工作人员让我打这个电话开具结清证明。 | C100 | `self_service` | `self_service`/low_confidence | 0.226 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在微信卡卡贷借款，已经结清了，工作人员让我打这个电话开具结清证明。 | C101 | `self_service` | `self_service`/low_confidence | 0.228 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我在微信卡卡贷借款，已经结清了，工作人员让我打这个电话开具结清证明。 | C102 | `self_service` | `self_service`/low_confidence | 0.228 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在平台有一笔借款已经还清，想要开具结清证明。 | C100 | `self_service` | `self_service`/low_confidence | 0.226 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我在平台有一笔借款已经还清，想要开具结清证明。 | C101 | `self_service` | `self_service`/low_confidence | 0.229 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我在平台有一笔借款已经还清，想要开具结清证明。 | C102 | `self_service` | `self_service`/low_confidence | 0.228 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |

### `close_pre_reminder` 关闭预提醒服务
- records：12；expr selected：3；not selected：9。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 请在我还款前，先不要给我打电话。 | C100 | `proceed_close` | `proceed_close`/low_confidence | 0.225 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 请在我还款前，先不要给我打电话。 | C101 | `proceed_close` | `proceed_close`/low_confidence | 0.225 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 请在我还款前，先不要给我打电话。 | C102 | `proceed_close` | `proceed_close`/low_confidence | 0.226 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |
| 在还款日之前，为什么会有电话打来？ | C100 | `-` | `proceed_close`/low_confidence | 0.225 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 在还款日之前，为什么会有电话打来？ | C101 | `-` | `proceed_close`/low_confidence | 0.225 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `collection_complaint` 投诉催收
- records：561；expr selected：456；not selected：105。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的账单已经处理完了，为什么还在打电话？ | C100 | `high_frequency` | `high_frequency`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "frequency"}` |
| 我的账单已经处理完了，为什么还在打电话？ | C101 | `high_frequency` | `high_frequency`/low_confidence | 0.173 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "complaint_type": "frequency"}` |
| 我的账单已经处理完了，为什么还在打电话？ | C102 | `high_frequency` | `high_frequency`/low_confidence | 0.168 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "frequency"}` |
| 我今天1:50左右，也遇到了同样的情况，电话响一声就挂断了 | C100 | `high_frequency` | `high_frequency`/low_confidence | 0.194 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "complaint_type": "frequency"}` |
| 为什么平台在催我还款，但我已经没有借款了？ | C100 | `-` | `high_frequency`/low_confidence | 0.154 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 为什么平台在催我还款，但我已经没有借款了？ | C101 | `-` | `high_frequency`/low_confidence | 0.125 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `contract_retrieval` 调取合同
- records：66；expr selected：66；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想查询我的紧急联系人信息 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.191 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想查询我的紧急联系人信息 | C101 | `tier1_active` | `tier1_overdue`/low_confidence | 0.190 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我想查询我的紧急联系人信息 | C102 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.192 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |
| 我需要将我在豆豆钱平台的所有借款合同以邮箱形式发送给我。 | C100 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.190 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我需要将我在豆豆钱平台的所有借款合同以邮箱形式发送给我。 | C101 | `tier1_active` | `tier1_overdue`/low_confidence | 0.189 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我需要将我在豆豆钱平台的所有借款合同以邮箱形式发送给我。 | C102 | `tier1_overdue` | `tier1_overdue`/low_confidence | 0.192 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |

### `credit_inquiry` 征信问题咨询
- records：117；expr selected：36；not selected：81。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的征信报告显示上海维信汇智（你们公司）有一笔约300元的逾期记录，我想消除这个逾期记录，但找不到还款渠道。 | C100 | `overdue_impact` | `overdue_impact`/low_confidence | 0.193 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "overdue_impact"}` |
| 我的征信报告显示上海维信汇智（你们公司）有一笔约300元的逾期记录，我想消除这个逾期记录，但找不到还款渠道。 | C101 | `overdue_impact` | `overdue_impact`/low_confidence | 0.188 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "inquiry_type": "overdue_impact"}` |
| 我的征信报告显示上海维信汇智（你们公司）有一笔约300元的逾期记录，我想消除这个逾期记录，但找不到还款渠道。 | C102 | `overdue_impact` | `credit_inquiry_general`/low_confidence | 0.188 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "overdue_impact"}` |
| 如何处理因还款日期问题导致的逾期记录？ | C100 | `overdue_impact` | `overdue_impact`/low_confidence | 0.190 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "inquiry_type": "overdue_impact"}` |
| 咨询朋友在贵公司借款后延期，是否会向他人发送信息或拨打电话。 | C100 | `-` | `credit_inquiry_general`/low_confidence | 0.131 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 咨询朋友在贵公司借款后延期，是否会向他人发送信息或拨打电话。 | C101 | `-` | `credit_score`/low_confidence | 0.118 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `credit_modification` 修改征信
- records：60；expr selected：60；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的钱包逾期了，我想一次性还清，但我的征信报告显示是关注状态，我想解除关注状态。 | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.205 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我的钱包逾期了，我想一次性还清，但我的征信报告显示是关注状态，我想解除关注状态。 | C101 | `self_operated` | `non_self_operated`/low_confidence | 0.204 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "institution_type": "self_operated"}` |
| 我的钱包逾期了，我想一次性还清，但我的征信报告显示是关注状态，我想解除关注状态。 | C102 | `self_operated` | `self_operated`/low_confidence | 0.204 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我在2025年2月6日有一笔在你们平台的借贷，额度28000元，一直在还款，现已还10期，从未逾期。但有其他平台打电话和发短信说我逾期了，声称你们平台从其他平台... | C100 | `self_operated` | `non_self_operated`/low_confidence | 0.207 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |
| 我在2025年2月6日有一笔在你们平台的借贷，额度28000元，一直在还款，现已还10期，从未逾期。但有其他平台打电话和发短信说我逾期了，声称你们平台从其他平台... | C101 | `self_operated` | `non_self_operated`/low_confidence | 0.206 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "institution_type": "self_operated"}` |
| 我在2025年2月6日有一笔在你们平台的借贷，额度28000元，一直在还款，现已还10期，从未逾期。但有其他平台打电话和发短信说我逾期了，声称你们平台从其他平台... | C102 | `self_operated` | `non_self_operated`/low_confidence | 0.202 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "institution_type": "self_operated"}` |

### `deduction_issues` 扣款相关问题咨询
- records：51；expr selected：0；not selected：51。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想咨询一下，我的优惠券会自动扣款吗？ | C100 | `-` | `amount_mismatch`/no_select | 0.059 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想咨询一下，我的优惠券会自动扣款吗？ | C101 | `-` | `next_deduction_date`/no_select | 0.022 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `disbursement_progress` 放款进度查询
- records：30；expr selected：0；not selected：30。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的App上微信卡卡贷有2400元、2万元、4500万元、500元，但我点击普通通道后显示放款失败。 | C100 | `-` | `disbursing_status`/no_select | 0.046 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我的App上微信卡卡贷有2400元、2万元、4500万元、500元，但我点击普通通道后显示放款失败。 | C101 | `-` | `failed_disbursement`/no_select | 0.038 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `early_deduction` 未到还款日被提前扣款
- records：21；expr selected：0；not selected：21。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想问一下，我的银行卡今天被豆豆钱扣款了，但我的账单日是7号，为什么会提前扣款？ | C100 | `-` | `misunderstanding_due_date`/no_select | 0.032 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想问一下，我的银行卡今天被豆豆钱扣款了，但我的账单日是7号，为什么会提前扣款？ | C101 | `-` | `misunderstanding_due_date`/no_select | 0.040 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `early_loan_clearance` 提前清贷需求
- records：861；expr selected：0；not selected：861。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想提前还款。 | C100 | `-` | `assist_clearance_no_tag`/low_confidence | 0.141 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想提前还款。 | C101 | `-` | `assist_clearance_no_tag`/low_confidence | 0.141 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_consultation_tier1` 费用咨询（一线）
- records：96；expr selected：0；not selected：96。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我以前在你们平台借过钱，现在借不了钱了，为什么还在扣费？ | C100 | `-` | `guarantee_fee_legality`/no_select | 0.095 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我以前在你们平台借过钱，现在借不了钱了，为什么还在扣费？ | C101 | `-` | `guarantee_fee_legality`/no_select | 0.084 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_consultation_tier2` 费用咨询（二线/高阶内诉）
- records：24；expr selected：0；not selected：24。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我现在要全额还款，但你们的担保费不合理，我已经投诉了，你们到现在没给我回电话。 | C100 | `-` | `disguised_interest_objection`/no_select | 0.007 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我现在要全额还款，但你们的担保费不合理，我已经投诉了，你们到现在没给我回电话。 | C101 | `-` | `disguised_interest_objection`/no_select | 0.007 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_detail_query` 查询费用明细及综合费率
- records：249；expr selected：0；not selected：249。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 为什么我的账户里有一个叫东富的条目？ | C100 | `-` | `tier2_rate_query_by_order_age`/no_select | 0.011 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 为什么我的账户里有一个叫东富的条目？ | C101 | `-` | `tier2_rate_query_by_order_age`/no_select | 0.016 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_refund_status` 退费未到账情况咨询
- records：27；expr selected：0；not selected：27。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我之前还款的钱是朋友帮我支付的，客服说会退给我，为什么到现在还没到账？ | C100 | `-` | `refund_completed`/no_select | 0.028 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我之前还款的钱是朋友帮我支付的，客服说会退给我，为什么到现在还没到账？ | C101 | `-` | `refund_completed`/no_select | 0.056 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_refund_tier1` 要求退费（一线）
- records：75；expr selected：0；not selected：75。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想问一下，你们这边能给帮忙减免一下利息吗？ | C100 | `-` | `refund_not_eligible`/low_confidence | 0.137 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想问一下，你们这边能给帮忙减免一下利息吗？ | C101 | `-` | `refund_not_eligible`/low_confidence | 0.140 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `fee_refund_tier2` 要求退费（二线/高阶内诉）
- records：15；expr selected：0；not selected：15。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我联系了您提供的电话，对方表示无法退款，请问该如何处理？ | C100 | `-` | `customer_accepts_proposal`/no_select | 0.037 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我联系了您提供的电话，对方表示无法退款，请问该如何处理？ | C101 | `-` | `membership_offset`/no_select | 0.033 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `invoice_issuance` 发票开具
- records：18；expr selected：18；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我有两笔借款，其中一笔是最后一期。我向平台索要发票，但平台表示无法开具。此外，我想有条件地申请延期还款。 | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.233 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 我有两笔借款，其中一笔是最后一期。我向平台索要发票，但平台表示无法开具。此外，我想有条件地申请延期还款。 | C101 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.234 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "platform": "doudouqian"}` |
| 我有两笔借款，其中一笔是最后一期。我向平台索要发票，但平台表示无法开具。此外，我想有条件地申请延期还款。 | C102 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.236 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 客户之前在豆豆钱借款，最近要求开具发票，收到两份发票，分别是陕西盛信泰华融资担保有限公司和维氏融资担保有限公司开具的，询问这两家公司开具的是利息发票还是担保费发... | C100 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.230 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |
| 客户之前在豆豆钱借款，最近要求开具发票，收到两份发票，分别是陕西盛信泰华融资担保有限公司和维氏融资担保有限公司开具的，询问这两家公司开具的是利息发票还是担保费发... | C101 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.231 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "platform": "doudouqian"}` |
| 客户之前在豆豆钱借款，最近要求开具发票，收到两份发票，分别是陕西盛信泰华融资担保有限公司和维氏融资担保有限公司开具的，询问这两家公司开具的是利息发票还是担保费发... | C102 | `doudou_self_service` | `doudou_self_service`/low_confidence | 0.233 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "platform": "doudouqian"}` |

### `light_card_cancel_refund` 轻享卡取消退费
- records：3；expr selected：0；not selected：3。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我要取消清享卡会员。 | C100 | `-` | `provide_vendor_contact`/no_select | 0.071 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 我要取消清享卡会员。 | C101 | `-` | `provide_vendor_contact`/no_select | 0.080 | `{"overdue_days": 0, "repayment_status": "normal"}` |

### `loan_consultation` 贷款咨询
- records：126；expr selected：0；not selected：126。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我有可用额度119000元，需要立即申请借款，但申请时为什么会跳转到其他APP？ | C100 | `-` | `disbursement_timeline`/no_select | 0.056 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我有可用额度119000元，需要立即申请借款，但申请时为什么会跳转到其他APP？ | C101 | `-` | `disbursement_timeline`/no_select | 0.041 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `loan_dispute_refund` 借款争议特殊场景退费
- records：18；expr selected：0；not selected：18。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 为什么我的手机号总是收到卡卡贷融的催收信息，借款人不是我 | C100 | `-` | `fraud_with_police_report`/no_select | 0.089 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 为什么我的手机号总是收到卡卡贷融的催收信息，借款人不是我 | C101 | `-` | `fraud_with_police_report`/no_select | 0.084 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `loan_termination` 贷款解约
- records：30；expr selected：0；not selected：30。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 关于豆豆钱借款，昨天在不知情的情况下直接到账了，我想把借款退回去。 | C100 | `-` | `retention_success`/no_select | 0.042 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 关于豆豆钱借款，昨天在不知情的情况下直接到账了，我想把借款退回去。 | C101 | `-` | `cannot_terminate`/no_select | 0.028 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `member_cancel` 取消会员
- records：126；expr selected：0；not selected：126。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我刚才给你们打过电话，因为下午四点多你们扣了我1800多元的会员费，我要取消会员。这是第二次发生类似情况，上次也自动扣过我的会员费。 | C100 | `-` | `unknown_source_deferred`/no_select | 0.022 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我刚才给你们打过电话，因为下午四点多你们扣了我1800多元的会员费，我要取消会员。这是第二次发生类似情况，上次也自动扣过我的会员费。 | C101 | `-` | `unknown_source_deferred`/no_select | 0.022 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `member_consultation` 会员咨询
- records：75；expr selected：0；not selected：75。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 请帮我查看一下我的会员，为什么我没有续过费用，但每个月都扣款，每个月都扣？ | C100 | `-` | `benefit_change`/no_select | 0.032 | `{}` |
| 请帮我查看一下我的会员，为什么我没有续过费用，但每个月都扣款，每个月都扣？ | C101 | `-` | `benefit_change`/no_select | 0.014 | `{}` |

### `member_refund` 退会员费用
- records：96；expr selected：0；not selected：96。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 豆豆钱的会员为什么总是自动扣费 | C100 | `-` | `expired_or_used`/no_select | 0.038 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 豆豆钱的会员为什么总是自动扣费 | C101 | `-` | `active_benefits`/no_select | 0.036 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `no_quota_issue` 无额度问题
- records：63；expr selected：0；not selected：63。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的额度早上还有50000，现在打开一看额度没有了，这是怎么回事？ | C100 | `-` | `no_quota_after_clearance`/no_select | 0.021 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我的额度早上还有50000，现在打开一看额度没有了，这是怎么回事？ | C101 | `-` | `marketing_invited_no_quota`/no_select | 0.035 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `other_certificate` 开具其他证明
- records：3；expr selected：0；not selected：3。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我有逾期，但上笔逾期时已向你们发送相关证明，刚才有人联系我，让我再联系你们，说上次发的证明已无效。 | C100 | `-` | `identify_order_and_certificate`/low_confidence | 0.176 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我有逾期，但上笔逾期时已向你们发送相关证明，刚才有人联系我，让我再联系你们，说上次发的证明已无效。 | C101 | `-` | `identify_order_and_certificate`/low_confidence | 0.179 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `overdue_negotiation` 协商还款
- records：1977；expr selected：1977；not selected：0。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 因为减免政策要有的。 | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.175 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 因为减免政策要有的。 | C101 | `pre_overdue` | `early_overdue`/low_confidence | 0.123 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 因为减免政策要有的。 | C102 | `early_overdue` | `early_overdue`/low_confidence | 0.136 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想协商还款。 | C100 | `mid_overdue` | `pre_overdue`/low_confidence | 0.175 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我想协商还款。 | C101 | `pre_overdue` | `early_overdue`/low_confidence | 0.124 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |
| 我想协商还款。 | C102 | `early_overdue` | `early_overdue`/low_confidence | 0.136 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue"}` |

### `overpayment_refund` 客户对公转账出错退溢余
- records：30；expr selected：0；not selected：30。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 多扣的钱需要人工核实后退还 | C100 | `-` | `genuine_overpayment`/no_select | 0.014 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 多扣的钱需要人工核实后退还 | C101 | `-` | `genuine_overpayment`/no_select | 0.014 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `post_loan_verification` 核实贷后信息
- records：327；expr selected：204；not selected：123。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 昨天有一个人用私人号码联系我，让我本金八折还款，我想确认他是否是你们的工作人员。 | C100 | `verify_staff` | `verify_staff`/low_confidence | 0.167 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "verification_type": "staff_id"}` |
| 昨天有一个人用私人号码联系我，让我本金八折还款，我想确认他是否是你们的工作人员。 | C101 | `verify_staff` | `verify_staff`/low_confidence | 0.171 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "verification_type": "staff_id"}` |
| 昨天有一个人用私人号码联系我，让我本金八折还款，我想确认他是否是你们的工作人员。 | C102 | `verify_staff` | `verify_staff`/low_confidence | 0.177 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "verification_type": "staff_id"}` |
| 我之前在你们平台有几千块钱逾期一直没还，刚刚多元调解中心给我打电话，说你们委托他来协商还款，我想问一下是否有这个事情。他给了我一个账户，叫维氏融资担保有限公司，... | C100 | `verify_account` | `verify_account`/low_confidence | 0.151 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "verification_type": "account"}` |
| 我刚刚打电话联系过，是关于代偿的问题。 | C100 | `-` | `verify_account`/low_confidence | 0.145 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我刚刚打电话联系过，是关于代偿的问题。 | C101 | `-` | `verify_account`/low_confidence | 0.142 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `premium_card_cancel` 取消优享卡
- records：12；expr selected：0；not selected：12。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我刚刚在借款时点击了优享卡，它显示要扣费500多元且每月自动续费，自动续费已开通。现在放款失败，但协议已开通，我想取消它。 | C100 | `-` | `retain_fail`/no_select | 0.027 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 我刚刚在借款时点击了优享卡，它显示要扣费500多元且每月自动续费，自动续费已开通。现在放款失败，但协议已开通，我想取消它。 | C101 | `-` | `retain_fail`/no_select | 0.027 | `{"overdue_days": 0, "repayment_status": "normal"}` |

### `premium_card_inquiry` 优享卡咨询
- records：9；expr selected：0；not selected：9。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想咨询一下，我打开豆豆钱APP，看到有优享卡权益提示要付1000多块钱，这是什么意思？ | C100 | `-` | `not_purchased`/no_select | 0.045 | `{}` |
| 我想咨询一下，我打开豆豆钱APP，看到有优享卡权益提示要付1000多块钱，这是什么意思？ | C101 | `-` | `not_purchased`/no_select | 0.045 | `{}` |

### `premium_card_refund` 退优享卡费用
- records：6；expr selected：0；not selected：6。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 前两天办理了贷款，贷款金额为50000元。今天发现优享卡扣款2917元，我根本没有使用这个会员，为什么会扣款并要求退款？ | C100 | `-` | `refund_approved`/no_select | 0.017 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 前两天办理了贷款，贷款金额为50000元。今天发现优享卡扣款2917元，我根本没有使用这个会员，为什么会扣款并要求退款？ | C101 | `-` | `refund_approved`/no_select | 0.011 | `{"overdue_days": 0, "repayment_status": "normal"}` |

### `quota_consultation` 额度咨询
- records：24；expr selected：0；not selected：24。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我现在看到有额度但无法提现，过几天我会使用，你们可以开通额度吗？ | C100 | `-` | `max_quota`/no_select | 0.016 | `{"loan_status": "active"}` |
| 我现在看到有额度但无法提现，过几天我会使用，你们可以开通额度吗？ | C101 | `-` | `max_quota`/no_select | 0.024 | `{"loan_status": "active"}` |

### `refund_value_added_service` 退增值服务费
- records：3；expr selected：0；not selected：3。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 这个保险续保了，怎么退？ | C100 | `-` | `tianchuang_credit_refund`/no_select | 0.059 | `{"overdue_days": 45, "repayment_status": "overdue"}` |
| 这个保险续保了，怎么退？ | C101 | `-` | `zhonghui_insurance_refund`/no_select | 0.065 | `{"overdue_days": 0, "repayment_status": "normal"}` |

### `repayment_method_inquiry` 咨询还款方式
- records：588；expr selected：0；not selected：588。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的还款今天到期，你们一直用短信和电话提醒我，但我银行卡里有钱，准备主动还款时，系统显示还款日未到。 | C100 | `-` | `auto_deduction_detail`/no_select | 0.060 | `{}` |
| 我的还款今天到期，你们一直用短信和电话提醒我，但我银行卡里有钱，准备主动还款时，系统显示还款日未到。 | C101 | `-` | `auto_deduction_detail`/no_select | 0.060 | `{}` |

### `repayment_result_query` 查询还款结果
- records：399；expr selected：0；not selected：399。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我的钱上显示还有多少钱没还，今天已经还了5200元。 | C100 | `-` | `repayment_processing`/no_select | 0.009 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我的钱上显示还有多少钱没还，今天已经还了5200元。 | C101 | `-` | `repayment_processing`/no_select | 0.018 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `repayment_status_issue` 还款状态异常
- records：1053；expr selected：0；not selected：1053。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我已经提前还款了，但系统一直显示还款中，还在继续扣款。 | C100 | `-` | `failure_insufficient_balance_still_low`/no_select | 0.037 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue"}` |
| 我已经提前还款了，但系统一直显示还款中，还在继续扣款。 | C101 | `-` | `update_in_progress`/no_select | 0.026 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal"}` |

### `stop_collection` 要求停催
- records：357；expr selected：316；not selected：41。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 请停止催收，包括发送短信和威胁。 | C100 | `normal_stop` | `normal_stop`/low_confidence | 0.221 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 请停止催收，包括发送短信和威胁。 | C101 | `normal_stop` | `normal_stop`/low_confidence | 0.207 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "stop_days_requested": 15, "target": "self"}` |
| 请停止催收，包括发送短信和威胁。 | C102 | `normal_stop` | `escalate_stop`/low_confidence | 0.201 | `{"overdue_days": 12, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 我想请问，我上次还了一笔款，前几天催收是否可以暂停几天？ | C100 | `normal_stop` | `normal_stop`/low_confidence | 0.221 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "self"}` |
| 我想屏蔽我的紧急联系人和通讯录里的联系人。 | C100 | `-` | `normal_stop`/low_confidence | 0.207 | `{"overdue_days": 45, "loan_status": "active", "repayment_status": "overdue", "stop_days_requested": 15, "target": "third_party"}` |
| 我想屏蔽我的紧急联系人和通讯录里的联系人。 | C101 | `-` | `escalate_stop`/low_confidence | 0.196 | `{"overdue_days": 0, "loan_status": "active", "repayment_status": "normal", "stop_days_requested": 15, "target": "third_party"}` |

### `stop_marketing` 停止营销
- records：30；expr selected：0；not selected：30。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我之前在你们公司有贷款，现在已经基本全部还清了，但还清后过了一段时间，你们公司一直发短信给我，说点击app最快五分钟放款，这是什么？ | C100 | `-` | `kakaday_is_our_product`/no_select | 0.048 | `{}` |
| 我之前在你们公司有贷款，现在已经基本全部还清了，但还清后过了一段时间，你们公司一直发短信给我，说点击app最快五分钟放款，这是什么？ | C101 | `-` | `kakaday_is_our_product`/no_select | 0.049 | `{}` |

### `value_added_service_inquiry` 增值服务咨询
- records：30；expr selected：0；not selected：30。
| query | persona | expr selected | semantic candidate | score | key slots |
|---|---|---|---|---:|---|
| 我想查询我之前借款中是否包含还款无忧服务费 | C100 | `-` | `explain_tianchuang_credit`/no_select | 0.043 | `{}` |
| 我想查询我之前借款中是否包含还款无忧服务费 | C101 | `-` | `explain_tianchuang_credit`/no_select | 0.040 | `{}` |
