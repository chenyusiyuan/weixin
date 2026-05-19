# 真实多轮 Query Branch 选择效果

- 生成时间：2026-04-27 17:19:15
- 数据源：`golden_test.jsonl`；intent→skill 映射：`scripts/references/merged_intent_skill_mapping.json`。
- 口径：同一通电话内客户 query 合并为上下文，再在 gold skill 的 branch 树中选择最接近分支。
- 说明：仍然没有 gold branch 标签，因此这是分支可分性/命中清晰度检查。

## 总览

- 通电话数：295；评估 skill-context：811。
- 有真实上下文的 branch skill：37。
- confident：0；low_confidence：14；no_select：797。

## Skill 汇总

| skill_id | 名称 | branch | contexts | confident | low | no_select | top branches |
|---|---|---:|---:|---:|---:|---:|---|
| `account_cancellation` | 注销账户 | 4 | 15 | 0 | 1 | 14 | `doudouqian_self_service` 9；`escalate_to_tier2` 3；`cannot_cancel_outstanding` 2；`kakaday_manual_cancel` 1 |
| `bill_date_credit_impact` | 账单日还款是否影响征信 | 8 | 60 | 0 | 1 | 59 | `sufficient_balance_not_deducted_credit_concern` 19；`repayment_day_failed_sms_credit_concern` 12；`repayment_day_collection_call_credit_concern` 9；`overdue_credit_reporting` 7 |
| `bill_deduction_query` | 查询账单扣款情况 | 9 | 32 | 0 | 0 | 32 | `deduction_failed` 8；`no_internal_deduction_record` 6；`bill_deduction_amount_matched` 5；`deduction_success` 4 |
| `cancel_credit_authorization` | 注销授信额度 | 4 | 14 | 0 | 0 | 14 | `explain_difference` 8；`self_operated_can_cancel` 3；`non_self_operated` 3 |
| `card_rebinding` | 换绑银行卡 | 3 | 5 | 0 | 0 | 5 | `app_path_not_found` 4；`card_rebinding_failed` 1 |
| `clearance_certificate` | 开具结清证明 | 6 | 11 | 0 | 0 | 11 | `not_cleared` 5；`agent_assist` 2；`identify_target_order` 2；`system_failed` 1 |
| `collection_complaint` | 投诉催收 | 4 | 19 | 0 | 0 | 19 | `high_frequency` 8；`violent_collection` 6；`expose_contacts` 3；`bad_attitude` 2 |
| `contract_retrieval` | 调取合同 | 8 | 2 | 0 | 0 | 2 | `tier1_active` 2 |
| `credit_inquiry` | 征信问题咨询 | 18 | 14 | 0 | 0 | 14 | `no_credit_report_sms_notice` 2；`guarantee_compensation_reporting` 2；`reporting_rules` 2；`student_borrower_credit_dispute` 2 |
| `credit_modification` | 修改征信 | 7 | 14 | 0 | 0 | 14 | `clarify_institution_and_record` 9；`genuine_error` 3；`non_self_operated` 1；`repeat_dispute_escalation` 1 |
| `deactivated_customer_service` | 已注销客户进线服务 | 4 | 15 | 0 | 0 | 15 | `handle_current_order_only` 10；`send_dispute_sms` 3；`credit_report_flow` 2 |
| `deduction_issues` | 扣款相关问题咨询 | 4 | 46 | 0 | 1 | 45 | `next_deduction_date` 24；`channel_maintenance` 20；`duplicate_deduction` 2 |
| `disbursement_progress` | 放款进度查询 | 5 | 2 | 0 | 0 | 2 | `failed_disbursement` 2 |
| `early_deduction` | 未到还款日被提前扣款 | 8 | 46 | 0 | 0 | 46 | `next_deduction_time_after_failed_attempt` 21；`pre_deduction_sms_notice` 11；`misunderstanding_due_date` 6；`no_pre_deduction_sms_received` 3 |
| `early_loan_clearance` | 提前清贷需求 | 10 | 27 | 0 | 0 | 27 | `card_control_first_attempt` 9；`not_support_near_bill_date` 5；`retention_sufficient_funds` 3；`not_support_last_installment` 3 |
| `fee_consultation_tier1` | 费用咨询（一线） | 8 | 5 | 0 | 0 | 5 | `guarantee_fee_legality` 2；`irr_rate_explanation` 2；`bundled_sales_query` 1 |
| `fee_consultation_tier2` | 费用咨询（二线/高阶内诉） | 5 | 5 | 0 | 0 | 5 | `disguised_interest_objection` 3；`compliance_document_request` 2 |
| `fee_detail_query` | 查询费用明细及综合费率 | 7 | 36 | 0 | 0 | 36 | `dig_reason_before_statement_query` 11；`repayment_plan_table_request` 9；`tier2_rate_query_by_order_age` 8；`irr_calculation_explanation` 6 |
| `fee_refund_status` | 退费未到账情况咨询 | 5 | 4 | 0 | 0 | 4 | `refund_completed` 2；`confirm_refund_status_query` 2 |
| `fee_refund_tier1` | 要求退费（一线） | 6 | 4 | 0 | 0 | 4 | `frontline_fee_reasonable_explanation` 2；`persistent_demand_escalate` 1；`frontline_internal_complaint_escalation` 1 |
| `fee_refund_tier2` | 要求退费（二线/高阶内诉） | 15 | 4 | 0 | 0 | 4 | `repeated_application_and_price_reduction` 3；`ask_expected_amount_and_bottom_line` 1 |
| `invoice_issuance` | 发票开具 | 7 | 2 | 0 | 0 | 2 | `doudou_self_service` 1；`kaka_self_service` 1 |
| `loan_consultation` | 贷款咨询 | 13 | 12 | 0 | 1 | 11 | `loan_nature_and_lender_explanation` 3；`document_requirements` 3；`eligibility_explanation` 2；`application_rejected_data_concern` 2 |
| `loan_dispute_refund` | 借款争议特殊场景退费 | 10 | 4 | 0 | 0 | 4 | `hesitation_period_principal_clearance` 1；`special_loan_scenario_retention_then_clearance` 1；`claimed_unauthorized_normal_process` 1；`confirm_disputed_loan_order` 1 |
| `member_cancel` | 取消会员 | 5 | 18 | 0 | 0 | 18 | `not_needed_deferred` 8；`unknown_source_deferred` 4；`no_record` 4；`retain_fail` 1 |
| `member_refund` | 退会员费用 | 7 | 18 | 0 | 0 | 18 | `music_fitness_used` 9；`no_auto_renewal` 3；`retain_success` 2；`auto_renewal_cancel` 1 |
| `no_quota_issue` | 无额度问题 | 8 | 7 | 0 | 0 | 7 | `withdrawal_quota_zero` 3；`ops_ticket` 1；`no_quota_after_clearance` 1；`marketing_invited_no_quota` 1 |
| `overdue_negotiation` | 协商还款 | 4 | 70 | 0 | 0 | 70 | `pre_overdue` 44；`early_overdue` 11；`mid_overdue` 11；`severe_overdue` 4 |
| `post_loan_verification` | 核实贷后信息 | 4 | 6 | 0 | 1 | 5 | `verify_account` 3；`verify_institution` 2；`jiangnan_mediation` 1 |
| `premium_card_inquiry` | 优享卡咨询 | 3 | 10 | 0 | 0 | 10 | `not_purchased` 6；`purchased_inquire` 3；`purchased_confirm_continue` 1 |
| `quota_consultation` | 额度咨询 | 4 | 7 | 0 | 0 | 7 | `max_quota` 6；`amount_discrepancy` 1 |
| `repayment_method_inquiry` | 咨询还款方式 | 2 | 79 | 0 | 3 | 76 | `auto_deduction_detail` 49；`manual_repayment_path` 30 |
| `repayment_result_query` | 查询还款结果 | 3 | 77 | 0 | 1 | 76 | `repayment_success` 54；`repayment_delayed` 14；`repayment_processing` 9 |
| `repayment_status_issue` | 还款状态异常 | 14 | 46 | 0 | 5 | 41 | `failure_card_limit_has_other_card` 9；`failure_channel_corporate_payment` 7；`failure_bank_card_contract` 7；`failure_rule_not_due` 6 |
| `special_account_cancellation` | 特殊场景注销账户 | 5 | 15 | 0 | 0 | 15 | `direct_to_debt_company` 7；`direct_to_huatong_company` 3；`submit_other_ticket` 3；`request_settlement_proof` 1 |
| `stop_collection` | 要求停催 | 5 | 50 | 0 | 0 | 50 | `ai_collection_early` 38；`ivr_collection` 7；`escalate_stop` 2；`normal_stop` 2 |
| `value_added_service_inquiry` | 增值服务咨询 | 9 | 10 | 0 | 0 | 10 | `explain_fuqiang_notary` 4；`explain_tianchuang_credit` 2；`explain_acceleration_card` 2；`explain_zhonghui_insurance` 1 |

