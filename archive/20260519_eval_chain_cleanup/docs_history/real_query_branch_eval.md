# 真实 Query Branch 选择效果抽样

- 生成时间：2026-04-27 17:19:15
- 数据源：`raw_test.jsonl`；使用 gold_skill 固定 skill，只评估 branch 选择效果。
- gold 置信度过滤：`confidence >= 0.0`。
- 说明：真实数据没有 gold branch 标签，因此这里看的是分支可分性/命中清晰度，不是最终准确率。

## 总览

- 使用真实 query：2846 条。
- 有分支 skill：49 个；其中 46 个在 golden 中有真实 query。
- 参与 branch 评估 query：2835 条。
- confident：35；low_confidence：413；no_select：2387。
- 有分支但本次 golden 无真实样本：`deactivated_customer_service`, `remote_disbursement`, `special_account_cancellation`

## Skill 汇总

| skill_id | 名称 | branch | real query | confident | low | no_select | top branches |
|---|---|---:|---:|---:|---:|---:|---|
| `account_cancellation` | 注销账户 | 4 | 65 | 12 | 21 | 32 | `doudouqian_self_service` 50；`cannot_cancel_outstanding` 14；`kakaday_manual_cancel` 1 |
| `bill_date_credit_impact` | 账单日还款是否影响征信 | 8 | 9 | 0 | 3 | 6 | `normal_repayment_credit` 2；`repayment_day_failed_sms_credit_concern` 2；`repayment_day_collection_call_credit_concern` 2；`existing_overdue_credit_repair` 1 |
| `bill_deduction_query` | 查询账单扣款情况 | 9 | 103 | 0 | 32 | 71 | `bill_deduction_amount_matched` 40；`no_internal_deduction_record` 20；`unknown_external_deduction_entity` 15；`deduction_failed` 9 |
| `cancel_credit_authorization` | 注销授信额度 | 4 | 11 | 0 | 4 | 7 | `explain_difference` 8；`self_operated_has_loan` 2；`self_operated_can_cancel` 1 |
| `cancel_value_added_service` | 取消增值服务 | 5 | 10 | 0 | 0 | 10 | `cancel_before_charge` 6；`already_closed_no_charge` 4 |
| `card_rebinding` | 换绑银行卡 | 3 | 34 | 1 | 8 | 25 | `app_path_not_found` 28；`cannot_operate_for_customer` 4；`card_rebinding_failed` 2 |
| `clearance_certificate` | 开具结清证明 | 6 | 47 | 0 | 6 | 41 | `not_cleared` 36；`identify_target_order` 7；`agent_assist` 3；`system_failed` 1 |
| `close_pre_reminder` | 关闭预提醒服务 | 3 | 4 | 0 | 0 | 4 | `multi_order` 3；`no_ivr_record` 1 |
| `collection_complaint` | 投诉催收 | 4 | 187 | 1 | 4 | 182 | `high_frequency` 80；`bad_attitude` 58；`violent_collection` 36；`expose_contacts` 13 |
| `contract_retrieval` | 调取合同 | 8 | 22 | 0 | 10 | 12 | `tier1_active` 15；`all_contracts_request` 4；`cancelled_retention_dispute` 2；`tier2_cleared` 1 |
| `credit_inquiry` | 征信问题咨询 | 18 | 39 | 0 | 17 | 22 | `no_credit_report_sms_notice` 9；`guarantee_compensation_reporting` 5；`cannot_delete_valid_credit_record` 5；`customer_refuses_credit_evidence` 4 |
| `credit_modification` | 修改征信 | 7 | 20 | 0 | 2 | 18 | `clarify_institution_and_record` 7；`own_fault` 5；`repeat_dispute_escalation` 4；`self_operated` 2 |
| `deactivated_customer_service` | 已注销客户进线服务 | 4 | 0 | 0 | 0 | 0 | - |
| `deduction_issues` | 扣款相关问题咨询 | 4 | 17 | 0 | 1 | 16 | `next_deduction_date` 9；`channel_maintenance` 7；`duplicate_deduction` 1 |
| `disbursement_progress` | 放款进度查询 | 5 | 10 | 0 | 0 | 10 | `failed_disbursement` 5；`disbursing_status` 3；`delayed_disbursement` 1；`partner_disbursement` 1 |
| `early_deduction` | 未到还款日被提前扣款 | 8 | 7 | 0 | 3 | 4 | `pre_deduction_sms_notice` 5；`no_pre_deduction_sms_received` 1；`genuine_early_deduction` 1 |
| `early_loan_clearance` | 提前清贷需求 | 10 | 287 | 10 | 119 | 158 | `card_control_first_attempt` 109；`not_support_near_bill_date` 103；`retention_sufficient_funds` 24；`not_support_disbursement_day` 20 |
| `fee_consultation_tier1` | 费用咨询（一线） | 8 | 32 | 0 | 1 | 31 | `fund_occupation_fee_difference` 8；`student_identity_fee_dispute` 7；`guarantee_fee_legality` 6；`same_entity_query` 3 |
| `fee_consultation_tier2` | 费用咨询（二线/高阶内诉） | 5 | 8 | 0 | 0 | 8 | `disguised_interest_objection` 6；`regulatory_complaint_threat` 2 |
| `fee_detail_query` | 查询费用明细及综合费率 | 7 | 83 | 0 | 4 | 79 | `dig_reason_before_statement_query` 33；`specific_period_query` 14；`repayment_plan_table_request` 12；`irr_calculation_explanation` 11 |
| `fee_refund_status` | 退费未到账情况咨询 | 5 | 9 | 0 | 0 | 9 | `refund_processing` 5；`confirm_refund_status_query` 2；`refund_completed` 1；`refund_overdue` 1 |
| `fee_refund_tier1` | 要求退费（一线） | 6 | 25 | 0 | 1 | 24 | `frontline_fee_reasonable_explanation` 10；`refund_not_eligible` 6；`refund_eligible` 3；`frontline_internal_complaint_escalation` 3 |
| `fee_refund_tier2` | 要求退费（二线/高阶内诉） | 15 | 5 | 0 | 0 | 5 | `guarantee_fee_or_over_24_negotiation` 2；`complaint_deescalation_before_external_channel` 1；`full_guarantee_fee_refund_objection` 1；`customer_demands_higher_minimum_amount` 1 |
| `invoice_issuance` | 发票开具 | 7 | 6 | 0 | 0 | 6 | `kaka_self_service` 3；`principal_invoice_not_supported` 1；`unsupported_funder_partner` 1；`doudou_self_service` 1 |
| `light_card_cancel_refund` | 轻享卡取消退费 | 5 | 1 | 0 | 0 | 1 | `provide_vendor_contact` 1 |
| `loan_consultation` | 贷款咨询 | 13 | 42 | 0 | 7 | 35 | `loan_nature_and_lender_explanation` 18；`guarantee_explanation_pre_and_post_loan` 7；`loan_purpose_explanation` 4；`application_rejected_data_concern` 2 |
| `loan_dispute_refund` | 借款争议特殊场景退费 | 10 | 6 | 0 | 0 | 6 | `loan_amount_not_received` 2；`claimed_unauthorized_normal_process` 2；`special_loan_scenario_retention_then_clearance` 1；`fraud_with_police_report` 1 |
| `loan_termination` | 贷款解约 | 5 | 10 | 0 | 2 | 8 | `ops_ticket_for_termination` 5；`explain_term_rationale` 5 |
| `member_cancel` | 取消会员 | 5 | 42 | 1 | 9 | 32 | `no_record` 23；`unknown_source_deferred` 16；`retain_fail` 2；`not_needed_deferred` 1 |
| `member_consultation` | 会员咨询 | 4 | 25 | 0 | 2 | 23 | `compliance_question` 15；`legality_question` 10 |
| `member_refund` | 退会员费用 | 7 | 32 | 0 | 2 | 30 | `music_fitness_used` 20；`no_auto_renewal` 7；`active_benefits` 3；`auto_renewal_cancel` 1 |
| `no_quota_issue` | 无额度问题 | 8 | 21 | 0 | 3 | 18 | `ops_ticket` 7；`no_quota_after_clearance` 5；`marketing_invited_no_quota` 3；`withdrawal_quota_zero` 3 |
| `other_certificate` | 开具其他证明 | 8 | 1 | 0 | 0 | 1 | `non_malicious_proof` 1 |
| `overdue_negotiation` | 协商还款 | 4 | 659 | 3 | 18 | 638 | `pre_overdue` 488；`mid_overdue` 125；`severe_overdue` 27；`early_overdue` 19 |
| `overpayment_refund` | 客户对公转账出错退溢余 | 8 | 10 | 0 | 0 | 10 | `genuine_overpayment` 2；`transfer_verified_full_match` 2；`not_our_corporate_account` 2；`corporate_mis_transfer_requires_statement` 1 |
| `post_loan_verification` | 核实贷后信息 | 4 | 109 | 0 | 9 | 100 | `verify_account` 49；`jiangnan_mediation` 21；`verify_staff` 20；`verify_institution` 19 |
| `premium_card_cancel` | 取消优享卡 | 8 | 4 | 0 | 2 | 2 | `no_record` 2；`retain_fail` 1；`accidental_purchase` 1 |
| `premium_card_inquiry` | 优享卡咨询 | 3 | 3 | 0 | 0 | 3 | `not_purchased` 3 |
| `premium_card_refund` | 退优享卡费用 | 5 | 2 | 0 | 0 | 2 | `retain_success` 2 |
| `quota_consultation` | 额度咨询 | 4 | 8 | 0 | 0 | 8 | `max_quota` 8 |
| `refund_value_added_service` | 退增值服务费 | 10 | 1 | 0 | 0 | 1 | `zhonghui_insurance_refund` 1 |
| `remote_disbursement` | 异地放款 | 3 | 0 | 0 | 0 | 0 | - |
| `repayment_method_inquiry` | 咨询还款方式 | 2 | 196 | 0 | 24 | 172 | `auto_deduction_detail` 105；`manual_repayment_path` 91 |
| `repayment_result_query` | 查询还款结果 | 3 | 133 | 0 | 9 | 124 | `repayment_success` 122；`repayment_delayed` 6；`repayment_processing` 5 |
| `repayment_status_issue` | 还款状态异常 | 14 | 351 | 7 | 87 | 257 | `failure_channel_corporate_payment` 111；`failure_card_limit_has_other_card` 41；`failure_rule_not_due` 41；`failure_limit_corporate_payment` 36 |
| `special_account_cancellation` | 特殊场景注销账户 | 5 | 0 | 0 | 0 | 0 | - |
| `stop_collection` | 要求停催 | 5 | 119 | 0 | 3 | 116 | `ivr_collection` 63；`ai_collection_early` 46；`normal_stop` 6；`escalate_stop` 3 |
| `stop_marketing` | 停止营销 | 7 | 10 | 0 | 0 | 10 | `kakaday_is_our_product` 4；`deactivated_received_marketing` 3；`already_stopped_still_receiving` 2；`collect_name_then_stop` 1 |
| `value_added_service_inquiry` | 增值服务咨询 | 9 | 10 | 0 | 0 | 10 | `explain_fuqiang_notary` 4；`explain_acceleration_card` 2；`collect_name_then_explain` 2；`faxin_notary_fee` 1 |