## 抽样明细

### `account_cancellation` 注销账户
- contexts：15；confident：0；low_confidence：1；no_select：14。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，帮我把账户关掉，注销了。；对，我要注销，让我的征信上面体现不了。；我知道有记录，我要显示销户，是结清嘛？；那到时候我的征信上面就显示结清了，对不对？ | `cannot_cancel_outstanding` | no_select | 0.031 | `doudouqian_self_service` 0.029 |
| 我现在在网上看到你们公司的贷款，我想把它注销了。刚才是对外贸易金融公司转接到你这边了。；没有原因，我征信影响啊。；结清证明您这边不能充嘛，我征信上直接显示已结清啊。；我让你这边直接线上注销，我那个软件... | `doudouqian_self_service` | no_select | 0.031 | `escalate_to_tier2` 0.031 |

### `bill_date_credit_impact` 账单日还款是否影响征信
- contexts：60；confident：0；low_confidence：1；no_select：59。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我问一下，你们这个平台怎么还款还不了？；我是用微信里面还的，但是点进去说请稍后联系客服，点不进去。；都是我手工还的。不是卡不卡的问题，点进去根本就点不进去你们平台。；为什么要自动扣？我人工还不行... | `refuse_evidence_for_credit_check` | no_select | 0.010 | `repeated_credit_query_concern` 0.010 |
| 我想问一下你们这个豆豆钱，我昨天还不进去，今天还还不进去，现在老给我打电话，就200 多块钱嘛；一天打十几个电话，我的天；建设银行，之前中行，现在我往里面转上2300块钱，你们扣吧，好吧；我已经绑定了... | `repayment_day_collection_call_credit_concern` | no_select | 0.010 | `repayment_day_failed_sms_credit_concern` 0.009 |

### `bill_deduction_query` 查询账单扣款情况
- contexts：32；confident：0；low_confidence：0；no_select：32。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我这个豆豆钱是不是11月16号已经全部还清了？；那有什么证明吗？；我看到了，但他说要发邮箱。我好像把我的邮箱搞丢了，我之前那个邮箱就是我这个手机号码，后来不知道怎么变成了六位数字加字母的。之前那... | `no_internal_deduction_record` | no_select | 0.005 | `bill_deduction_amount_matched` 0.004 |
| 你好，我问一下我还款的钱，每期都是一样的吗？我上个月9月30日用了60000元，分12个月，现在每个月是多少？；对，我就问问那个。是这样，我想问一下，如果说我下个月要提前结清的话，还多少利息？还是我每... | `no_internal_deduction_record` | no_select | 0.014 | `deduction_failed` 0.011 |

### `cancel_credit_authorization` 注销授信额度
- contexts：14；confident：0；low_confidence：0；no_select：14。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你刚刚是哪个打电话给我了？；刚刚就是这个021的号码给我回电了，你看一下是不是那个，你们那边征信部门的同事啊。 | `self_operated_can_cancel` | no_select | 0.000 | `self_operated_has_loan` 0.000 |
| 你好，之前的几期以为是20号还款，所以都正好晚还了一天，产生逾期了，前段时间联系那个客服，客服说如果说产生逾期的话，再联系我们，说我们帮我处理。你看怎么怎么处理一下这个问题啊。；对，我听他们说我这有逾... | `non_self_operated` | no_select | 0.004 | `explain_difference` 0.004 |

### `card_rebinding` 换绑银行卡
- contexts：5；confident：0；low_confidence：0；no_select：5。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 啊，我这边想查询我的紧急联系人；那过了这段时间是可以帮我查到紧急联系人的，是吗；哪边可以查询到；因为我的有的紧急联系人可能换了联系方式。然后我这边就是留的那个电话号码，是那个机主已经换人了，然后可能会... | `card_rebinding_failed` | no_select | 0.019 | `app_path_not_found` 0.009 |
| 我今天应该是最后一笔还款，但是还不进去，它老是显示该银行卡需要重新签约。；我已经换了2张银行卡了，都是这个样子。 | `app_path_not_found` | no_select | 0.036 | `cannot_operate_for_customer` 0.029 |

### `clearance_certificate` 开具结清证明
- contexts：11；confident：0；low_confidence：0；no_select：11。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我这个豆豆钱是不是11月16号已经全部还清了？；那有什么证明吗？；我看到了，但他说要发邮箱。我好像把我的邮箱搞丢了，我之前那个邮箱就是我这个手机号码，后来不知道怎么变成了六位数字加字母的。之前那... | `official_issuance` | no_select | 0.010 | `agent_assist` 0.006 |
| 你好，你看一下我那个贷款是2500的是不都还完了？；我要开具结清证明。；然后你帮我把我在豆豆钱的所有卡的信息包括身份信息全部删除销户。；暂时没有借款需求了。 | `not_cleared` | no_select | 0.018 | `agent_assist` 0.017 |