## 抽样明细

### `account_cancellation` 注销账户
- 真实 query：65；confident：12；low_confidence：21；no_select：32。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想注销账户 | `doudouqian_self_service` | confident | 0.379 | `cannot_cancel_outstanding` 0.082 |
| 我想注销账户 | `doudouqian_self_service` | confident | 0.379 | `cannot_cancel_outstanding` 0.082 |
| 我想注销账户 | `doudouqian_self_service` | confident | 0.379 | `cannot_cancel_outstanding` 0.082 |
| 我想注销账户 | `doudouqian_self_service` | confident | 0.379 | `cannot_cancel_outstanding` 0.082 |
| 我现在要进行销户。 | `doudouqian_self_service` | no_select | 0.000 | `kakaday_manual_cancel` 0.000 |
| 我要取消并关闭这个账号 | `doudouqian_self_service` | no_select | 0.000 | `kakaday_manual_cancel` 0.000 |

### `bill_date_credit_impact` 账单日还款是否影响征信
- 真实 query：9；confident：0；low_confidence：3；no_select：6。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我昨天晚上过了还款时间，一直点击还款但还不进去，后来才还进去，这是否算逾期？ | `overdue_credit_reporting` | no_select | 0.034 | `normal_repayment_credit` 0.033 |
| 我想咨询豆豆钱逾期一天是否会影响信用记录。 | `existing_overdue_credit_repair` | no_select | 0.045 | `refuse_evidence_for_credit_check` 0.040 |