### `collection_complaint` 投诉催收
- contexts：19；confident：0；low_confidence：0；no_select：19。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，今天是还款日，有两个问题。第一个是银行卡不能用，上几期都是通过微信还款的，你们会发链接，对吧？；第二个问题是我是不是今天才到还款日？您帮我查一下。；20分钟？我现在还不上，得回去之后再还。；好的... | `high_frequency` | no_select | 0.000 | `bad_attitude` 0.000 |
| 你好，你们这个每个月给我打电话骚扰，找什么蔡女士还钱。你们搞没搞清楚到底是不是蔡女士的电话？ | `high_frequency` | no_select | 0.000 | `bad_attitude` 0.000 |

### `contract_retrieval` 调取合同
- contexts：2；confident：0；low_confidence：0；no_select：2。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，请问一下，我前几天也打电话了，这边催收的电话给我打了过来，然后跟我联系，现在我要那个借款合同。；959，建行的。对了，我跟你再说一下，帮我登记一下，因为之前我也说了，但是估计他们没给我备注吧。我... | `tier1_active` | no_select | 0.018 | `account_cancelled` 0.016 |
| 我要看一下借款，我要借款合同。；好，然后我要查看合同，然后我要开发票。；合同你发到我邮箱里面吗？我自己也能看得到，我在平台里也能看得到哈。；那没有，我就是要开发票，所有每一笔的交易还款，帮我开下发票。... | `tier1_active` | no_select | 0.033 | `cancelled_retention_dispute` 0.014 |

### `credit_inquiry` 征信问题咨询
- contexts：14；confident：0；low_confidence：0；no_select：14。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你刚刚是哪个打电话给我了？；刚刚就是这个021的号码给我回电了，你看一下是不是那个，你们那边征信部门的同事啊。 | `credit_score` | no_select | 0.011 | `credit_inquiry_general` 0.011 |
| 我申请的征信异议资料已经递交了。早上看到有12点多、快12点给我打了3个电话没接到，所以我看一下回电给您。；着急啊，你赶紧把我修复一下，我有急用这个征信啊。 | `no_grace_period_credit_reporting` | no_select | 0.014 | `credit_update_timeline_after_correction` 0.013 |

### `credit_modification` 修改征信
- contexts：14；confident：0；low_confidence：0；no_select：14。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，帮我查询一下我在豆豆钱的账号是否已经注销完了？；是这样的，我另外一个平台小米天星金融要注销账号，他们说我在豆豆钱上还有一个账号跟他们有服务，没有注销，让我来这边注销后他们才能处理。；那注销完后，... | `repeat_dispute_escalation` | no_select | 0.009 | `non_self_operated` 0.006 |
| 你好，是这样的，我今天把你们的款全部结清了，然后我想开个结清证明，他说要隔一天。我现在想问，你能不能提前帮我把你们平台的授信额度全部关闭？；对，您帮我把授信额度都关了吧。；可以。豆豆钱的其他的您全部都... | `genuine_error` | no_select | 0.010 | `special_circumstances` 0.009 |

### `deactivated_customer_service` 已注销客户进线服务
- contexts：15；confident：0；low_confidence：0；no_select：15。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，你看一下我那个贷款是2500的是不都还完了？；我要开具结清证明。；然后你帮我把我在豆豆钱的所有卡的信息包括身份信息全部删除销户。；暂时没有借款需求了。 | `send_dispute_sms` | no_select | 0.000 | `credit_report_flow` 0.000 |
| 你好，我想把这个豆豆钱的账户号那些都给我取消了。 | `send_dispute_sms` | no_select | 0.000 | `credit_report_flow` 0.000 |

### `deduction_issues` 扣款相关问题咨询
- contexts：46；confident：0；low_confidence：1；no_select：45。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我逾期了一天有没有征信问题？；我想问一下逾期一天有没有问题？；怎么个跟进法？ | `next_deduction_date` | no_select | 0.000 | `amount_mismatch` 0.000 |
| 我想问一下你们这个豆豆钱，我昨天还不进去，今天还还不进去，现在老给我打电话，就200 多块钱嘛；一天打十几个电话，我的天；建设银行，之前中行，现在我往里面转上2300块钱，你们扣吧，好吧；我已经绑定了... | `next_deduction_date` | no_select | 0.000 | `amount_mismatch` 0.000 |

### `disbursement_progress` 放款进度查询
- contexts：2；confident：0；low_confidence：0；no_select：2。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好。我想请问一下，我刚才是不是就是说借款失败的？；想问一下，我刚才我刚才看上面显示的是啥，是审核当中还是说失败呀？；我在看上面是显示好像什么失败了，还有普通通道了，还有啥东西？什么通道，然后普通通道... | `failed_disbursement` | no_select | 0.025 | `delayed_disbursement` 0.008 |
| 微信卡卡贷还有这种微商用不了。；提现显示普通通道反馈失败。 | `failed_disbursement` | no_select | 0.053 | `delayed_disbursement` 0.019 |

### `early_deduction` 未到还款日被提前扣款
- contexts：46；confident：0；low_confidence：0；no_select：46。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想问一下你们这个豆豆钱，我昨天还不进去，今天还还不进去，现在老给我打电话，就200 多块钱嘛；一天打十几个电话，我的天；建设银行，之前中行，现在我往里面转上2300块钱，你们扣吧，好吧；我已经绑定了... | `next_deduction_time_after_failed_attempt` | no_select | 0.010 | `pre_deduction_sms_notice` 0.009 |
| 我问一下，我那个明明是180多没还吧，怎么老是显示826没还？；什么？我们不是已经还进去了吗？那个六百多。；对，我的意思就是说昨天的我已经还掉了，然后它显示有一个短信过来说还有八百多。 | `pre_deduction_sms_notice` | no_select | 0.011 | `no_pre_deduction_sms_received` 0.007 |

### `early_loan_clearance` 提前清贷需求
- contexts：27；confident：0；low_confidence：0；no_select：27。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我想查询一下，我还差多少本金就完了，我想提前结清。；我就是不想再欠钱了，我现在手里有点钱，想就提前都给你们还上。我当时着急用钱，现在不需要了，谢谢。；1004.59，先零数的，我去查个零。那个利... | `card_control_first_attempt` | no_select | 0.020 | `retention_high_rate` 0.013 |
| 我是想协商自主还款的，王小云。；现在实在是管不上了，所以我想着能不能把那个利息给我免一下。；就是你这个针对，嗯，我觉得这个就是利息太高了，我觉得也没有意思。；对，能不能让催收的还了，停催2~3年。；后... | `retention_sufficient_funds` | no_select | 0.024 | `retention_frequent_collection` 0.023 |

### `fee_consultation_tier1` 费用咨询（一线）
- contexts：5；confident：0；low_confidence：0；no_select：5。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想问一下，我12月08日有一期还款是吧？；然后我看了一下，这里面息费的话，还有一个担保费在里面。；我今天这是最后一期了，是吧？我现在才看到还有这个担保费在里面。；我要是早看到有这个担保费，我早就打投... | `guarantee_fee_legality` | no_select | 0.020 | `same_entity_query` 0.017 |
| 刚才我有一个账单是明天到期，明天还款。刚才我操作了一下，提前还款，因为是12 期嘛，这是最后一期。我说提前一下子全部还吧，结果应该是还1500 多，结果呢我提前结清呢，他扣了我两笔，扣了一个530 ，... | `irr_rate_explanation` | no_select | 0.021 | `fund_occupation_fee_difference` 0.021 |

### `fee_consultation_tier2` 费用咨询（二线/高阶内诉）
- contexts：5；confident：0；low_confidence：0；no_select：5。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我想问一下，我12月08日有一期还款是吧？；然后我看了一下，这里面息费的话，还有一个担保费在里面。；我今天这是最后一期了，是吧？我现在才看到还有这个担保费在里面。；我要是早看到有这个担保费，我早就打投... | `disguised_interest_objection` | no_select | 0.013 | `customer_accepts` 0.010 |
| 你好，你帮我查一下我这个豆豆钱的会员费是多少钱？；没有开通过会员。那我总共订单是多少钱？；5万元本金吗？；那5万元是本金是吗？；我想问一下这个利息是多少，担保费是多少？；没有办法查询是吗？那我举报了，... | `disguised_interest_objection` | no_select | 0.017 | `regulatory_complaint_threat` 0.015 |

### `fee_detail_query` 查询费用明细及综合费率
- contexts：36；confident：0；low_confidence：0；no_select：36。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 今天扣了我两笔钱，一个八十九，一个是两千多块钱。我想看一下这两笔钱。 | `irr_calculation_explanation` | no_select | 0.000 | `high_rate_objection` 0.000 |
| 扣款多扣了是吗？不是，是扣款扣过，刚才我又手动还了，相当于重复还了。 | `irr_calculation_explanation` | no_select | 0.000 | `high_rate_objection` 0.000 |

### `fee_refund_status` 退费未到账情况咨询
- contexts：4；confident：0；low_confidence：0；no_select：4。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 对，0847，没有。我都没接到短信，上次查也没有记录。；11月9号到今天10月24号，很多天了。之前说三天能退回来，又过了三天，我又打电话，说退回来了，让我去银行查，我也没有收到。 | `refund_completed` | no_select | 0.013 | `refund_remitted` 0.010 |
| 你好，我之前我还的那个钱，用朋友帮我还的，然后说给我退回来，为什么到现在还没到？；什么意思啊？你原路给我退回，不是退到我朋友那吗？；你们客服给我，你们那边员工给我打电话，19号就给我退了，到现在还没退... | `confirm_refund_status_query` | no_select | 0.015 | `refund_processing` 0.000 |