### `bill_deduction_query` 查询账单扣款情况
- 真实 query：103；confident：0；low_confidence：32；no_select：71。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么今天扣了我88块钱？ | `deduction_success` | no_select | 0.000 | `deduction_pending` 0.000 |
| 帮我查一下刚才为什么扣了我39.9元 | `deduction_success` | no_select | 0.000 | `deduction_pending` 0.000 |

### `cancel_credit_authorization` 注销授信额度
- 真实 query：11；confident：0；low_confidence：4；no_select：7。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我要撤回个人信息处理的授权。 | `self_operated_can_cancel` | no_select | 0.000 | `self_operated_has_loan` 0.000 |
| 我早上在你们的APP里有一个网络贷款的申请，但你们的APP把我推给了一家第三方中介公司，他们早上给我打了几个电话进行线上分析。我现在要求收回... | `explain_difference` | no_select | 0.014 | `self_operated_can_cancel` 0.007 |

### `cancel_value_added_service` 取消增值服务
- 真实 query：10；confident：0；low_confidence：0；no_select：10。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么每个月6号都会扣我一百多块钱？ | `already_closed_no_charge` | no_select | 0.000 | `cancel_before_charge` 0.000 |
| 我刚刚开通了一个业务，要880元，请帮我退掉。 | `already_closed_no_charge` | no_select | 0.000 | `cancel_before_charge` 0.000 |