### `fee_refund_tier1` 要求退费（一线）
- contexts：4；confident：0；low_confidence：0；no_select：4。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，多扣的钱，然后现在需要人工给我核实过后退过来呀；前天吧，我现在也不太清楚了，这个事情已经两天了，一直打电话一直说，退到今天也还没退呀；那行，我给你们上传是吧，上传完之后呢，再给你们打电话吗 | `frontline_fee_reasonable_explanation` | no_select | 0.006 | `refund_eligible` 0.000 |
| 我的账单已经结清了。你们上次说返我多余的利息，返我100块钱是2900，那个账单5000多。我已经找了你们人工，让你们给我返款。那个5000块钱的得多收我的利息，不然我举报了，不然我打电话了。；他给我... | `frontline_internal_complaint_escalation` | no_select | 0.006 | `refund_eligible` 0.000 |

### `fee_refund_tier2` 要求退费（二线/高阶内诉）
- contexts：4；confident：0；low_confidence：0；no_select：4。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，多扣的钱，然后现在需要人工给我核实过后退过来呀；前天吧，我现在也不太清楚了，这个事情已经两天了，一直打电话一直说，退到今天也还没退呀；那行，我给你们上传是吧，上传完之后呢，再给你们打电话吗 | `repeated_application_and_price_reduction` | no_select | 0.016 | `fraud_claim_refund` 0.008 |
| 我的账单已经结清了。你们上次说返我多余的利息，返我100块钱是2900，那个账单5000多。我已经找了你们人工，让你们给我返款。那个5000块钱的得多收我的利息，不然我举报了，不然我打电话了。；他给我... | `repeated_application_and_price_reduction` | no_select | 0.020 | `guarantee_fee_or_over_24_negotiation` 0.012 |

### `invoice_issuance` 发票开具
- contexts：2；confident：0；low_confidence：0；no_select：2。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 第一个就是我前两周打过电话，我前期跟平台合作，但是我已经把这个还清了，发票的开具截止到现在依然没有开具。；第二个就是因为平台现在也出现收贷的问题，所以我有个诉求，就是我的贷款需要申请一个延展期，在不减... | `kaka_self_service` | no_select | 0.020 | `doudou_self_service` 0.019 |
| 我要看一下借款，我要借款合同。；好，然后我要查看合同，然后我要开发票。；合同你发到我邮箱里面吗？我自己也能看得到，我在平台里也能看得到哈。；那没有，我就是要开发票，所有每一笔的交易还款，帮我开下发票。... | `doudou_self_service` | no_select | 0.024 | `kaka_self_service` 0.022 |

### `loan_consultation` 贷款咨询
- contexts：12；confident：0；low_confidence：1；no_select：11。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，今天我收到了一条卡卡贷融的短信，但是我今天的还款已经还了。我想问我在你们那边还有别的借款吗？为什么你们会发这条短信给我？；那卡卡贷融是哪里的？；不是你们这边的是吧？因为百度上搜卡卡贷常是你们。我... | `eligibility_explanation` | no_select | 0.008 | `reserved_amount_actual_disbursement_gap` 0.006 |
| 你好，我要提前还款，这里说什么预约不让还款，我今天现在就要还。；就是那个叫安逸花底下有个电话，是你们电话，我就拨过来了。 | `document_requirements` | no_select | 0.009 | `reserved_amount_actual_disbursement_gap` 0.009 |

### `loan_dispute_refund` 借款争议特殊场景退费
- contexts：4；confident：0；low_confidence：0；no_select：4。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我的账单已经结清了。你们上次说返我多余的利息，返我100块钱是2900，那个账单5000多。我已经找了你们人工，让你们给我返款。那个5000块钱的得多收我的利息，不然我举报了，不然我打电话了。；他给我... | `claimed_unauthorized_normal_process` | no_select | 0.007 | `non_principal_fee_special_application` 0.006 |
| 你好，多扣的钱，然后现在需要人工给我核实过后退过来呀；前天吧，我现在也不太清楚了，这个事情已经两天了，一直打电话一直说，退到今天也还没退呀；那行，我给你们上传是吧，上传完之后呢，再给你们打电话吗 | `confirm_disputed_loan_order` | no_select | 0.012 | `special_loan_scenario_retention_then_clearance` 0.011 |

### `member_cancel` 取消会员
- contexts：18；confident：0；low_confidence：0；no_select：18。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我这个手机号被无辜扣款了一个99元的消费，他说你们这边扣款的。；退款，然后解决这个。；对，还有就是把我的退订了。；那99块钱多久到账？；不是刚刚可以退款的吗？；为什么不能退？你这个是合规的吗？；好的，... | `no_record` | no_select | 0.000 | `not_needed_deferred` 0.000 |
| 你好，麻烦你把我这个会员取消掉，一直在扣款59一个月，有什么意义呢？；我这个会员不起作用，一直在扣款。豆豆钱APP我都卸载了，所以说没必要用这个会员了。；那你赶紧给我取消掉吧。 | `no_record` | no_select | 0.013 | `retain_fail` 0.013 |

### `member_refund` 退会员费用
- contexts：18；confident：0；low_confidence：0；no_select：18。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你看那个昨天晚上我不小心点了，好像点了个优享卡，你帮我取消吧，好像就办了两个；嗯，你帮我取消了；嗯，不需要，谢谢，他是7天之内可以取消的对吧；嗯，对你帮我取消吧。嗯，那个你每个月都不用哈，都不要扣我的... | `retain_success` | no_select | 0.000 | `auto_renewal_cancel` 0.000 |
| 我这个手机号被无辜扣款了一个99元的消费，他说你们这边扣款的。；退款，然后解决这个。；对，还有就是把我的退订了。；那99块钱多久到账？；不是刚刚可以退款的吗？；为什么不能退？你这个是合规的吗？；好的，... | `music_fitness_used` | no_select | 0.007 | `retain_success` 0.000 |

### `no_quota_issue` 无额度问题
- contexts：7；confident：0；low_confidence：0；no_select：7。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 请问豆豆钱有多少额度？；刚刚有个电话叫我加他微信，发一个APP给我，说有1万到8万的额度，是真的不？；好的。我打电话就是想咨询一下。；我现在就不加他微信了，我跟他说挂掉五分钟再打给我，我先问一下你们。... | `withdrawal_quota_zero` | no_select | 0.028 | `marketing_invited_no_quota` 0.014 |
| 你好，我想问一下我这里面还有额度可借吗？；我是那个里面的账户，没有额度啊。；这不写了吗？暂时无法获取额度。我记得以前借过钱，借过5000，然后直接就还完了。 | `ops_ticket` | no_select | 0.028 | `no_quota_after_clearance` 0.027 |

### `overdue_negotiation` 协商还款
- contexts：70；confident：0；low_confidence：0；no_select：70。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我想咨询一下，我现在还款已经资金周转不过来了，后面几期的利息又很高。我现在平台也转不出钱来，朋友都已经借完了。你们这个还款如果一次性还清的话，能不能帮我把后面的利息减免了？；对，我已经没办法每期... | `pre_overdue` | no_select | 0.000 | `early_overdue` 0.000 |
| 你好，我想查一下我在你家平台有没有欠款？；你这个2万元可以做什么减免吗？ | `pre_overdue` | no_select | 0.000 | `early_overdue` 0.000 |

### `post_loan_verification` 核实贷后信息
- contexts：6；confident：0；low_confidence：1；no_select：5。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 请问豆豆钱有多少额度？；刚刚有个电话叫我加他微信，发一个APP给我，说有1万到8万的额度，是真的不？；好的。我打电话就是想咨询一下。；我现在就不加他微信了，我跟他说挂掉五分钟再打给我，我先问一下你们。... | `verify_account` | no_select | 0.000 | `verify_staff` 0.000 |
| 你好，我当时跟咱们协商了停催，并且屏蔽了除我本人以外的联系人，但刚才就有一个咱们这的机器人给我打电话，说什么律师函。；是不是也有系统的电话？；但是刚才真的是你们这的，他说维信金科，然后又说这个律师函，... | `verify_institution` | no_select | 0.007 | `verify_account` 0.000 |

### `premium_card_inquiry` 优享卡咨询
- contexts：10；confident：0；low_confidence：0；no_select：10。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 今天扣了我两笔钱，一个八十九，一个是两千多块钱。我想看一下这两笔钱。 | `not_purchased` | no_select | 0.000 | `purchased_inquire` 0.000 |
| 你好，你们当时说给我一个优惠券，怎么没给我呢？；哦哦哦，那我昨天账单到了没看见，一看没有券，正好钱不够。；我现在存上，你没有券我一看我的钱不够，我存上也没用啊？正好今天昨天凌晨才给我打过来的钱。这样的... | `not_purchased` | no_select | 0.000 | `purchased_inquire` 0.000 |