### `card_rebinding` 换绑银行卡
- 真实 query：34；confident：1；low_confidence：8；no_select：25。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 客户要求更换一张银行卡。 | `cannot_operate_for_customer` | confident | 0.297 | `app_path_not_found` 0.157 |
| 我之前与贵方协商了270000元的再分期协议，现在想咨询是否可以更改协商好的还款账号。 | `app_path_not_found` | no_select | 0.000 | `card_rebinding_failed` 0.000 |
| 我之前是还款日期，但是我想换一张还款卡，但是换不了 | `app_path_not_found` | no_select | 0.000 | `card_rebinding_failed` 0.000 |

### `clearance_certificate` 开具结清证明
- 真实 query：47；confident：0；low_confidence：6；no_select：41。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想问一下，我有一个50000元的借款，昨天晚上已经结清了，为什么借款证明开不出来？ | `not_cleared` | no_select | 0.014 | `agent_assist` 0.013 |
| 前几天我有一笔1417.45的账单，我已经结清了，需要打电话出具结清证明。 | `not_cleared` | no_select | 0.015 | `agent_assist` 0.014 |

### `close_pre_reminder` 关闭预提醒服务
- 真实 query：4；confident：0；low_confidence：0；no_select：4。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我从未逾期，但你们一天内不停地打电话提醒我周末还款日，一天打800个电话，能否关掉这个电话提醒？ | `multi_order` | no_select | 0.023 | `no_ivr_record` 0.023 |
| 在还款日之前，为什么会有电话打来？ | `multi_order` | no_select | 0.027 | `no_ivr_record` 0.000 |

### `collection_complaint` 投诉催收
- 真实 query：187；confident：1；low_confidence：4；no_select：182。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想投诉暴力催收。 | `violent_collection` | confident | 0.317 | `bad_attitude` 0.107 |
| 为什么今天我又收到你们的信息，说我不接电话、故意逃避问题？ | `high_frequency` | no_select | 0.000 | `bad_attitude` 0.000 |
| 为什么你们一直给我发短信打电话，我还欠你们钱吗？请帮我查询一下。 | `high_frequency` | no_select | 0.000 | `bad_attitude` 0.000 |

### `contract_retrieval` 调取合同
- 真实 query：22；confident：0；low_confidence：10；no_select：12。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想询问一下，你们给我发送了一条短信，说给了我一个电子函，这是做什么用的？ | `tier2_cleared` | no_select | 0.029 | `all_contracts_request` 0.025 |
| 我收到桔多多的短信，说微信卡卡贷平台有一笔贷款需要还款，但我在微信卡卡贷里查不到借款合同、借款金额等详细信息。 | `tier1_active` | no_select | 0.029 | `paper_copy` 0.021 |

### `credit_inquiry` 征信问题咨询
- 真实 query：39；confident：0；low_confidence：17；no_select：22。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我有一笔豆豆钱的还款，金额为354元，昨天到期，我忘记还款，今天早晨才看到已经还掉了，请问这算不算逾期？ | `no_credit_report_sms_notice` | no_select | 0.041 | `repayment_day_deduction_failed_credit_concern` 0.027 |
| 我的账单是14号的，你们平台没有打电话提醒我，我在15号凌晨两点还款，这算逾期吗？ | `repayment_day_deduction_failed_credit_concern` | no_select | 0.043 | `cannot_delete_valid_credit_record` 0.033 |