### `quota_consultation` 额度咨询
- contexts：7；confident：0；low_confidence：0；no_select：7。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 请问豆豆钱有多少额度？；刚刚有个电话叫我加他微信，发一个APP给我，说有1万到8万的额度，是真的不？；好的。我打电话就是想咨询一下。；我现在就不加他微信了，我跟他说挂掉五分钟再打给我，我先问一下你们。... | `max_quota` | no_select | 0.011 | `escalate_ops` 0.010 |
| 这个豆豆钱，我现在没有额度可以用，你们可不可以帮我反馈一下，再给我一笔额度啊？；不是，我意思是我很着急，但是我想帮我再给你们上级申请一下。；那个我现在申请不了。；我意思是你帮我上报一下，然后看上面怎么... | `max_quota` | no_select | 0.011 | `escalate_ops` 0.011 |

### `repayment_method_inquiry` 咨询还款方式
- contexts：79；confident：0；low_confidence：3；no_select：76。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好你好，我想核实一下你们的这个账号。 | `auto_deduction_detail` | no_select | 0.000 | `manual_repayment_path` 0.000 |
| 你好，我叫曹碧安。我现在在豆豆钱平台上面逾期的嘛，现在我想核实一下，你们那边有一个专员联系我，叫我存钱到这个账号：15203607980086。 | `auto_deduction_detail` | no_select | 0.000 | `manual_repayment_path` 0.000 |

### `repayment_result_query` 查询还款结果
- contexts：77；confident：0；low_confidence：1；no_select：76。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 今天扣了我两笔钱，一个八十九，一个是两千多块钱。我想看一下这两笔钱。 | `repayment_success` | no_select | 0.000 | `repayment_processing` 0.000 |
| 你好，您帮我查一下我这个账户总结清的金额是多少？；帮我看一下总的是多少。；是在哪里呢？ | `repayment_success` | no_select | 0.000 | `repayment_processing` 0.000 |

### `repayment_status_issue` 还款状态异常
- contexts：46；confident：0；low_confidence：5；no_select：41。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 我问一下，我暂时还没有逾期吧；今天是4号了啊。那我问一下，为什么我没有逾期，为什么一个劲的给我打电话呢；那前段时间2号3号的时候也有，为什么会这样子呢？你们已经严重影响到我的正常生活了，知道吗；我知道... | `failure_channel_corporate_payment` | no_select | 0.011 | `failure_insufficient_balance_sufficient_now` 0.010 |
| 你好，我问一下，为什么我这边钱扣了，但是你们平台上还有账单呢？我已经全部结清了。；那我需不需要注销什么的？；不是，我是说还清了之后，需不需要注销？ | `update_in_progress` | no_select | 0.012 | `failure_rule_not_due` 0.011 |

### `special_account_cancellation` 特殊场景注销账户
- contexts：15；confident：0；low_confidence：0；no_select：15。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，我想把这个豆豆钱的账户号那些都给我取消了。 | `direct_to_debt_company` | no_select | 0.000 | `request_settlement_proof` 0.000 |
| 你好，我之前在豆豆钱上借的款，我想查一下我现在都是还清了嘛，因为我看不到最近期要还款的记录。；那我再不用这个软件了，是怎么操作？；我借钱比较频繁，你们也不放款了，正好结清了，我就不用了。；因为你们不放... | `direct_to_debt_company` | no_select | 0.010 | `submit_other_ticket` 0.007 |

### `stop_collection` 要求停催
- contexts：50；confident：0；low_confidence：0；no_select：50。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 你好，就我之前办的那个缓催，然后今天到期了，我想再办十天。；对，然后再帮我申请。；主要是什么呢？就是我这两天有那个培训。然后可能我接电话就不太方便。；我把我那个征信给你可以吗？；那我怎么发呢？；那我得... | `ai_collection_early` | no_select | 0.000 | `ivr_collection` 0.000 |
| 你好，我想查询一下我在你们平台的剩余本金是多少？；现在我的欠款金额是多少？；对，之前我们已经协商好了。；就是说缓催一年，一年过后。；那我想确认一下，屏蔽日期是2025年12月5号对吗？ | `ai_collection_early` | no_select | 0.000 | `ivr_collection` 0.000 |

### `value_added_service_inquiry` 增值服务咨询
- contexts：10；confident：0；low_confidence：0；no_select：10。
| customer context | selected branch | status | score | runner_up |
|---|---|---|---:|---|
| 今天扣了我两笔钱，一个八十九，一个是两千多块钱。我想看一下这两笔钱。 | `explain_fuqiang_notary` | no_select | 0.000 | `explain_legal_basis` 0.000 |
| 你好，今天早上众安保险怎么又从我这边扣了274块钱？；你那边能联系吗？我打电话过去都是智能语音，找不到人工。；现在是不是还没上班？ | `explain_zhonghui_insurance` | no_select | 0.011 | `explain_fuqiang_notary` 0.000 |