### `credit_modification` 修改征信
- 真实 query：20；confident：0；low_confidence：2；no_select：18。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 2022年3月11日，维氏融资担保有限公司为我担保了1721元的代偿，我已经结清了，是否可以申请向人行撤销这个代偿记录？ | `self_operated` | no_select | 0.009 | `genuine_error` 0.009 |
| 我在2025年2月6日有一笔在你们平台的借贷，额度28000元，一直在还款，现已还10期，从未逾期。但有其他平台打电话和发短信说我逾期了，声... | `clarify_institution_and_record` | no_select | 0.012 | `self_operated` 0.007 |

### `deactivated_customer_service` 已注销客户进线服务
- 本次真实数据中没有该 skill 的 query。

### `deduction_issues` 扣款相关问题咨询
- 真实 query：17；confident：0；low_confidence：1；no_select：16。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你们要求我还六百多块钱是什么意思？我没有这笔钱。 | `next_deduction_date` | no_select | 0.000 | `amount_mismatch` 0.000 |
| 为什么显示扣款59.9元后，拒赔业务没有扣款，也没有下额度？ | `next_deduction_date` | no_select | 0.021 | `amount_mismatch` 0.021 |

### `disbursement_progress` 放款进度查询
- 真实 query：10；confident：0；low_confidence：0；no_select：10。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我今天收到的这笔贷款，现在怎么看不见 | `disbursing_status` | no_select | 0.000 | `failed_disbursement` 0.000 |
| 我昨天预约了借款，显示预约借款已完成，但我没有收到款项。 | `failed_disbursement` | no_select | 0.019 | `disbursing_status` 0.000 |

### `early_deduction` 未到还款日被提前扣款
- 真实 query：7；confident：0；low_confidence：3；no_select：4。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我有一笔3500多元的还款，11月22日才到期，为什么今天就把钱扣了？ | `pre_deduction_sms_notice` | no_select | 0.049 | `next_deduction_time_after_failed_attempt` 0.039 |
| 我的手机号被无故扣款了99元，据说是你们这边扣款的。 | `no_pre_deduction_sms_received` | no_select | 0.069 | `misunderstanding_due_date` 0.022 |

### `early_loan_clearance` 提前清贷需求
- 真实 query：287；confident：10；low_confidence：119；no_select：158。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想申请提前结清贷款 | `card_control_first_attempt` | confident | 0.403 | `not_support_near_bill_date` 0.123 |
| 我想申请提前结清贷款。 | `card_control_first_attempt` | confident | 0.403 | `not_support_near_bill_date` 0.123 |
| 我想提前结清贷款 | `card_control_first_attempt` | confident | 0.312 | `not_support_near_bill_date` 0.105 |
| 我想提前结清贷款 | `card_control_first_attempt` | confident | 0.312 | `not_support_near_bill_date` 0.105 |
| 我刚刚借的2万块钱，我要还回去。 | `not_support_disbursement_day` | no_select | 0.000 | `not_support_near_bill_date` 0.000 |
| 我想把上次借的钱全部还掉 | `not_support_disbursement_day` | no_select | 0.000 | `not_support_near_bill_date` 0.000 |

### `fee_consultation_tier1` 费用咨询（一线）
- 真实 query：32；confident：0；low_confidence：1；no_select：31。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 手续费太高了 | `guarantee_fee_legality` | no_select | 0.000 | `same_entity_query` 0.000 |
| 我之前打电话询问打包费的问题，你们说会回电话，但至今没有回复。 | `student_identity_fee_dispute` | no_select | 0.015 | `irr_rate_explanation` 0.015 |

### `fee_consultation_tier2` 费用咨询（二线/高阶内诉）
- 真实 query：8；confident：0；low_confidence：0；no_select：8。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我在微信卡卡贷平台上有五笔借款，现已全部结清，但发现每笔借款的利率都超过了国家规定的24%，达到了36%，这属于高利贷。 | `disguised_interest_objection` | no_select | 0.024 | `regulatory_complaint_threat` 0.000 |
| 我之前跟你们联系过，关于利息多出了将近8000块钱的问题，你们打算怎么处理？ | `regulatory_complaint_threat` | no_select | 0.024 | `customer_accepts` 0.017 |

### `fee_detail_query` 查询费用明细及综合费率
- 真实 query：83；confident：0；low_confidence：4；no_select：79。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 帮我查一下我的账号有没有被扣款 | `irr_calculation_explanation` | no_select | 0.000 | `high_rate_objection` 0.000 |
| 帮我查一下豆豆钱平台欠款还有多少？ | `irr_calculation_explanation` | no_select | 0.000 | `high_rate_objection` 0.000 |

### `fee_refund_status` 退费未到账情况咨询
- 真实 query：9；confident：0；low_confidence：0；no_select：9。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么我现在查不到我要退款的合同？ | `refund_processing` | no_select | 0.000 | `refund_remitted` 0.000 |
| 我上个月被扣了921元，至今未退还。 | `refund_processing` | no_select | 0.000 | `refund_remitted` 0.000 |

### `fee_refund_tier1` 要求退费（一线）
- 真实 query：25；confident：0；low_confidence：1；no_select：24。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想对本次账单做一个减免。 | `refund_eligible` | no_select | 0.000 | `refund_not_eligible` 0.000 |
| 我想把罚息退给我 | `refund_eligible` | no_select | 0.000 | `refund_not_eligible` 0.000 |

### `fee_refund_tier2` 要求退费（二线/高阶内诉）
- 真实 query：5；confident：0；low_confidence：0；no_select：5。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我上个月逾期时想提前还款，当时有工作人员加我微信，承诺提前还款可以申请减免。但现在联系不上该工作人员，提前还款和减免都无法办理。 | `customer_demands_higher_minimum_amount` | no_select | 0.017 | `full_guarantee_fee_refund_objection` 0.016 |
| 我联系了您提供的电话，对方表示无法退款，请问该如何处理？ | `complaint_deescalation_before_external_channel` | no_select | 0.045 | `repeated_application_and_price_reduction` 0.030 |

### `invoice_issuance` 发票开具
- 真实 query：6；confident：0；low_confidence：0；no_select：6。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 请帮我打印账单 | `doudou_self_service` | no_select | 0.000 | `kaka_self_service` 0.000 |
| 我在12月03日收到一张维氏融资担保有限公司开具的发票 | `kaka_self_service` | no_select | 0.031 | `doudou_self_service` 0.030 |

### `light_card_cancel_refund` 轻享卡取消退费
- 真实 query：1；confident：0；low_confidence：0；no_select：1。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我要取消清享卡会员。 | `provide_vendor_contact` | no_select | 0.095 | `guide_self_cancel_renewal` 0.046 |

### `loan_consultation` 贷款咨询
- 真实 query：42；confident：0；low_confidence：7；no_select：35。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我在豆豆钱里的钱已经还完了，我能不能在豆豆钱那边再借一点钱？ | `loan_purpose_explanation` | no_select | 0.000 | `eligibility_explanation` 0.000 |
| 我很久没使用豆豆钱了，为什么现在还要我还钱？ | `loan_purpose_explanation` | no_select | 0.000 | `eligibility_explanation` 0.000 |

### `loan_dispute_refund` 借款争议特殊场景退费
- 真实 query：6；confident：0；low_confidence：0；no_select：6。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我没有在你们平台借过钱。 | `claimed_unauthorized_normal_process` | no_select | 0.000 | `confirm_disputed_loan_order` 0.000 |
| 我没有在豆豆钱包上借钱，为什么扣我的钱？ | `claimed_unauthorized_normal_process` | no_select | 0.000 | `confirm_disputed_loan_order` 0.000 |

### `loan_termination` 贷款解约
- 真实 query：10；confident：0；low_confidence：2；no_select：8。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 关于豆豆钱借款，昨天在不知情的情况下直接到账了，我想把借款退回去。 | `ops_ticket_for_termination` | no_select | 0.015 | `retention_success` 0.000 |
| 这个贷款你把它停掉，我不需要了。这个什么缴费，我根本不知道怎么回事，你把它帮我取消掉。 | `explain_term_rationale` | no_select | 0.024 | `cannot_terminate` 0.016 |

### `member_cancel` 取消会员
- 真实 query：42；confident：1；low_confidence：9；no_select：32。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我要取消会员服务。 | `no_record` | confident | 0.292 | `retain_fail` 0.058 |
| 我账户上显示有会员月卡，能否帮我取消这个会员？我没有订购过这个会员。 | `no_record` | no_select | 0.021 | `retain_fail` 0.021 |
| 我想问一下，我这个会员能不能帮我解除掉并退掉 | `no_record` | no_select | 0.025 | `not_needed_deferred` 0.023 |

### `member_consultation` 会员咨询
- 真实 query：25；confident：0；low_confidence：2；no_select：23。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 请帮我查看一下我的会员，为什么我没有续过费用，但每个月都扣款，每个月都扣？ | `compliance_question` | no_select | 0.017 | `legality_question` 0.016 |
| 请帮我查看一下，我在你们平台上开通了多少元的会员？ | `compliance_question` | no_select | 0.021 | `legality_question` 0.020 |

### `member_refund` 退会员费用
- 真实 query：32；confident：0；low_confidence：2；no_select：30。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我昨天申请了一笔贷款失败了，我开了两个会员，我要把这两个会员退了 | `music_fitness_used` | no_select | 0.016 | `retain_success` 0.000 |
| 我在豆豆钱APP的还款功能板块中，误将近期应还下方的会员充值当作还款操作，点错了，能否退回这笔费用？ | `active_benefits` | no_select | 0.016 | `escalate_to_supervisor` 0.012 |

### `no_quota_issue` 无额度问题
- 真实 query：21；confident：0；low_confidence：3；no_select：18。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想在你们这个平台借钱，但借不出来，请问是什么原因？ | `no_loan_record` | no_select | 0.000 | `has_loan_record` 0.000 |
| 麻烦帮我查看一下豆豆钱账户，为什么账户显示有钱，我没有逾期过，征信也比较好，却借不出来钱？ | `wait_activation` | no_select | 0.014 | `withdrawal_quota_zero` 0.012 |

### `other_certificate` 开具其他证明
- 真实 query：1；confident：0；low_confidence：0；no_select：1。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我有逾期，但上笔逾期时已向你们发送相关证明，刚才有人联系我，让我再联系你们，说上次发的证明已无效。 | `non_malicious_proof` | no_select | 0.023 | `supported_overdue_proof` 0.021 |

### `overdue_negotiation` 协商还款
- 真实 query：659；confident：3；low_confidence：18；no_select：638。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想申请二次分期。 | `mid_overdue` | confident | 0.477 | `pre_overdue` 0.000 |
| 我想申请二次分期。 | `mid_overdue` | confident | 0.477 | `pre_overdue` 0.000 |
| 我想协商延期还款。 | `pre_overdue` | confident | 0.273 | `early_overdue` 0.000 |
| 为什么还没有人联系我？ | `pre_overdue` | no_select | 0.000 | `early_overdue` 0.000 |
| 之前的方案到期了，我想续一下这个方案。 | `pre_overdue` | no_select | 0.000 | `early_overdue` 0.000 |

### `overpayment_refund` 客户对公转账出错退溢余
- 真实 query：10；confident：0；low_confidence：0；no_select：10。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想问一下，我已经还清欠款了，你们还打电话催收，导致我多交了钱，现在要求退款为什么这么难？ | `transfer_verified_full_match` | no_select | 0.015 | `corporate_mis_transfer_requires_statement` 0.010 |
| 我刚刚还了一笔钱，朋友转款到卡里后，你们的系统直接扣掉了，能否给我退回来？ | `transfer_verified_full_match` | no_select | 0.017 | `proof_received_wait_refund` 0.013 |

### `post_loan_verification` 核实贷后信息
- 真实 query：109；confident：0；low_confidence：9；no_select：100。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么有一个微信的人加我微信，让我从另一个账户里还款 | `verify_account` | no_select | 0.000 | `verify_staff` 0.000 |
| 刚刚是哪个部门打电话给我了？ | `verify_account` | no_select | 0.000 | `verify_staff` 0.000 |

### `premium_card_cancel` 取消优享卡
- 真实 query：4；confident：0；low_confidence：2；no_select：2。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我刚刚在借款时点击了优享卡，它显示要扣费500多元且每月自动续费，自动续费已开通。现在放款失败，但协议已开通，我想取消它。 | `retain_fail` | no_select | 0.045 | `no_record` 0.044 |
| 我刚刚打开我的账户，发现上面有一个优享卡，30天后到期将扣款1645元，这个价格太高了，能给我取消吗？ | `no_record` | no_select | 0.046 | `accidental_purchase` 0.036 |

### `premium_card_inquiry` 优享卡咨询
- 真实 query：3；confident：0；low_confidence：0；no_select：3。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想咨询一下，现在借钱有优享卡和亲享卡，优享卡是一次性扣费还是每月扣费？ | `not_purchased` | no_select | 0.053 | `purchased_inquire` 0.051 |
| 我有一笔贷款，但发现有一个优享卡，这是什么？ | `not_purchased` | no_select | 0.077 | `purchased_inquire` 0.074 |

### `premium_card_refund` 退优享卡费用
- 真实 query：2；confident：0；low_confidence：0；no_select：2。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 前两天办理了贷款，贷款金额为50000元。今天发现优享卡扣款2917元，我根本没有使用这个会员，为什么会扣款并要求退款？ | `retain_success` | no_select | 0.000 | `no_risk_refusal` 0.000 |
| 我刚才借了一笔款，为什么优享卡费用1938元，要求立即退还给我 | `retain_success` | no_select | 0.000 | `no_risk_refusal` 0.000 |

### `quota_consultation` 额度咨询
- 真实 query：8；confident：0；low_confidence：0；no_select：8。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我明天有一笔还款，但你们从上个月开始就不给我周转额度了，导致我还款很困难。 | `max_quota` | no_select | 0.017 | `escalate_ops` 0.017 |
| 我想请你帮我看一下我在你们这个平台上是否有额度，是否可以提现。 | `max_quota` | no_select | 0.019 | `escalate_ops` 0.019 |

### `refund_value_added_service` 退增值服务费
- 真实 query：1；confident：0；low_confidence：0；no_select：1。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 这个保险续保了，怎么退？ | `zhonghui_insurance_refund` | no_select | 0.044 | `fuqiang_partial_refund` 0.000 |

### `remote_disbursement` 异地放款
- 本次真实数据中没有该 skill 的 query。

### `repayment_method_inquiry` 咨询还款方式
- 真实 query：196；confident：0；low_confidence：24；no_select：172。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你们这边是否支持对公账户转账？ | `auto_deduction_detail` | no_select | 0.000 | `manual_repayment_path` 0.000 |
| 刚才专员给我打电话，发了一个短信链接，但我现在用不了，想麻烦他再发一个，请问怎么联系？ | `auto_deduction_detail` | no_select | 0.000 | `manual_repayment_path` 0.000 |

### `repayment_result_query` 查询还款结果
- 真实 query：133；confident：0；low_confidence：9；no_select：124。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么我已经向公司账户转账2746元还清了欠款，但平台上还没有核销显示？ | `repayment_success` | no_select | 0.000 | `repayment_processing` 0.000 |
| 帮我查询一下还有多少钱没有还。 | `repayment_success` | no_select | 0.000 | `repayment_processing` 0.000 |

### `repayment_status_issue` 还款状态异常
- 真实 query：351；confident：7；low_confidence：87；no_select：257。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么我的银行卡扣款失败？ | `failure_card_limit_has_other_card` | confident | 0.494 | `failure_bank_card_contract` 0.307 |
| 自动还款扣款失败，为什么？ | `failure_limit_corporate_payment` | confident | 0.344 | `failure_rule_not_due` 0.278 |
| 我的银行卡无法还款。 | `failure_card_limit_has_other_card` | confident | 0.334 | `failure_bank_card_contract` 0.152 |
| 我的还款扣款失败了，无法还款。 | `failure_limit_corporate_payment` | confident | 0.302 | `failure_limit_qr_payment` 0.239 |
| 我刚才不小心有一笔500元的借款，我要把它还了，为什么还不了 | `failure_insufficient_balance_sufficient_now` | no_select | 0.000 | `failure_insufficient_balance_still_low` 0.000 |
| 我有一笔款项，为什么还无法存入？ | `failure_insufficient_balance_sufficient_now` | no_select | 0.000 | `failure_insufficient_balance_still_low` 0.000 |

### `special_account_cancellation` 特殊场景注销账户
- 本次真实数据中没有该 skill 的 query。

### `stop_collection` 要求停催
- 真实 query：119；confident：0；low_confidence：3；no_select：116。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 为什么我没有逾期，却一直收到电话？ | `ai_collection_early` | no_select | 0.000 | `ivr_collection` 0.000 |
| 为什么还有这些短信发送？ | `ai_collection_early` | no_select | 0.000 | `ivr_collection` 0.000 |

### `stop_marketing` 停止营销
- 真实 query：10；confident：0；low_confidence：0；no_select：10。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想问一下，你们1068或1069发的信息都是你们系统发的吗？ | `deactivated_received_marketing` | no_select | 0.017 | `execute_stop_marketing` 0.017 |
| 我今天下午发现有两个未接电话，我估计是你们打过来的。 | `kakaday_is_our_product` | no_select | 0.018 | `deactivated_received_marketing` 0.018 |

### `value_added_service_inquiry` 增值服务咨询
- 真实 query：10；confident：0；low_confidence：0；no_select：10。
| query | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我刚才收到了一个关于卡卡的短信，想确认一下是怎么回事。 | `explain_fuqiang_notary` | no_select | 0.000 | `explain_legal_basis` 0.000 |
| 我刚才借了800块钱，发现上面有很多会员需要付费，请帮我查看一下。 | `explain_zhonghui_insurance` | no_select | 0.016 | `explain_ju_jiu_fan` 0.015 |
