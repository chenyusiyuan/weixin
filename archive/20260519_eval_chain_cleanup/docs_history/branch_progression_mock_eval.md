# Skill Branch 递进话术 Mock 评测

- 生成时间：2026-04-27 17:19:36
- 口径：每个 `branch_conditions` 生成一组递进用户话术，在同一个 skill 内选择最匹配 branch，检查是否回到预期 `variant`。
- 注意：这是离线 smoke test；生产链路中 `expr` 可确定性选择，`hint` 分支仍是传给 LLM 的软提示。

## 总览

- Skill 总数：54；有分支 skill：49；无分支 skill：5。
- Branch case：322；通过：322；低置信：0；失败：0。
- Expr 确定性分支：65；实际 evaluator 通过：65；失败：0。
- Runtime 口径：expr_runtime=64，expr_or_hint=1，expr_needs_slots_or_quotes=0，hint_soft=257。

## 异常清单

- 未发现错选、低置信或明显 expr 风险。

## 逐个 Skill

### `account_cancellation` 注销账户
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `doudouqian_self_service` | `doudouqian_self_service` | `-` | 0.719 | hint_soft | 我的情况是：客户坚持注销（豆豆钱）。补充一下，优先引导APP自助操作"我的-设置-注销账户"或发送短信链接；坚持人工操作且提及投诉则升级二线 |
| `kakaday_manual_cancel` | `kakaday_manual_cancel` | `-` | 0.661 | hint_soft | 我的情况是：客户坚持注销（卡卡贷/维信闪贷）。补充一下，可操作人工注销，需客户提供身份证号，告知注销事项后确认执行 |
| `cannot_cancel_outstanding` | `cannot_cancel_outstanding` | `-` | 0.532 | hint_soft | 我的情况是：客户有未结清欠款。补充一下，告知所有欠款结清后方可注销 |
| `escalate_to_tier2` | `escalate_to_tier2` | `-` | 0.546 | hint_soft | 我的情况是：客户提及投诉（豆豆钱）。补充一下，建"投诉工单-内部"升级二线处理 |

### `acknowledgement` 应答确认
- 无 `branch_conditions`，跳过 branch mock。

### `bill_date_credit_impact` 账单日还款是否影响征信
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `normal_repayment_credit` | `normal_repayment_credit` | `-` | 0.626 | hint_soft | 我的情况是：客户询问正常还款是否上征信。补充一下，说明正常按时还款有积累良好征信的作用 |
| `overdue_credit_reporting` | `overdue_credit_reporting` | `-` | 0.609 | hint_soft | 我的情况是：客户询问逾期多久上征信。补充一下，说明逾期会按监管要求上报，建议按时还款 |
| `existing_overdue_credit_repair` | `existing_overdue_credit_repair` | `-` | 0.663 | hint_soft | 我的情况是：客户已有逾期，询问如何消除征信记录。补充一下，建议尽快还清逾期款项，征信记录保留期限按央行规定执行 |
| `repayment_day_failed_sms_credit_concern` | `repayment_day_failed_sms_credit_concern` | `-` | 0.746 | hint_soft | 我的情况是：还款日当天扣款失败短信，客户担心已上征信。补充一下，递进话术：先说明今天既是还款日也是系统扣款日，扣款失败短信主要是提醒客户及时处理。，如果客户在还... |
| `repayment_day_collection_call_credit_concern` | `repayment_day_collection_call_credit_concern` | `-` | 0.799 | hint_soft | 我的情况是：还款日当天收到电话提醒逾期，客户担心征信。补充一下，先为提醒带来的体验道歉，再说明只要还款日当天成功还款即可，不要把提醒电话等同于已经上征信。，建议... |
| `sufficient_balance_not_deducted_credit_concern` | `sufficient_balance_not_deducted_credit_concern` | `-` | 0.802 | hint_soft | 我的情况是：客户晚上才存钱或余额充足但系统没扣，担心影响征信。补充一下，如果客户称因我司原因未及时扣款并影响征信，需引导提供当日卡内余额充足证明。，后续建议客户... |
| `refuse_evidence_for_credit_check` | `refuse_evidence_for_credit_check` | `-` | 0.797 | hint_soft | 我的情况是：客户不接受提供征信凭证，认为是平台问题。补充一下，解释征信报告属于客户个人隐私，我司无法直接查询完整报告。，需要客户先确认是否实际产生影响；若没有影... |
| `repeated_credit_query_concern` | `repeated_credit_query_concern` | `-` | 0.806 | hint_soft | 我的情况是：客户担心不能每次都查询征信。补充一下，安抚客户不需要每次还款都查询征信；本次如客户特别担心，可后续自行确认。，如果本次没有异常，也能说明账单日正常还... |

### `bill_deduction_query` 查询账单扣款情况
- 分支：9；通过：9；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `deduction_success` | `deduction_success` | `-` | 0.549 | hint_soft | 我的情况是：账单已扣款成功。补充一下，告知扣款成功时间和金额，账单已更新 |
| `deduction_pending` | `deduction_pending` | `-` | 0.628 | hint_soft | 我的情况是：账单待扣款，未到还款日。补充一下，告知还款日及预计扣款时间，提醒保持余额充足 |
| `deduction_failed` | `deduction_failed` | `-` | 0.570 | hint_soft | 我的情况是：账单扣款失败。补充一下，转入还款失败处理流程，定位失败原因 |
| `bill_overdue` | `bill_overdue` | `-` | 0.584 | hint_soft | 我的情况是：账单已逾期。补充一下，告知逾期情况，建议尽快还款避免影响征信 |
| `bill_deduction_amount_matched` | `bill_deduction_amount_matched` | `-` | 0.775 | hint_soft | 我的情况是：客户提供扣款日期和金额，系统核实为账单扣款。补充一下，递进话术：先确认客户反馈的扣款时间和金额，再查询在偿订单及近期账单明细。，若金额与账单扣款匹配... |
| `value_added_service_deduction_matched` | `value_added_service_deduction_matched` | `-` | 0.833 | hint_soft | 我的情况是：客户反馈被扣一笔钱，系统核实为增值业务或活动服务扣款。补充一下，递进话术：先说明已查询到客户购买了对应服务，再告知服务名称和金额。，如客户进一步质疑... |
| `no_internal_deduction_record` | `no_internal_deduction_record` | `-` | 0.821 | hint_soft | 我的情况是：客户反馈被扣款但系统未查询到对应扣款记录。补充一下，告知目前未查询到对应扣款情况，请客户在被扣款银行卡，APP，中查看扣款主体、商户名称、时间和金额... |
| `known_external_deduction_entity` | `known_external_deduction_entity` | `-` | 0.808 | hint_soft | 我的情况是：客户已能提供扣款主体且主体非我司。补充一下，告知这笔款项非我司扣费，建议联系对应扣款主体客服核实。，如本地知识中有对应主体联系方式，可提供联系方式和... |
| `unknown_external_deduction_entity` | `unknown_external_deduction_entity` | `-` | 0.772 | hint_soft | 我的情况是：客户无法确认扣款主体，且系统核实非我司扣款。补充一下，告知这笔款项非我司扣费，建议联系银行或对应扣款主体协助查询。，不要直接判断为我司异常扣款，也不... |

### `cancel_credit_authorization` 注销授信额度
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：4/4。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `self_operated_can_cancel` | `self_operated_can_cancel` | `self_operated_can_cancel` | 0.358 | expr_runtime | 我的情况是：自营机构且全部结清——可办理注销，提交注销申请工单 |
| `self_operated_has_loan` | `self_operated_has_loan` | `self_operated_has_loan` | 0.371 | expr_runtime | 我的情况是：自营机构但有未结清贷款——告知需全部还清后才能注销 |
| `non_self_operated` | `non_self_operated` | `non_self_operated` | 0.409 | expr_runtime | 我的情况是：非自营机构——引导客户联系对应资方办理，提供资方联系方式 |
| `explain_difference` | `explain_difference` | `explain_difference` | 0.434 | expr_runtime | 我的情况是：客户混淆授信额度和贷款申请记录——解释两者区别，贷款申请记录不可删除 |

### `cancel_value_added_service` 取消增值服务
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `already_closed_no_charge` | `already_closed_no_charge` | `-` | 0.696 | hint_soft | 我的情况是：放款失败或加速失败。补充一下，告知放款失败/加速失败系统默认关闭订单不扣款，引导在APP端刷新或重新登录查看，无需操作取消 |
| `cancel_before_charge` | `cancel_before_charge` | `-` | 0.682 | hint_soft | 我的情况是：未扣款且未到期自动取消前，客户坚持取消。补充一下，挽留无果支持取消，告知加速卡服务可为贷款加速，建议考虑保留 |
| `pending_deduction_dispute` | `pending_deduction_dispute` | `-` | 0.690 | hint_soft | 我的情况是：已放款且加速成功，未批扣成功。补充一下，权益已生效，客户要求取消，建超权限工单升级主管处理，沟通无果可申请退款 |
| `retention_success` | `retention_success` | `-` | 0.520 | hint_soft | 我的情况是：挽留成功。补充一下，说明加速卡权益价值，确认客户保留 |
| `confirmed_service_still_cancel` | `confirmed_service_still_cancel` | `-` | 0.752 | hint_soft | 我的情况是：客户确认增值服务活动后仍坚持取消。补充一下，客户回复好了/ok/是的/好/嗯等确认后，继续询问取消原因并按未扣款、已生效、加速失败等状态分流处理 |

### `card_rebinding` 换绑银行卡
- 分支：3；通过：3；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `app_path_not_found` | `app_path_not_found` | `-` | 0.683 | hint_soft | 我的情况是：客户反映APP操作找不到入口。补充一下，再次详细说明路径：我的，→，我的银行卡，→，右上角三个点 |
| `card_rebinding_failed` | `card_rebinding_failed` | `-` | 0.650 | hint_soft | 我的情况是：客户反映换卡失败。补充一下，告知可在服务时间联系客服协助处理，转人工或记录工单 |
| `cannot_operate_for_customer` | `cannot_operate_for_customer` | `-` | 0.787 | hint_soft | 我的情况是：客户要求客服直接代操作换绑。补充一下，出于账户和资金安全，客服不能直接代客户换绑银行卡；引导客户本人在APP按路径操作，遇到失败再记录具体报错协助处... |

### `channel_check` 通话状态确认
- 无 `branch_conditions`，跳过 branch mock。

### `clearance_certificate` 开具结清证明
- 分支：6；通过：6；低置信：0；失败：0；expr evaluator：6/6。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `not_cleared` | `not_cleared` | `not_cleared` | 0.500 | expr_runtime | 我的情况是：订单未结清——告知需结清后次日才可在APP开具，引导先还款 |
| `self_service` | `self_service` | `self_service` | 0.397 | expr_runtime | 我的情况是：结清2年内——优先引导APP自助开具，发路径短信 |
| `agent_assist` | `agent_assist` | `agent_assist` | 0.430 | expr_runtime | 我的情况是：结清超2年——客服协助开具，需提供邮箱，1-3工作日发送 |
| `official_issuance` | `official_issuance` | `official_issuance` | 0.419 | expr_runtime | 我的情况是：不接受自助或需要资方章——客服协助申请，1-5工作日发至邮箱 |
| `system_failed` | `system_failed` | `system_failed` | 0.340 | expr_runtime | 我的情况是：系统提示开具失败——按升级流程处理 |
| `identify_target_order` | `identify_target_order` | `identify_target_order` | 0.641 | expr_runtime | 我的情况是：客户只说XX年XX月XX日办理的那笔贷款时，先核对并确认目标订单，再判断是否已结清、结清是否超过2年，以及走APP自助或客服代办路径 |

### `close_pre_reminder` 关闭预提醒服务
- 分支：3；通过：3；低置信：0；失败：0；expr evaluator：3/3。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `multi_order` | `multi_order` | `multi_order` | 0.448 | expr_runtime | 我的情况是：客户名下多笔订单——说明每笔订单都会提醒，查询客户良好还款记录后尝试留存 |
| `no_ivr_record` | `no_ivr_record` | `no_ivr_record` | 0.492 | expr_runtime | 我的情况是：IVR提示"对应业务号无客户信息"——该业务号从未有IVR提醒，尝试其他业务号或告知无需操作 |
| `proceed_close` | `proceed_close` | `proceed_close` | 0.337 | expr_runtime | 我的情况是：客户坚持关闭——直接操作IVR预提醒停催 |

### `closing` 结束语
- 无 `branch_conditions`，跳过 branch mock。

### `collection_complaint` 投诉催收
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：4/4。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `high_frequency` | `high_frequency` | `high_frequency` | 0.400 | expr_runtime | 我的情况是：催收频次过高——核实系统记录，解释催收合理性，协商停催方案 |
| `bad_attitude` | `bad_attitude` | `bad_attitude` | 0.389 | expr_runtime | 我的情况是：态度恶劣——安抚为主，收集凭证（如录音），提交催收投诉工单 |
| `violent_collection` | `violent_collection` | `violent_collection` | 0.523 | expr_runtime | 我的情况是：暴力催收/上门/威胁/工作人员威胁上门——严肃处理，明确公司立场，收集证据，发催收投诉工单并升级 |
| `expose_contacts` | `expose_contacts` | `expose_contacts` | 0.451 | expr_runtime | 我的情况是：爆通讯录——明确告知公司无法获取通讯录，属虚假投诉则解释，属真实则升级处理 |

### `contract_retrieval` 调取合同
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：8/8。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `tier1_active` | `tier1_active` | `tier1_active` | 0.549 | expr_runtime | 我的情况是：还款中未逾期（一线）——询问原因，尝试解决，引导APP查看路径【我的-借款记录-查看合同】 |
| `tier1_overdue` | `tier1_overdue` | `tier1_overdue` | 0.466 | expr_runtime | 我的情况是：还款中已逾期（一线）——询问原因，引导APP查看，坚持则升级二线 |
| `tier2_cleared` | `tier2_cleared` | `tier2_cleared` | 0.481 | expr_runtime | 我的情况是：已结清订单（二线）——发送电子合同至邮箱，1-3工作日处理 |
| `cancelled_retention_dispute` | `cancelled_retention_dispute` | `cancelled_retention_dispute` | 0.619 | expr_runtime | 我的情况是：客户认为注销后仍应保留所有合同，或以发票/费用信息反问为何没有个人信息时，按注销后个人信息删除或匿名化口径解释，客户坚持则升级 |
| `account_cancelled` | `account_cancelled` | `account_cancelled` | 0.635 | expr_runtime | 我的情况是：账户已注销——依据《国家标准GB/T，35273-2020》第8.5条说明，数据已处理，无法提供 |
| `paper_copy` | `paper_copy` | `paper_copy` | 0.485 | expr_runtime | 我的情况是：要求纸质合同——说明只提供电子版，纸质如有需要引导线下公证 |
| `material_collection` | `material_collection` | `material_collection` | 0.642 | expr_runtime | 我的情况是：客户追问需要哪些材料时，说明需核身并确认订单、合同范围、接收邮箱；涉及诉讼或监管用途的，记录用途并升级二线处理 |
| `all_contracts_request` | `all_contracts_request` | `all_contracts_request` | 0.625 | expr_runtime | 我的情况是：客户要求当时所有合同时，先确认订单范围和合同类型，可提供电子合同的按邮箱发送，超权限或无法确认的转二线 |

### `credit_inquiry` 征信问题咨询
- 分支：18；通过：18；低置信：0；失败：0；expr evaluator：6/6。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `unauthorized_query` | `unauthorized_query` | `unauthorized_query` | 0.451 | expr_runtime | 我的情况是：未授权查征信——解释所有查询均需授权，引导确认授权记录，安抚情绪 |
| `multiple_queries` | `multiple_queries` | `multiple_queries` | 0.467 | expr_runtime | 我的情况是：多次查征记录——解释匹配多资方需多次查询，属正常流程，不影响最终授信 |
| `overdue_impact` | `overdue_impact` | `overdue_impact` | 0.453 | expr_runtime | 我的情况是：逾期影响征信——说明逾期上报规则，宽限期规则，建议按时足额还款 |
| `reporting_rules` | `reporting_rules` | `reporting_rules` | 0.516 | expr_runtime | 我的情况是：征信上报规则咨询——说明还款日当天显示逾期属系统延迟，实际未逾期不影响征信 |
| `credit_score` | `credit_score` | `credit_score` | 0.385 | expr_runtime | 我的情况是：征信评分咨询——解释评分影响因素，提供改善建议 |
| `credit_inquiry_general` | `credit_inquiry_general` | `credit_inquiry_general` | 0.372 | expr_runtime | 我的情况是：其他征信问题——详细了解情况后针对性解答 |
| `credit_update_timeline_after_correction` | `credit_update_timeline_after_correction` | `-` | 0.755 | hint_soft | 我的情况是：客户询问修改后征信多久更新或催促更新。补充一下，话术主干：说明我司核实无误后会第一时间报送更正信息，后续由人民银行征信系统统一处理。，告知通常可在申... |
| `guarantee_compensation_reporting` | `guarantee_compensation_reporting` | `-` | 0.726 | hint_soft | 我的情况是：客户询问逾期记录下为什么还有担保代偿或特殊交易类型。补充一下，根据人民银行二代征信中心数据采集规则，贷款完整信息需如实上报，包含转担保、担保代偿或特... |
| `cannot_delete_valid_credit_record` | `cannot_delete_valid_credit_record` | `-` | 0.811 | hint_soft | 我的情况是：客户要求马上还款并删除逾期记录，或质疑担保代偿记录不一致。补充一下，说明担保公司根据账单还款情况按规则自动上报人民银行征信中心。，不承诺删除逾期、担... |
| `no_grace_period_credit_reporting` | `no_grace_period_credit_reporting` | `-` | 0.806 | hint_soft | 我的情况是：客户询问逾期多久会上征信或是否有宽限期。补充一下，说明逾期会按规则上报，具体以征信报告显示为准。，建议客户按时足额还款，避免逾期后申请修改征信失败，... |
| `no_credit_report_sms_notice` | `no_credit_report_sms_notice` | `-` | 0.758 | hint_soft | 我的情况是：客户称未收到征信上报通知短信。补充一下，说明借款后的还款记录、逾期或担保代偿会按规则如实上报，通常不一定单独发送“上报成功”短信。，具体征信情况以人... |
| `repayment_day_deduction_failed_credit_concern` | `repayment_day_deduction_failed_credit_concern` | `-` | 0.716 | hint_soft | 我的情况是：还款日当天扣款失败或收到提醒，客户担心已经影响征信。补充一下，递进话术：先说明还款日/账单日当天系统扣款失败提醒主要是提醒客户及时处理。，如果客户在... |
| `customer_refuses_credit_evidence` | `customer_refuses_credit_evidence` | `-` | 0.779 | hint_soft | 我的情况是：客户不接受提供凭证，质疑为什么要自己提供征信报告。补充一下，说明征信报告属于客户个人隐私，我司无法直接查询客户完整征信报告。，需要客户确认是否实际产... |
| `excessive_query_concern` | `excessive_query_concern` | `-` | 0.806 | hint_soft | 我的情况是：客户质疑征信查询次数过多或每次还款都要查征信。补充一下，安抚客户对征信查询次数的担忧，说明本次账单日还款判断并不要求客户每次还款都查询征信。，可引导... |
| `student_borrower_credit_dispute` | `student_borrower_credit_dispute` | `-` | 0.788 | hint_soft | 我的情况是：客户称贷款时是学生，逾期后要求修改征信。补充一下，告知平台不支持向学生身份提供借款，借贷前需签署非在校学生承诺。，对客户反馈的问题，收集最新征信报告... |
| `compensation_invoice_or_detail_request` | `compensation_invoice_or_detail_request` | `-` | 0.818 | hint_soft | 我的情况是：客户要求提供代偿记录明细或代偿发票，威胁投诉偷税漏税。补充一下，说明担保公司代偿本质是替客户向银行履行债务清偿义务，属于风险处置流程，不一定符合商品... |
| `reporting_entity_qualification_dispute` | `reporting_entity_qualification_dispute` | `-` | 0.802 | hint_soft | 我的情况是：客户质疑上报方无资质。补充一下，告知合作资金方或金融机构具备合法合规上报征信的资质和能力，征信记录由资金提供方等合规合作机构按央行规定上报。，客户仍... |
| `external_policy_sms_verification` | `external_policy_sms_verification` | `-` | 0.777 | hint_soft | 我的情况是：客户收到外部信托或资方短信，询问征信处理政策是否真实有效。补充一下，先提醒客户谨防不法分子借政策名义诈骗。，建议客户直接联系短信内对应的官方机构确认... |

### `credit_modification` 修改征信
- 分支：7；通过：7；低置信：0；失败：0；expr evaluator：7/7。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `self_operated` | `self_operated` | `self_operated` | 0.469 | expr_runtime | 我的情况是：自营机构（上海小贷、成都小贷、维仕担保）——建征信问题工单，内部处理 |
| `non_self_operated` | `non_self_operated` | `non_self_operated` | 0.419 | expr_runtime | 我的情况是：非自营机构——说明需联系对应资方处理，提供资方联系方式 |
| `genuine_error` | `genuine_error` | `genuine_error` | 0.495 | expr_runtime | 我的情况是：确属系统错误或非本人原因——协助提交征信异议申请，1-3工作日处理 |
| `own_fault` | `own_fault` | `own_fault` | 0.514 | expr_runtime | 我的情况是：客户自身逾期导致——解释征信如实记录原则，婉拒修改，告知还清后影响逐步减轻 |
| `special_circumstances` | `special_circumstances` | `special_circumstances` | 0.491 | expr_runtime | 我的情况是：重大疾病/自然灾害等特殊情况——收集证明材料，上报审核，有一定开绿灯可能性 |
| `clarify_institution_and_record` | `clarify_institution_and_record` | `clarify_institution_and_record` | 0.591 | expr_runtime | 我的情况是：客户只说是XX家的贷款或让客服看一下时，先确认征信显示的管理机构、订单和逾期记录，再判断自营/非自营路径 |
| `repeat_dispute_escalation` | `repeat_dispute_escalation` | `repeat_dispute_escalation` | 0.636 | expr_runtime | 我的情况是：客户对之前反馈的征信问题不满意并要求改过来时，先查询历史工单和处理结论，复述如实上报原则；确有新证据则补充材料升级征信异议 |

### `deactivated_customer_service` 已注销客户进线服务
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `send_dispute_sms` | `send_dispute_sms` | `-` | 0.610 | hint_soft | 我的情况是：客户反映发票或可举证问题。补充一下，推送【异议处理】短信，告知客户由专员联系处理，短信时效72小时 |
| `credit_report_flow` | `credit_report_flow` | `-` | 0.550 | hint_soft | 我的情况是：客户反映征信问题。补充一下，一线可优先询问办理事项，正常受理征信问题流程 |
| `reject_and_escalate` | `reject_and_escalate` | `-` | 0.586 | hint_soft | 我的情况是：客户无法举证其他场景。补充一下，再次婉拒，客户不接受可推送【异议处理】短信，由专员处理 |
| `handle_current_order_only` | `handle_current_order_only` | `-` | 0.603 | hint_soft | 我的情况是：注销后重新注册客户进线。补充一下，仅受理当前注册业务，一线无法查询相关订单直接升级 |

### `deduction_issues` 扣款相关问题咨询
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `next_deduction_date` | `next_deduction_date` | `-` | 0.594 | hint_soft | 我的情况是：客户询问下次扣款时间。补充一下，根据账单信息告知下次还款日及预计扣款时间 |
| `amount_mismatch` | `amount_mismatch` | `-` | 0.594 | hint_soft | 我的情况是：客户反映扣款金额与预期不符。补充一下，核查账单明细，逐项解释费用构成 |
| `duplicate_deduction` | `duplicate_deduction` | `-` | 0.636 | hint_soft | 我的情况是：客户反映被重复扣款。补充一下，查询扣款记录，确认是否存在重复，如确认重复需发起退款处理 |
| `channel_maintenance` | `channel_maintenance` | `-` | 0.810 | hint_soft | 我的情况是：客户询问扣款渠道维护导致扣款失败后续处理。补充一下，因我司产品当前是由第三方渠道进行代扣，若遇扣款渠道维护，系统扣不到款项，系统也会自动触发短信提醒... |

### `disbursement_progress` 放款进度查询
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `disbursing_status` | `disbursing_status` | `-` | 0.658 | hint_soft | 我的情况是：系统查询已审核通过，放款中。补充一下，告知预计1-10个工作日到账，最晚到账日期；T+1工作日内安抚等待，超T+1发运维工单 |
| `failed_disbursement` | `failed_disbursement` | `-` | 0.636 | hint_soft | 我的情况是：系统显示已解约/放款失败。补充一下，告知系统综合评估未申请成功，会有短信提醒，提现入口关闭，后续可重新尝试 |
| `delayed_disbursement` | `delayed_disbursement` | `-` | 0.567 | hint_soft | 我的情况是：放款延迟。补充一下，安抚客户，告知系统自动放款无法确认具体时间，加急反馈处理 |
| `partner_disbursement` | `partner_disbursement` | `-` | 0.616 | hint_soft | 我的情况是：导流产品放款（非豆豆钱直接放款）。补充一下，告知合作平台均为持牌金融机构，合法合规，客户已签署协议 |
| `fraud_victim` | `fraud_victim` | `-` | 0.626 | hint_soft | 我的情况是：客户反映被诈骗，要求本金结清。补充一下，引导提供报警回执单，发信息安全工单报备；需减免清贷则升级二线 |

### `early_deduction` 未到还款日被提前扣款
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `genuine_early_deduction` | `genuine_early_deduction` | `-` | 0.610 | hint_soft | 我的情况是：扣款日期确实早于合同约定还款日。补充一下，需升级处理，核查系统扣款规则是否有异常 |
| `product_rule_deduction` | `product_rule_deduction` | `-` | 0.626 | hint_soft | 我的情况是：扣款日期符合产品规则（如提前N天预扣）。补充一下，解释该产品的扣款规则，如提前1-3天预扣属于正常机制 |
| `misunderstanding_due_date` | `misunderstanding_due_date` | `-` | 0.560 | hint_soft | 我的情况是：客户误解还款日与扣款日的区别。补充一下，说明账单日、还款日、扣款日三者的区别 |
| `pre_deduction_sms_notice` | `pre_deduction_sms_notice` | `-` | 0.764 | hint_soft | 我的情况是：客户收到提前扣款短信，询问是否真实或为什么提前扣。补充一下，递进话术：先确认短信提醒是为了减少逾期风险，再解释系统可能在还款日前发起或提醒自动扣款。... |
| `decline_or_close_pre_deduction` | `decline_or_close_pre_deduction` | `-` | 0.692 | hint_soft | 我的情况是：客户要求关闭、不保留或不同意提前扣款。补充一下，先确认客户诉求是“不接受提前扣款提醒/预扣机制”，再解释自动扣款规则与账单还款义务。，如果系统支持关... |
| `early_deduction_failed_credit_fee_concern` | `early_deduction_failed_credit_fee_concern` | `-` | 0.743 | hint_soft | 我的情况是：提前扣款未扣成功，客户担心费用或征信影响。补充一下，递进话术：先说明未扣成功本身不等于已逾期，关键看还款日当天是否按时足额还款。，提醒客户及时补足余... |
| `next_deduction_time_after_failed_attempt` | `next_deduction_time_after_failed_attempt` | `-` | 0.769 | hint_soft | 我的情况是：客户询问今天没扣到后什么时候还会再扣。补充一下，告知系统会根据账单周期和扣款策略再次发起扣款，具体时间以系统为准。，建议客户不要只等待自动扣款，可在... |
| `no_pre_deduction_sms_received` | `no_pre_deduction_sms_received` | `-` | 0.766 | hint_soft | 我的情况是：客户质疑未收到提前扣款短信。补充一下，先安抚并核实手机号、短信拦截和，APP，消息设置；说明短信仅作提醒，不影响客户按账单还款日履约。，如客户称未收... |

### `early_loan_clearance` 提前清贷需求
- 分支：10；通过：10；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `not_support_disbursement_day` | `not_support_disbursement_day` | `-` | 0.827 | hint_soft | 我的情况是：放款当天，不支持提前清贷。补充一下，今天是你的放款日，您的款项已经放款成功。毕竟申请一次也不容易，您也花了不少时间，建议您继续使用，后续按照账单周期... |
| `not_support_near_bill_date` | `not_support_near_bill_date` | `-` | 0.781 | hint_soft | 我的情况是：账单日当天及前后两天，不建议清贷。补充一下，马上就要到您的账单日了，您可以根据实际账单来还款，如果您确实需要提前清贷，建议您账单出来后过几天通过AP... |
| `not_support_last_installment` | `not_support_last_installment` | `-` | 0.752 | hint_soft | 我的情况是：最后一期账单日及以后，不建议清贷。补充一下，您的账单已经是最后一期并且已经出了账单，建议您按照还款日正常还款即可，可以先把钱用在其他您需要的地方 |
| `retention_sufficient_funds` | `retention_sufficient_funds` | `-` | 0.789 | hint_soft | 我的情况是：支持清贷，客户原因为资金充裕。补充一下，{customer_name}，您好，相信您申请借款时也是因为资金需要周转，这边建议您可以按照还款计划按期归... |
| `retention_high_rate` | `retention_high_rate` | `-` | 0.724 | hint_soft | 我的情况是：支持清贷，客户原因为费率高。补充一下，{customer_name}，您好，感谢您的反馈，我们平台是严格遵守国家法律法规，我们的费用标准也都是合法合... |
| `retention_quota_dissatisfied` | `retention_quota_dissatisfied` | `-` | 0.782 | hint_soft | 我的情况是：支持清贷，客户原因为额度不满意。补充一下，{customer_name}，您好，额度方面您不用担心的，是由系统自动审核的，目前的小额度是为您之后的额... |
| `retention_frequent_collection` | `retention_frequent_collection` | `-` | 0.763 | hint_soft | 我的情况是：支持清贷，客户因催收频繁。补充一下，如果您的账单在逾期状态的话，可能是会有工作人员联系您。主要也是建议您尽快还款，避免因为欠款时间过长，影响到您的个... |
| `assist_clearance_no_tag` | `assist_clearance_no_tag` | `-` | 0.740 | hint_soft | 我的情况是：无清贷卡控标签，挽留失败，协助清贷。补充一下，{customer_name}，您好。这笔账单今日结清金额是{clearance_amount}元，从... |
| `card_control_first_attempt` | `card_control_first_attempt` | `-` | 0.813 | hint_soft | 我的情况是：有清贷卡控标签，首次挽留。补充一下，{customer_name}，您好，为防范金融交易风险，确保您的账户安全。目前还在审核中，类似于房贷一样，申请... |
| `card_control_close_tag` | `card_control_close_tag` | `-` | 0.829 | hint_soft | 我的情况是：有清贷卡控标签且有挽留无效关闭卡控标签，协助关闭卡控。补充一下，为了给您提供更好的服务，本次已为您申请处理。因为也是为了防范金融交易风险，确保您的账... |

### `fee_consultation_tier1` 费用咨询（一线）
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `guarantee_fee_legality` | `guarantee_fee_legality` | `-` | 0.774 | hint_soft | 我的情况是：客户质疑担保费违法。补充一下，{customer_name}，请您放心所有担保费用收取都是合法合规并且都是由有资质的融资担保公司收取，具体收费主体您... |
| `same_entity_query` | `same_entity_query` | `-` | 0.782 | hint_soft | 我的情况是：客户质疑担保公司与平台为同一主体。补充一下，担保公司与平台公司是两家独立的主体，经营过程中依法独立运作，并按照监管规定开展业务。利息由放款方收取，担... |
| `bundled_sales_query` | `bundled_sales_query` | `-` | 0.733 | hint_soft | 我的情况是：客户质疑捆绑销售。补充一下，在您申请贷款的时候，如果涉及到有担保方的贷款，是为了提高您贷款增信的要求而设定的。担保合同是依赖贷款合同（主合同）而存在... |
| `irr_rate_explanation` | `irr_rate_explanation` | `-` | 0.775 | hint_soft | 我的情况是：客户询问IRR费率。补充一下，根据相关法律要求，我司所有借款均使用IRR计算方式，为了缓解借款人的还款压力，拆分到了每一期账单分期偿还，但请您放心，... |
| `undisclosed_fee_query` | `undisclosed_fee_query` | `-` | 0.805 | hint_soft | 我的情况是：客户质疑费用未提前告知。补充一下，关于借款过程中重要信息，比如借款金额、还款计划、逾期影响等，在您借款时有对应的特别提示函，重点提醒您的，具体明细您... |
| `fund_occupation_fee_difference` | `fund_occupation_fee_difference` | `-` | 0.786 | hint_soft | 我的情况是：客户询问资金占用费为什么每期不一样。补充一下，资金占用费会随借款本金余额、借款天数、还款计划等因素变化，每期金额可能不同；引导客户查看合同和账单明细... |
| `student_identity_fee_dispute` | `student_identity_fee_dispute` | `-` | 0.759 | hint_soft | 我的情况是：客户称办理贷款时还是学生。补充一下，先安抚并核实借款时身份和订单情况，说明借款申请需本人确认并签署协议；若客户坚持反馈学生身份或资质问题，记录诉求并... |
| `escalate_to_tier2` | `escalate_to_tier2` | `-` | 0.612 | hint_soft | 我的情况是：客户坚持不接受费用解释，要求升级。补充一下，转接二线或高阶坐席进行内诉处理 |

### `fee_consultation_tier2` 费用咨询（二线/高阶内诉）
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `disguised_interest_objection` | `disguised_interest_objection` | `-` | 0.751 | hint_soft | 我的情况是：客户坚持认为担保费是变相利息超过法定上限。补充一下，担保费与利息的收取主体、法律依据、计算方式均不同。利息由持牌金融机构收取，适用央行利率规定；担保... |
| `regulatory_complaint_threat` | `regulatory_complaint_threat` | `-` | 0.793 | hint_soft | 我的情况是：客户声称要向监管部门投诉。补充一下，我们欢迎并尊重您通过合法渠道反映问题。如您认为存在问题，可向中国人民银行、银保监会或地方金融监管局进行投诉。同时... |
| `compliance_document_request` | `compliance_document_request` | `-` | 0.647 | hint_soft | 我的情况是：客户提出费用合规文件要求。补充一下，可告知客户在APP合同页面查阅完整合同，或协助其获取合同复印件 |
| `customer_accepts` | `customer_accepts` | `-` | 0.558 | hint_soft | 我的情况是：客户经充分解释后接受。补充一下，感谢客户理解，询问是否还有其他问题 |
| `persistent_refund_demand` | `persistent_refund_demand` | `-` | 0.562 | hint_soft | 我的情况是：客户始终不接受，坚持退费。补充一下，转入退费流程，由二线评估退费可行性 |

### `fee_detail_query` 查询费用明细及综合费率
- 分支：7；通过：7；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `irr_calculation_explanation` | `irr_calculation_explanation` | `-` | 0.766 | hint_soft | 我的情况是：客户询问综合费率计算方式。补充一下，根据相关法律要求，我司所有借款均使用IRR（内部收益率）计算方式，综合反映借款的实际资金成本，包括利息和其他费用... |
| `high_rate_objection` | `high_rate_objection` | `-` | 0.595 | hint_soft | 我的情况是：客户认为费率过高。补充一下，解释费率合规性，如客户坚持不接受转费用咨询处理 |
| `specific_period_query` | `specific_period_query` | `-` | 0.584 | hint_soft | 我的情况是：客户查询特定期次费用明细。补充一下，提供客户指定期次的详细费用分项说明 |
| `dig_reason_before_statement_query` | `dig_reason_before_statement_query` | `-` | 0.706 | hint_soft | 我的情况是：客户要求查询某笔或名下所有订单明细，但未说明真实原因。补充一下，递进话术：至少两次挖掘查账原因。，第一次可问“冒昧了解下您是什么原因要求查询账单呢？... |
| `repayment_plan_table_request` | `repayment_plan_table_request` | `-` | 0.704 | hint_soft | 我的情况是：客户坚持查询已结清或指定订单账单明细。补充一下，结清3年内订单默认可协助调取还款计划表，告知正常处理时间3个工作日，调取后需回访确认并再次询问查账原... |
| `frontline_rate_query_not_directly_available` | `frontline_rate_query_not_directly_available` | `-` | 0.693 | hint_soft | 我的情况是：一线客户要求查询订单综合费率或所有订单利率。补充一下，一线不直接对客告知费率情况，先挖掘客户真实诉求。，话术递进：先说“客服目前无法查询到，您是遇到... |
| `tier2_rate_query_by_order_age` | `tier2_rate_query_by_order_age` | `-` | 0.732 | hint_soft | 我的情况是：二线或高阶客户要求查询订单综合费率。补充一下，先挖掘原因，告知根因则按实际问题处理。，客户未告知原因时，2021年后订单如客户强烈要求可告知IRR费... |

### `fee_refund_status` 退费未到账情况咨询
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `refund_processing` | `refund_processing` | `-` | 0.601 | hint_soft | 我的情况是：退费申请处理中，未超时效。补充一下，告知处理中，预计时效3-7个工作日，请耐心等待 |
| `refund_remitted` | `refund_remitted` | `-` | 0.629 | hint_soft | 我的情况是：退费已处理，打款中。补充一下，告知已打款，到账时效取决于银行处理速度，一般1-3个工作日 |
| `refund_completed` | `refund_completed` | `-` | 0.542 | hint_soft | 我的情况是：退费已到账。补充一下，告知退费已完成，请查看对应银行卡或账户 |
| `refund_overdue` | `refund_overdue` | `-` | 0.570 | hint_soft | 我的情况是：退费超时效仍未到账。补充一下，需升级处理，核查退费状态并推进处理 |
| `confirm_refund_status_query` | `confirm_refund_status_query` | `-` | 0.717 | hint_soft | 我的情况是：客户确认查询退费进度。补充一下，客户催促退费到账，或回复好了/ok/是的/好/嗯确认后，继续核身并查询退费申请日期、金额、状态和原路退回账户 |

### `fee_refund_tier1` 要求退费（一线）
- 分支：6；通过：6；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `refund_eligible` | `refund_eligible` | `-` | 0.587 | hint_soft | 我的情况是：客户退费诉求符合退费规则。补充一下，按流程发起退费申请，告知退费时效 |
| `refund_not_eligible` | `refund_not_eligible` | `-` | 0.752 | hint_soft | 我的情况是：客户退费诉求不符合退费规则。补充一下，{customer_name}，关于您申请退还{fee_type}的诉求，根据我们的合同约定和相关规定，该费用... |
| `persistent_demand_escalate` | `persistent_demand_escalate` | `-` | 0.628 | hint_soft | 我的情况是：客户情绪激动，坚持退费。补充一下，一线解释后客户仍坚持，转接二线处理 |
| `customer_accepts_no_refund` | `customer_accepts_no_refund` | `-` | 0.569 | hint_soft | 我的情况是：客户接受解释，放弃退费。补充一下，感谢理解，询问是否有其他问题 |
| `frontline_fee_reasonable_explanation` | `frontline_fee_reasonable_explanation` | `-` | 0.797 | hint_soft | 我的情况是：一线首次解释费用合理性。补充一下，话术主干：告知客户申请贷款时相关费用均有展示，需要客户签署并确认合同内容后才会放款。，表述重点是合同展示、客户确认... |
| `frontline_internal_complaint_escalation` | `frontline_internal_complaint_escalation` | `-` | 0.766 | hint_soft | 我的情况是：一线解释后客户不接受，要求领导或更高级人员处理。补充一下，建“投诉工单-内部”升级二线。，递进话术：先安抚“您先消消气”，再告知问题已反馈专员跟进，... |

### `fee_refund_tier2` 要求退费（二线/高阶内诉）
- 分支：15；通过：15；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `partial_refund_negotiation` | `partial_refund_negotiation` | `-` | 0.696 | hint_soft | 我的情况是：客户提出部分退费诉求，可协商。补充一下，充分理解客户诉求后，评估是否可提供部分退费作为让步方案。需在系统权限范围内操作，超出权限需提交工单 |
| `full_refund_evaluation` | `full_refund_evaluation` | `-` | 0.667 | hint_soft | 我的情况是：客户提出全额退费，评估合理性。补充一下，核实退费依据，如客户有合理诉求（如误操作、系统错误等），按流程提交工单申请全额退费审批 |
| `membership_offset` | `membership_offset` | `-` | 0.581 | hint_soft | 我的情况是：客户有会员权益可抵扣。补充一下，查询客户会员信息，评估是否可用会员权益抵扣部分费用 |
| `fraud_claim_refund` | `fraud_claim_refund` | `-` | 0.657 | hint_soft | 我的情况是：客户声称遭遇诈骗或非本人操作。补充一下，需核实客户陈述，收集相关证据（报案记录等），提交工单走特殊退费审批流程 |
| `customer_accepts_proposal` | `customer_accepts_proposal` | `-` | 0.595 | hint_soft | 我的情况是：客户经充分协商后接受方案。补充一下，确认方案，发起退费申请，告知退费时效和退款路径 |
| `no_agreement_reached` | `no_agreement_reached` | `-` | 0.688 | hint_soft | 我的情况是：客户拒绝所有方案，坚持全额退费。补充一下，告知客户已尽力协商，保留投诉权利，记录通话内容作为后续处理依据，必要时上报主管处理 |
| `probe_refund_basis_and_proxy_risk` | `probe_refund_basis_and_proxy_risk` | `-` | 0.664 | hint_soft | 我的情况是：客户引用法务团队、律师、网上信息或朋友退费作为退费依据。补充一下，递进话术：先肯定客户重视合规，再追问依据来源和具体计算方式。，法务团队：请客户说明... |
| `understand_refund_basis_after_verification` | `understand_refund_basis_after_verification` | `-` | 0.703 | hint_soft | 我的情况是：已核身后需要了解用户退费依据。补充一下，递进话术：先问“请问您是通过什么方式了解到这些信息的呢？平台费用都是合法合规的哦”。，如果客户只用“好了/o... |
| `ask_expected_amount_and_bottom_line` | `ask_expected_amount_and_bottom_line` | `-` | 0.709 | hint_soft | 我的情况是：客户不说具体金额，只追问能不能退或凭什么不给退。补充一下，至少一次明确挖掘客户心理预期和金额依据。，可递进使用：“您的需求是什么，我们愿意认真聆听”... |
| `guarantee_fee_or_over_24_negotiation` | `guarantee_fee_or_over_24_negotiation` | `-` | 0.697 | hint_soft | 我的情况是：客户要求退担保费或超24%费用，需要判断是否有方案。补充一下，费用边界：本金和利息不可协商，24%内费用不协商；超24%费用、罚息/延迟支付违约金、... |
| `full_guarantee_fee_refund_objection` | `full_guarantee_fee_refund_objection` | `-` | 0.745 | hint_soft | 我的情况是：客户要求退全部担保费或认为费用不合规不合理。补充一下，递进话术：先表达理解并说明会争取方案，再明确无法承诺全部承担。，解释关怀券/关怀金是公司基于客... |
| `complaint_deescalation_before_external_channel` | `complaint_deescalation_before_external_channel` | `-` | 0.665 | hint_soft | 我的情况是：客户不认可解释并表示投诉或外部反馈。补充一下，先消气和换位思考，再说明双方沟通目的是友好协商解决问题。，覆盖客户表达：不认可解释坚持表示投诉、我就是... |
| `repeated_application_and_price_reduction` | `repeated_application_and_price_reduction` | `-` | 0.669 | hint_soft | 我的情况是：客户认为申请无用、方案不够或要求继续申请。补充一下，递进话术：说明当前方案是已努力申请后的结果，表达持续跟进诚意。，覆盖客户表达：你们老是这么申请来... |
| `customer_demands_higher_minimum_amount` | `customer_demands_higher_minimum_amount` | `-` | 0.770 | hint_soft | 我的情况是：客户明确说方案太少，要求至少退固定金额。补充一下，先确认客户最低可接受金额和依据，记录心理底价。，说明会基于其诉求和公司权限继续反馈评估，但无法承诺... |
| `settlement_execution_after_acceptance` | `settlement_execution_after_acceptance` | `-` | 0.733 | hint_soft | 我的情况是：客户接受关怀方案，需要进入履约或签署协议。补充一下，先确认方案内容、金额、券或关怀金形式，再判断是否需要签署和解协议。，涉及需签署协议的，签署前必须... |

### `greeting_opening` 开场寒暄
- 无 `branch_conditions`，跳过 branch mock。

### `identity_readback` 核身信息回答
- 无 `branch_conditions`，跳过 branch mock。

### `invoice_issuance` 发票开具
- 分支：7；通过：7；低置信：0；失败：0；expr evaluator：7/7。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `doudou_self_service` | `doudou_self_service` | `doudou_self_service` | 0.468 | expr_runtime | 我的情况是：豆豆钱平台——引导APP自助开具，路径：我的-借款记录-查看详情-更多-开发票 |
| `kaka_self_service` | `kaka_self_service` | `kaka_self_service` | 0.445 | expr_runtime | 我的情况是：卡卡贷平台——引导APP自助开具，路径：我的-借款记录-右上角"开发票" |
| `escalate_to_tier2` | `escalate_to_tier2` | `escalate_to_tier2` | 0.455 | expr_runtime | 我的情况是：不接受自助——升级二线做二轮挖需协商，一线无需直接建单开票 |
| `resolve_underlying_issue` | `resolve_underlying_issue` | `resolve_underlying_issue` | 0.488 | expr_runtime | 我的情况是：开票原因可直接解决（如还款疑问）——优先解决根本问题，避免不必要开票 |
| `principal_invoice_not_supported` | `principal_invoice_not_supported` | `principal_invoice_not_supported` | 0.634 | expr_runtime | 我的情况是：客户问为什么本金不支持开具发票时，说明本金属于借款本金返还，不属于平台服务收费项目，开票范围以可开具费用和系统页面为准 |
| `invoice_title_content` | `invoice_title_content` | `invoice_title_content` | 0.624 | expr_runtime | 我的情况是：客户询问发票抬头是否可修改或发票内容能否指定时，引导以APP开票页面支持项为准；已开具或系统不支持修改的，升级二线核查 |
| `unsupported_funder_partner` | `unsupported_funder_partner` | `unsupported_funder_partner` | 0.592 | expr_runtime | 我的情况是：部分资方和合作方不支持发票开具时，向客户说明限制来源，记录具体订单和开票诉求，客户不接受则升级二线 |

### `light_card_cancel_refund` 轻享卡取消退费
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `guide_self_cancel_renewal` | `guide_self_cancel_renewal` | `-` | 0.713 | hint_soft | 我的情况是：客户收到续费扣款短信，坚持取消续费。补充一下，引导通过豆豆钱APP【我的卡券-权益券包-管理-续费管理】关闭续费；或联系服务商400-018-900... |
| `provide_vendor_contact` | `provide_vendor_contact` | `-` | 0.665 | hint_soft | 我的情况是：客户要求取消轻享卡，坚持退费，愿意联系服务商。补充一下，提供服务商联系方式：400-018-9000，人工服务时间9:00-21:00 |
| `non_risk_firm_decline` | `non_risk_firm_decline` | `-` | 0.647 | hint_soft | 我的情况是：客户不接受联系服务商，非风险客户。补充一下，告知这是平台与三方服务商合作服务，需联系服务商协商，我司无法直接操作退费 |
| `risk_client_assist` | `risk_client_assist` | `-` | 0.613 | hint_soft | 我的情况是：客户不接受联系服务商，风险客户。补充一下，协助反馈给服务商处理，预计1-3个工作日，保持电话畅通 |
| `escalate_vendor_dispute` | `escalate_vendor_dispute` | `-` | 0.671 | hint_soft | 我的情况是：客户已联系供应商但不处理或对处理结果不满。补充一下，协助反馈服务商沟通处理，预计1-3个工作日，请耐心等待保持电话畅通 |

### `loan_consultation` 贷款咨询
- 分支：13；通过：13；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `loan_purpose_explanation` | `loan_purpose_explanation` | `-` | 0.636 | hint_soft | 我的情况是：客户咨询贷款用途限制。补充一下，告知仅用于消费，不得用于购房、购车、投资、购买理财产品等 |
| `eligibility_explanation` | `eligibility_explanation` | `-` | 0.666 | hint_soft | 我的情况是：客户咨询申请条件/资质。补充一下，系统根据婚姻状态、职业背景、征信情况等综合评估，不承诺具体通过率 |
| `document_requirements` | `document_requirements` | `-` | 0.745 | hint_soft | 我的情况是：客户咨询申请资料。补充一下，注册实名：身份证正反面、基本资料、人脸识别、银行卡四要素验证，紧急联系人2位；要求银行预留手机号与网银/电话银行/手机银... |
| `disbursement_timeline` | `disbursement_timeline` | `-` | 0.666 | hint_soft | 我的情况是：客户咨询放款时效。补充一下，系统授信常规3天；申请提现审核1-2天；放款一般1-10个工作日，最快当天 |
| `rejection_explanation` | `rejection_explanation` | `-` | 0.632 | hint_soft | 我的情况是：审核被拒或评分不足。补充一下，告知系统综合评分不足，人工无法干预，建议过段时间再尝试申请 |
| `loan_nature_and_lender_explanation` | `loan_nature_and_lender_explanation` | `-` | 0.810 | hint_soft | 我的情况是：客户咨询贷款性质、放贷主体或是否平台自营放贷。补充一下，告知产品是纯线上、无抵押的互联网智能信贷产品。，如客户问“你们公司放贷吗/到底哪个公司发放”... |
| `guarantee_explanation_pre_and_post_loan` | `guarantee_explanation_pre_and_post_loan` | `-` | 0.784 | hint_soft | 我的情况是：客户咨询贷款是否有担保。补充一下，贷前：说明是否需要担保由系统根据客户资质自动判断，申请过程中合同会明确贷款和担保信息。，贷后：根据系统查询结果回复... |
| `max_quota_explanation` | `max_quota_explanation` | `-` | 0.704 | hint_soft | 我的情况是：客户咨询最高额度或可贷额度。补充一下，最高额度可说明为20万，但必须强调具体以系统综合评估结果为准，不承诺客户一定可获得 |
| `reserved_amount_actual_disbursement_gap` | `reserved_amount_actual_disbursement_gap` | `-` | 0.782 | hint_soft | 我的情况是：客户质疑预约借款金额和实际放款金额不一致。补充一下，告知客户借款时签署了相关协议，最终放款金额以实际放款金额为准，提现展示金额仅作参考。，客户情绪激... |
| `application_rejected_data_concern` | `application_rejected_data_concern` | `-` | 0.812 | hint_soft | 我的情况是：客户质疑提交资料后审核不通过或认为平台骗取资料。补充一下，先表达理解和歉意，再说明产品由系统自动审核，综合评分不足时无法通过，人工无法干预。，可说明... |
| `withdrawal_review_and_call_missed` | `withdrawal_review_and_call_missed` | `-` | 0.789 | hint_soft | 我的情况是：客户已提现，咨询审核中多久出结果或审核电话未接。补充一下，已提现审核一般1-2个工作日，具体以产品流程展示时间告知。，审核电话没接到时，安抚客户不用... |
| `approved_disbursement_timeline` | `approved_disbursement_timeline` | `-` | 0.675 | hint_soft | 我的情况是：客户咨询审核通过后多久放款。补充一下，审核通过后一般1-10个工作日左右放款，最快当天到账，具体以实际到账为准 |
| `deep_usage_control_or_media_followup` | `deep_usage_control_or_media_followup` | `-` | 0.757 | hint_soft | 我的情况是：客户深入追问资金用途控制或媒体类问题。补充一下，先确认客户当前操作步骤，必要时查询状态。，未提现时说明提现后仍会再次审核，审核通过后才放款；审核被拒... |

### `loan_dispute_refund` 借款争议特殊场景退费
- 分支：10；通过：10；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `claimed_unauthorized_normal_process` | `claimed_unauthorized_normal_process` | `-` | 0.773 | hint_soft | 我的情况是：客户声称非本人操作，系统显示正常借款流程。补充一下，核查借款申请记录：借款申请是通过您的账号完成的，包括实名认证、人脸识别、合同签署等步骤，全部操作... |
| `confirm_disputed_loan_order` | `confirm_disputed_loan_order` | `-` | 0.753 | hint_soft | 我的情况是：核实客户订单，核身后需要先确认客户争议订单。补充一下，先询问“请问您需要查询哪笔订单呢”，确认订单日期、金额、产品或业务号。，若客户只回答“好了/o... |
| `fraud_with_police_report` | `fraud_with_police_report` | `-` | 0.781 | hint_soft | 我的情况是：客户提供公安报案证明，声称被诈骗。补充一下，收到报案证明后，按照诈骗借款争议流程提交工单，转专项处理团队核查。，告知客户：我们会认真核查，处理结果将... |
| `loan_amount_not_received` | `loan_amount_not_received` | `-` | 0.702 | hint_soft | 我的情况是：客户声称未收到借款金额。补充一下，核查放款记录，确认放款账户和金额。如系统显示已放款，提供放款凭证（银行流水信息），建议客户核查对应银行账户 |
| `induced_loan_claim` | `induced_loan_claim` | `-` | 0.751 | hint_soft | 我的情况是：客户声称是被诱导贷款。补充一下，了解被诱导的具体情况，核查借款申请记录。操作借款时系统均会展示相关信息及确认页面，所有信息均需本人填写上传，合同也需... |
| `confirmed_anomaly` | `confirmed_anomaly` | `-` | 0.570 | hint_soft | 我的情况是：核查后确认存在异常。补充一下，提交工单走特殊退费申请，告知处理时效 |
| `special_loan_scenario_retention_then_clearance` | `special_loan_scenario_retention_then_clearance` | `-` | 0.762 | hint_soft | 我的情况是：特殊借款场景，客户称不需要已放款订单，包含解约失败放款、预约借款、再借一笔、拆单放款悦享金或福利金。补充一下，递进话术：先安抚并挽留，告知已借款成功... |
| `non_principal_fee_special_application` | `non_principal_fee_special_application` | `-` | 0.729 | hint_soft | 我的情况是：客户坚持本金外费用不承担，要求处理费用。补充一下，在特殊借款场景且符合处理条件时，可告知账单中产生的费用将为客户特殊申请。，递进话术：先说明可为费用... |
| `fee_application_bank_info_received` | `fee_application_bank_info_received` | `-` | 0.746 | hint_soft | 我的情况是：客户提供打款银行卡信息，等待费用特殊申请处理。补充一下，感谢客户配合，告知客服提交申请后正常处理时间为1-4个工作日。，提醒客户期间无需重复联系，关... |
| `hesitation_period_principal_clearance` | `hesitation_period_principal_clearance` | `-` | 0.735 | hint_soft | 我的情况是：借款犹豫期内，首贷首笔客户称只是看了下或还在考虑就放款。补充一下，核实订单有借款犹豫期标签且在犹豫期内，优先协助本金清贷。，递进顺序：1）协助清贷并... |

### `loan_termination` 贷款解约
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `retention_success` | `retention_success` | `-` | 0.705 | hint_soft | 我的情况是：客户因放款慢要取消，挽留成功。补充一下，告知审核通过后1-10个工作日放款，系统按先后顺序处理，最快当天，建议继续等待 |
| `execute_termination` | `execute_termination` | `-` | 0.710 | hint_soft | 我的情况是：客户坚持取消，订单支持解约。补充一下，操作路径：客服系统-订单管理-解约处理（有业务号）或解约处理（新）（无业务号）；仅订单确认和待放款阶段可解约 |
| `cannot_terminate` | `cannot_terminate` | `-` | 0.600 | hint_soft | 我的情况是：订单不支持解约（已放款等状态）。补充一下，告知当前订单状态不支持取消，请客户理解 |
| `ops_ticket_for_termination` | `ops_ticket_for_termination` | `-` | 0.723 | hint_soft | 我的情况是：解约操作失败。补充一下，建运维工单，分类"取消借款"，填写客户身份证号、系统截图、订单状态及诉求，处理时效3个工作日；24小时内安抚等待 |
| `explain_term_rationale` | `explain_term_rationale` | `-` | 0.764 | hint_soft | 我的情况是：客户因贷款期限短要取消。补充一下，客户表示你们给到我的贷款期限太少了时，解释期限由资质决定，期限短意味着利息少，对客户更划算；如仍坚持取消，再按订单... |

### `member_cancel` 取消会员
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `no_record` | `no_record` | `-` | 0.543 | hint_soft | 我的情况是：系统未查询到会员服务。补充一下，询问客户查询路径，建议再核实 |
| `not_needed_deferred` | `not_needed_deferred` | `-` | 0.603 | hint_soft | 我的情况是：系统查询到会员，客户不需要（先享后付）。补充一下，介绍会员权益，强调性价比，尝试挽留 |
| `unknown_source_deferred` | `unknown_source_deferred` | `-` | 0.635 | hint_soft | 我的情况是：客户称不知道哪里来的会员（先享后付）。补充一下，说明借款时无意操作可能性，引导回忆，尝试挽留 |
| `retain_success` | `retain_success` | `-` | 0.489 | hint_soft | 我的情况是：挽留成功。补充一下，感谢支持，询问是否有其他问题 |
| `retain_fail` | `retain_fail` | `-` | 0.545 | hint_soft | 我的情况是：挽留失败。补充一下，在系统中直接操作取消，告知取消后不再扣费 |

### `member_consultation` 会员咨询
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `quota_increase_fail` | `quota_increase_fail` | `-` | 0.692 | hint_soft | 我的情况是：客户询问提额失败原因。补充一下，说明额度失效或已提升过额度会显示失败，建议有效期内获取额度后再使用 |
| `compliance_question` | `compliance_question` | `-` | 0.652 | hint_soft | 我的情况是：客户询问会员是否强制捆绑搭售。补充一下，说明会员属自愿购买，与贷款申请发放无关 |
| `legality_question` | `legality_question` | `-` | 0.690 | hint_soft | 我的情况是：客户询问会员收费是否合法。补充一下，说明会员费由第三方服务方收取，用户自愿购买，符合监管合规要求 |
| `benefit_change` | `benefit_change` | `-` | 0.728 | hint_soft | 我的情况是：客户询问腾讯视频权益更换为咪咕钻石会员。补充一下，说明因腾讯官方政策调整进行的正常权益调整，咪咕钻石会员月卡与原权益价值一致 |

### `member_refund` 退会员费用
- 分支：7；通过：7；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `retain_success` | `retain_success` | `-` | 0.472 | hint_soft | 我的情况是：挽留成功。补充一下，感谢支持，询问是否有其他问题 |
| `auto_renewal_cancel` | `auto_renewal_cancel` | `-` | 0.572 | hint_soft | 我的情况是：已开通自动续费，客户坚持。补充一下，先关闭自动续费，再说明当月权益已生效建议使用 |
| `no_auto_renewal` | `no_auto_renewal` | `-` | 0.521 | hint_soft | 我的情况是：未开通自动续费，客户坚持退费。补充一下，直接进入退费判断流程 |
| `active_benefits` | `active_benefits` | `-` | 0.517 | hint_soft | 我的情况是：权益生效中。补充一下，协助全额退费，告知1-4工作日原路退回 |
| `expired_or_used` | `expired_or_used` | `-` | 0.662 | hint_soft | 我的情况是：外部权益已过期或已使用。补充一下，先婉拒，说明无法全额退回，协商部分退费金额；客户不接受则升级主管；内诉可直接处理 |
| `music_fitness_used` | `music_fitness_used` | `-` | 0.702 | hint_soft | 我的情况是：仅音乐健身（29元）已完结，其他未使用。补充一下，先告知音乐健身权益使用方法挽留；不接受则优先部分退（总金额-29元）；会员费为79或98元时直接全... |
| `escalate_to_supervisor` | `escalate_to_supervisor` | `-` | 0.617 | hint_soft | 我的情况是：客户坚持全额退费且一线无法处理。补充一下，一线建超权限工单升级主管；内诉可直接系统操作退费 |

### `no_quota_issue` 无额度问题
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `no_loan_record` | `no_loan_record` | `-` | 0.546 | hint_soft | 我的情况是：系统中未查询到贷款信息。补充一下，询问客户贷款渠道，建议再核实 |
| `has_loan_record` | `has_loan_record` | `-` | 0.579 | hint_soft | 我的情况是：系统中查询到贷款信息。补充一下，与客户核实贷款日期，进一步了解具体问题 |
| `wait_activation` | `wait_activation` | `-` | 0.612 | hint_soft | 我的情况是：额度获取显示激活中/超时，未超过3天。补充一下，告知耐心等待，同时检查身份证是否过期 |
| `ops_ticket` | `ops_ticket` | `-` | 0.535 | hint_soft | 我的情况是：额度获取超过3天且身份证未过期。补充一下，发运维工单处理 |
| `reserved_loan` | `reserved_loan` | `-` | 0.538 | hint_soft | 我的情况是：预约借款相关问题。补充一下，说明预约借款机制，放款金额以实际为准 |
| `withdrawal_quota_zero` | `withdrawal_quota_zero` | `-` | 0.706 | hint_soft | 我的情况是：提现额度显示为0。补充一下，解释提现额度以系统综合评估结果为准，当前展示为0说明暂不符合提现条件；建议保持良好信用记录并后续关注APP |
| `marketing_invited_no_quota` | `marketing_invited_no_quota` | `-` | 0.710 | hint_soft | 我的情况是：营销电话邀请贷款但系统无额度。补充一下，说明营销邀约不等于审批通过或保证有额度，最终额度以客户提交申请后的系统综合评估为准 |
| `no_quota_after_clearance` | `no_quota_after_clearance` | `-` | 0.697 | hint_soft | 我的情况是：贷款还清后再借无额度。补充一下，解释还清历史贷款不代表再次申请一定有额度，系统会结合最新信用、负债、资方政策等重新评估 |

### `other_certificate` 开具其他证明
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：8/8。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `supported_overdue_proof` | `supported_overdue_proof` | `supported_overdue_proof` | 0.365 | expr_runtime | 我的情况是：支持开具逾期还款证明的资方——协助申请，说明时效 |
| `unsupported_overdue_proof` | `unsupported_overdue_proof` | `unsupported_overdue_proof` | 0.302 | expr_runtime | 我的情况是：不支持开具的资方——婉拒，告知征信自动更新 |
| `non_malicious_proof` | `non_malicious_proof` | `non_malicious_proof` | 0.401 | expr_runtime | 我的情况是：非恶意逾期证明——通常不支持，婉拒后引导征信查询渠道 |
| `loan_voucher` | `loan_voucher` | `loan_voucher` | 0.378 | expr_runtime | 我的情况是：放款凭证——按资方规定处理，部分支持发送银行流水 |
| `escalate_to_tier2` | `escalate_to_tier2` | `escalate_to_tier2` | 0.334 | expr_runtime | 我的情况是：客户坚持要求开具——升级二线处理 |
| `identify_order_and_certificate` | `identify_order_and_certificate` | `identify_order_and_certificate` | 0.524 | expr_runtime | 我的情况是：客户只说XX年XX月XX日办理的那笔贷款并要求开XX证明时，先确认订单、证明类型和用途，再按是否支持开具分流 |
| `repayment_statement_for_unfreeze` | `repayment_statement_for_unfreeze` | `repayment_statement_for_unfreeze` | 0.611 | expr_runtime | 我的情况是：客户要求还款情况说明用于解冻账户时，说明非标准证明通常不支持直接开具；可记录用途、订单和接收方式，升级二线核查资方是否支持 |
| `credit_inquiry_record_statement` | `credit_inquiry_record_statement` | `credit_inquiry_record_statement` | 0.576 | expr_runtime | 我的情况是：客户未贷款成功但征信存在审查记录时，解释授信/担保资格审查可能产生查询记录；如要求出具说明，按担保资格审查说明路径升级处理 |

### `overdue_negotiation` 协商还款
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：4/4。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `pre_overdue` | `pre_overdue` | `pre_overdue` | 0.463 | expr_runtime | 我的情况是：未逾期客户协商延期——婉拒延期，提醒征信影响，添加催收备注 |
| `early_overdue` | `early_overdue` | `early_overdue` | 0.525 | expr_runtime | 我的情况是：逾期1-30天——了解原因，IVR/AI阶段引导等待专员，发单时效1-2工作日 |
| `mid_overdue` | `mid_overdue` | `mid_overdue` | 0.524 | expr_runtime | 我的情况是：逾期31-90天——强调征信影响，可申请二次分期（需提供困难凭证），发单时效1-2工作日 |
| `severe_overdue` | `severe_overdue` | `severe_overdue` | 0.523 | expr_runtime | 我的情况是：逾期90天以上——委外/法诉阶段，对公入账1-3工作日，法诉业务入账约1个月 |

### `overpayment_refund` 客户对公转账出错退溢余
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `transfer_verified_full_match` | `transfer_verified_full_match` | `-` | 0.582 | hint_soft | 我的情况是：转账信息核实成功，金额与系统匹配。补充一下，确认溢余金额，发起全额退款申请 |
| `genuine_overpayment` | `genuine_overpayment` | `-` | 0.576 | hint_soft | 我的情况是：转账金额超出账单金额（有真实溢余）。补充一下，核实溢余金额（转账金额，-，账单金额），仅退还溢余部分 |
| `no_overpayment` | `no_overpayment` | `-` | 0.607 | hint_soft | 我的情况是：转账金额与账单金额一致（非溢余）。补充一下，告知客户转账金额已抵扣账单，无溢余可退，账单已更新 |
| `incomplete_proof` | `incomplete_proof` | `-` | 0.613 | hint_soft | 我的情况是：客户提供凭证信息不完整。补充一下，请客户补充完整转账凭证（包含转账时间、金额、收款账户信息） |
| `collect_corporate_account_for_verification` | `collect_corporate_account_for_verification` | `-` | 0.734 | hint_soft | 我的情况是：客户表示对公误转或转多了，尚未核实收款账号。补充一下，递进话术：先请客户提供转入对公账号、转账时间、金额和转账凭证，为其核实具体情况。，不要在未核实... |
| `corporate_mis_transfer_requires_statement` | `corporate_mis_transfer_requires_statement` | `-` | 0.768 | hint_soft | 我的情况是：核实收款账号为我司对公账号，且转账金额非客户名下应还当期或逾期账单。补充一下，引导客户提供“本人+手持说明”照片和转账记录。，说明内容需包含真实姓名... |
| `not_our_corporate_account` | `not_our_corporate_account` | `-` | 0.625 | hint_soft | 我的情况是：核实收款账号并非我司对公账号。补充一下，告知该账号并非我司对公账号，建议客户再核实确认或联系银行查询收款方 |
| `proof_received_wait_refund` | `proof_received_wait_refund` | `-` | 0.710 | hint_soft | 我的情况是：客户已提供完整凭证和情况说明。补充一下，告知凭证已收到，预计1-6个工作日原路退回，请客户注意查收。，在此期间无需重复进线；不要承诺当天到账 |

### `post_loan_verification` 核实贷后信息
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：3/3。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `verify_account` | `verify_account` | `verify_account` | 0.465 | expr_runtime | 我的情况是：核实对公账号——按资方功能表查询，属实则发账号短信并提醒防诈骗，不属实则发单核实 |
| `verify_staff` | `verify_staff` | `verify_staff` | 0.423 | expr_runtime | 我的情况是：核实工号——查询到则告知属实（姓名不显示），未查询到则告知无法确认并提交核实 |
| `verify_institution` | `verify_institution` | `verify_institution` | 0.437 | expr_runtime | 我的情况是：核实调解机构——查询到则告知可联系，未查询到则提交工单1-2工作日内回复 |
| `jiangnan_mediation` | `jiangnan_mediation` | `-` | 0.673 | hint_soft | 我的情况是：institution_name，==，江南商事调解中心。补充一下，江南商事调解中心——系受公司委托，由重庆市南岸区人民法院指导的合法调解机构 |

### `premium_card_cancel` 取消优享卡
- 分支：8；通过：8；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `no_record` | `no_record` | `-` | 0.560 | hint_soft | 我的情况是：系统未查询到优享卡服务。补充一下，询问客户查询路径，建议再核实 |
| `accidental_purchase` | `accidental_purchase` | `-` | 0.659 | hint_soft | 我的情况是：系统查询到优享卡服务，客户原因为不小心点错。补充一下，说明购买前权益有展示，属自主选择，尝试挽留 |
| `deny_purchase` | `deny_purchase` | `-` | 0.541 | hint_soft | 我的情况是：客户称从未点击过。补充一下，安抚情绪，说明系统记录，尝试挽留 |
| `not_needed` | `not_needed` | `-` | 0.513 | hint_soft | 我的情况是：客户称不需要该服务。补充一下，介绍权益价值，尝试挽留 |
| `too_expensive` | `too_expensive` | `-` | 0.513 | hint_soft | 我的情况是：客户称太贵了。补充一下，强调权益丰富性价比，尝试挽留 |
| `forced_sale_complaint` | `forced_sale_complaint` | `-` | 0.550 | hint_soft | 我的情况是：客户指责强卖。补充一下，安抚情绪，说明购买为自主选择，尝试挽留 |
| `retain_success` | `retain_success` | `-` | 0.493 | hint_soft | 我的情况是：挽留成功。补充一下，感谢支持，询问是否有其他问题 |
| `retain_fail` | `retain_fail` | `-` | 0.543 | hint_soft | 我的情况是：挽留失败。补充一下，在系统中直接操作取消，告知后续不会扣费 |

### `premium_card_inquiry` 优享卡咨询
- 分支：3；通过：3；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `not_purchased` | `not_purchased` | `-` | 0.615 | hint_soft | 我的情况是：客户未购买优享卡。补充一下，引导客户APP端查看，具体以APP页面展示为准 |
| `purchased_inquire` | `purchased_inquire` | `-` | 0.645 | hint_soft | 我的情况是：客户已购买优享卡且追问权益。补充一下，需核身，核身通过后引导至对应服务商联系方式 |
| `purchased_confirm_continue` | `purchased_confirm_continue` | `-` | 0.754 | hint_soft | 我的情况是：已购买客户确认继续咨询权益。补充一下，客户回复好了/ok/是的/好/嗯后，继续确认具体权益问题；如需查询已购权益详情，核身后提供第三方服务商联系方式 |

### `premium_card_refund` 退优享卡费用
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `retain_success` | `retain_success` | `-` | 0.508 | hint_soft | 我的情况是：挽留成功。补充一下，感谢支持，询问是否有其他问题 |
| `no_risk_refusal` | `no_risk_refusal` | `-` | 0.591 | hint_soft | 我的情况是：客户不接受，无风险行为。补充一下，提供服务商联系方式，引导客户自行联系 |
| `risk_behavior` | `risk_behavior` | `-` | 0.670 | hint_soft | 我的情况是：客户不接受，且有风险行为（扬言外诉/自杀/报复社会）。补充一下，代为反馈供应商处理，升级主管操作退费 |
| `supplier_failed` | `supplier_failed` | `-` | 0.670 | hint_soft | 我的情况是：客户已联系供应商，供应商不处理或不满结果。补充一下，直接受理；一线建超权限工单给主管，内诉可直接处理 |
| `refund_approved` | `refund_approved` | `-` | 0.649 | hint_soft | 我的情况是：退费：告知1-3工作日原路退回。补充一下，一线建超权限工单给主管；内诉坐席可直接操作，告知1-3工作日原路退回 |

### `quota_consultation` 额度咨询
- 分支：4；通过：4；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `max_quota` | `max_quota` | `-` | 0.578 | hint_soft | 我的情况是：客户询问最高额度。补充一下，直接告知最高20万，具体以系统评估为准 |
| `amount_discrepancy` | `amount_discrepancy` | `-` | 0.601 | hint_soft | 我的情况是：客户询问放款金额与申请金额不符。补充一下，解释协议约定，实际放款以系统为准 |
| `escalate_ops` | `escalate_ops` | `-` | 0.589 | hint_soft | 我的情况是：额度获取超时或激活失败。补充一下，超过3天且身份证未过期，发运维工单 |
| `collect_name_then_answer` | `collect_name_then_answer` | `-` | 0.673 | hint_soft | 我的情况是：客户先提供姓名或姓氏。补充一下，客户回复我姓XX/我叫XX后，以称呼承接，再说明最高额度、实际额度以系统评估为准 |

### `refund_value_added_service` 退增值服务费
- 分支：10；通过：10；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `fuqiang_partial_refund` | `fuqiang_partial_refund` | `-` | 0.773 | hint_soft | 我的情况是：赋强公证退费，客户坚持退款。补充一下，婉拒后仍坚持，可申请退120元关怀金（建"营业外支出工单"）；60元在订单结清后自动退回；若客户要求全退，解释... |
| `explain_legal_compliance` | `explain_legal_compliance` | `-` | 0.661 | hint_soft | 我的情况是：赋强公证费用违法质疑。补充一下，告知系统展示协议，客户自愿勾选同意，赋强公证由政府公证处收取，合法合规 |
| `acceleration_card_refund_dispute` | `acceleration_card_refund_dispute` | `-` | 0.720 | hint_soft | 我的情况是：加速卡已放款且加速成功，要求退费。补充一下，婉拒：权益已生效不支持退费；坚持：建"超权限工单"升级主管，沟通无果可申请退款，1-4个工作日原路退回 |
| `jujufan_success_refund` | `jujufan_success_refund` | `-` | 0.650 | hint_soft | 我的情况是：拒就返权益状态：成功。补充一下，一线婉拒，坚持则升二线；二线评估风险需退费：退费金额=已付金额-已赔付金额 |
| `jujufan_failed_refund` | `jujufan_failed_refund` | `-` | 0.575 | hint_soft | 我的情况是：拒就返权益状态：失败。补充一下，一线婉拒，坚持升二线；二线评估风险可退费 |
| `pending_status` | `pending_status` | `-` | 0.634 | hint_soft | 我的情况是：权益状态：申请中/处理中。补充一下，告知权益尚在处理中，耐心等待确认权益使用结果后再进一步沟通 |
| `tianchuang_credit_refund` | `tianchuang_credit_refund` | `-` | 0.659 | hint_soft | 我的情况是：天创信用/贷前必查/借钱必查退费。补充一下，非我司收费，引导联系天创信用服务方，客服热线4001812600 |
| `zhonghui_insurance_refund` | `zhonghui_insurance_refund` | `-` | 0.603 | hint_soft | 我的情况是：众惠保险退费。补充一下，引导联系众惠财产相互保险客服热线4008106088 |
| `confirmed_service_refund_request` | `confirmed_service_refund_request` | `-` | 0.768 | hint_soft | 我的情况是：客户确认增值服务活动后继续退费。补充一下，客户回复好了/ok/是的/好/嗯确认服务后，继续核实服务类型、扣款状态、权益是否生效，再按赋强公证/加速卡... |
| `unbound_card_deduction_dispute` | `unbound_card_deduction_dispute` | `-` | 0.780 | hint_soft | 我的情况是：客户称未绑定银行卡却被扣款。补充一下，客户说我没绑定的银行卡为什么会被你们扣钱时，先引导核对银行流水扣款方和扣款协议；如为赋强公证或协议内扣款，解释... |

### `remote_disbursement` 异地放款
- 分支：3；通过：3；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `firm_denial_with_best_offer` | `firm_denial_with_best_offer` | `-` | 0.689 | hint_soft | 我的情况是：客户坚持要求提供放款方可异地放款的凭证。补充一下，告知贷款不存在异地放款情况，建议客户考虑我司给到的最优方案 |
| `explain_verification_criteria` | `explain_verification_criteria` | `-` | 0.745 | hint_soft | 我的情况是：客户询问如何核实异地放款。补充一下，告知如有疑问可提供凭证，客服帮助核实；四要素：身份证前六位对应地区、户籍地址、正常IP地址、APP自行填写的居住... |
| `escalate_to_consumer_protection` | `escalate_to_consumer_protection` | `-` | 0.673 | hint_soft | 我的情况是：客户提供完整证据链且四要素均不符合。补充一下，告知已收到凭证，情况特殊，帮助核实后回复；上报消保团队处理 |

### `repayment_method_inquiry` 咨询还款方式
- 分支：2；通过：2；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `auto_deduction_detail` | `auto_deduction_detail` | `-` | 0.585 | hint_soft | 我的情况是：客户询问自动还款细节。补充一下，说明绑定银行卡后系统自动扣款机制 |
| `manual_repayment_path` | `manual_repayment_path` | `-` | 0.568 | hint_soft | 我的情况是：客户询问主动还款操作路径。补充一下，引导客户在APP上操作主动还款 |

### `repayment_result_query` 查询还款结果
- 分支：3；通过：3；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `repayment_success` | `repayment_success` | `-` | 0.516 | hint_soft | 我的情况是：还款已成功到账。补充一下，告知还款成功，账单已更新 |
| `repayment_processing` | `repayment_processing` | `-` | 0.581 | hint_soft | 我的情况是：还款处理中，未超时效。补充一下，告知处理时效1-2小时，请耐心等待 |
| `repayment_delayed` | `repayment_delayed` | `-` | 0.571 | hint_soft | 我的情况是：还款超时效未到账。补充一下，需进一步排查，可能需要升级处理 |

### `repayment_status_issue` 还款状态异常
- 分支：14；通过：14；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `failure_insufficient_balance_sufficient_now` | `failure_insufficient_balance_sufficient_now` | `-` | 0.752 | hint_soft | 我的情况是：扣款失败-余额不足，客户确认现在余额已充足。补充一下，这边查询扣款失败是因为余额不足导致扣款失败，您现在余额是否充足？充足的话客服这边可以帮您扣款。... |
| `failure_insufficient_balance_still_low` | `failure_insufficient_balance_still_low` | `-` | 0.665 | hint_soft | 我的情况是：扣款失败-余额不足，客户余额仍不足。补充一下，扣款失败是因为绑卡余额不足，辛苦您先把所绑定银行卡余额补足再尝试 |
| `failure_bank_card_contract` | `failure_bank_card_contract` | `-` | 0.583 | hint_soft | 我的情况是：扣款失败-银行卡签约问题。补充一下，扣款失败是因为银行卡签约问题，建议您重新签约银行卡 |
| `failure_rule_not_due` | `failure_rule_not_due` | `-` | 0.638 | hint_soft | 我的情况是：扣款失败-规则卡控（未到还款日）。补充一下，扣款失败是因为账单还未到还款日，建议您等到还款日系统自动扣款 |
| `failure_card_limit_has_other_card` | `failure_card_limit_has_other_card` | `-` | 0.687 | hint_soft | 我的情况是：扣款失败-银行卡限额，客户有其他卡。补充一下，扣款失败是银行卡限额所致。您是否有其他银行卡可更换？换卡路径：APP-我的-我的银行卡 |
| `failure_limit_qr_payment` | `failure_limit_qr_payment` | `-` | 0.670 | hint_soft | 我的情况是：扣款失败-限额，引导扫码付款。补充一下，扣款失败是系统原因。可支持微信/支付宝/云闪付扫码付款，付款码，20，分钟有效 |
| `failure_limit_corporate_payment` | `failure_limit_corporate_payment` | `-` | 0.695 | hint_soft | 我的情况是：扣款失败-限额，引导对公还款。补充一下，扣款失败是系统原因。可用对公还款：客服发送我司对公账户，通过银行转账后上传凭证即可 |
| `failure_channel_qr_payment` | `failure_channel_qr_payment` | `-` | 0.541 | hint_soft | 我的情况是：扣款失败-通道限额，引导扫码付款。补充一下，通道限额导致扣款失败，引导扫码付款 |
| `failure_channel_corporate_payment` | `failure_channel_corporate_payment` | `-` | 0.543 | hint_soft | 我的情况是：扣款失败-通道限额，引导对公还款。补充一下，通道限额导致扣款失败，引导对公还款 |
| `update_in_progress` | `update_in_progress` | `-` | 0.621 | hint_soft | 我的情况是：已扣款处理中，还款记录存在。补充一下，告知，1-2，小时到账时效，请耐心等待账单刷新 |
| `update_cache_refresh` | `update_cache_refresh` | `-` | 0.648 | hint_soft | 我的情况是：已扣款成功，仅，APP，页面缓存未刷新。补充一下，建议客户下拉刷新，APP，或重新登录查看最新状态 |
| `update_no_record` | `update_no_record` | `-` | 0.655 | hint_soft | 我的情况是：已扣款但无还款记录（可能客户记错/转到第三方）。补充一下，核实客户还款路径和凭证，必要时升级处理 |
| `partial_deduction` | `partial_deduction` | `-` | 0.690 | hint_soft | 我的情况是：部分扣款（客户还款金额大于当期应还或小于应还）。补充一下，告知客户具体扣款金额与应还金额对比，引导补足或说明差额去向 |
| `duplicate_deduction` | `duplicate_deduction` | `-` | 0.634 | hint_soft | 我的情况是：重复扣款（同一账单被扣两次）。补充一下，核实后若确认重复扣款，按退款流程处理。时效，3-5，工作日 |

### `special_account_cancellation` 特殊场景注销账户
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `direct_to_debt_company` | `direct_to_debt_company` | `-` | 0.738 | hint_soft | 我的情况是：智信贷已转让，客户表示未结清。补充一下，引导联系对应债权受让方结清，客服热线4006162978，工作日9:00-12:00，13:30-17:30... |
| `request_settlement_proof` | `request_settlement_proof` | `-` | 0.716 | hint_soft | 我的情况是：智信贷已转让，客户表示已结清但系统显示未结清。补充一下，需客户提供债权受让方开具的结清证明，收集凭证后发"其他工单"，作业组按每周一统一提交OA申请 |
| `submit_other_ticket` | `submit_other_ticket` | `-` | 0.627 | hint_soft | 我的情况是：客户已上传结清证明凭证。补充一下，建"其他工单"反馈作业处理，预计3-5个工作日，处理完成电话通知客户 |
| `direct_to_huatong_company` | `direct_to_huatong_company` | `-` | 0.671 | hint_soft | 我的情况是：华通已转让订单。补充一下，告知联系"湖北小蚁资产管理有限公司"，电话4006163978；注销处理流程同智信贷已转让 |
| `clarify_transferred_order_identity` | `clarify_transferred_order_identity` | `-` | 0.749 | hint_soft | 我的情况是：客户只提供姓名或称是某银行订单。补充一下，智信贷已转让/华通已转让订单，客户要求注销但只回复我叫XX/是XX银行时，先按姓名核身并确认是否为智信贷/... |

### `stop_collection` 要求停催
- 分支：5；通过：5；低置信：0；失败：0；expr evaluator：5/5。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `ai_collection_early` | `ai_collection_early` | `ai_collection_early` | 0.444 | expr_runtime | 我的情况是：AI催收阶段（还款日及账单日后3天内）——有停催权限，不支持降频，仅联系本人 |
| `ivr_collection` | `ivr_collection` | `ivr_collection` | 0.335 | expr_runtime | 我的情况是：IVR催收——可操作停催，按客户诉求操作 |
| `normal_stop` | `normal_stop` | `normal_stop` | 0.278 | expr_or_hint | 我的情况是：本人要求停催15天内。补充一下，本人停催15天内——客服直接操作 |
| `supervisor_stop` | `supervisor_stop` | `supervisor_stop` | 0.389 | expr_runtime | 我的情况是：本人停催15-30天——发超权限工单给主管操作，无需回电 |
| `escalate_stop` | `escalate_stop` | `escalate_stop` | 0.302 | expr_runtime | 我的情况是：超过30天——超主管权限，需升级处理 |

### `stop_marketing` 停止营销
- 分支：7；通过：7；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `execute_stop_marketing` | `execute_stop_marketing` | `-` | 0.671 | hint_soft | 我的情况是：客户坚持停止，提供联系方式。补充一下，申请停止营销服务电话（含人工、短信等），生效时间一个工作日；实际系统操作天数不可告知客户 |
| `pending_effective` | `pending_effective` | `-` | 0.594 | hint_soft | 我的情况是：已操作停止营销但未生效（生效期内）。补充一下，告知停止营销生效时间需一个工作日，建议耐心等待 |
| `already_stopped_still_receiving` | `already_stopped_still_receiving` | `-` | 0.621 | hint_soft | 我的情况是：已操作停止营销且已生效，仍收到营销。补充一下，告知我司不会对已停止营销客户提供营销服务，提醒谨防诈骗 |
| `deactivated_received_marketing` | `deactivated_received_marketing` | `-` | 0.659 | hint_soft | 我的情况是：已注销账户反映收到营销电话。补充一下，告知已注销账户不会收到我司营销，提醒谨防诈骗；客户坚持则请提供凭证（截图），建"信息安全"工单 |
| `unregistered_received_marketing` | `unregistered_received_marketing` | `-` | 0.693 | hint_soft | 我的情况是：未注册客户反映收到营销。补充一下，发其他工单反馈处理；若已加入黑名单告知即可；无拨打记录则引导提供凭证，反馈信息安全，预计1-3个工作日回复 |
| `kakaday_is_our_product` | `kakaday_is_our_product` | `-` | 0.648 | hint_soft | 我的情况是：客户咨询卡卡贷营销电话是否为我司。补充一下，告知卡卡贷也是我司产品，如有资金需求可通过豆豆钱或卡卡贷APP申请 |
| `collect_name_then_stop` | `collect_name_then_stop` | `-` | 0.667 | hint_soft | 我的情况是：客户先提供姓名或姓氏。补充一下，客户回复我姓XX/我叫XX后，以称呼承接并询问营销电话/短信对应联系方式，客户坚持则申请停止营销 |

### `value_added_service_inquiry` 增值服务咨询
- 分支：9；通过：9；低置信：0；失败：0；expr evaluator：0/0。
| expected branch | selected | expr selected | score | runtime | 递进话术末轮 |
|---|---|---|---:|---|---|
| `explain_fuqiang_notary` | `explain_fuqiang_notary` | `-` | 0.802 | hint_soft | 我的情况是：客户咨询赋强公证是什么。补充一下，赋予债权文书强制执行效力公证，可在债务人不履约时减少诉讼环节、提高纠纷处理效率；费用180元（120元公证处费用+... |
| `explain_legal_basis` | `explain_legal_basis` | `-` | 0.767 | hint_soft | 我的情况是：客户咨询赋强公证法律依据。补充一下，客户问赋强公证的法律依据时，引用《公证法》第37条、司发通2000年107号、最高法相关批复，说明强制执行公证如... |
| `faxin_notary_fee` | `faxin_notary_fee` | `-` | 0.573 | hint_soft | 我的情况是：法信-赋强公证费用咨询。补充一下，收费金额以APP端显示为准 |
| `explain_acceleration_card` | `explain_acceleration_card` | `-` | 0.677 | hint_soft | 我的情况是：客户咨询加速卡。补充一下，参加后对应借款订单提现可享受优先放款资方福利，加速卡履约成功后自动发起扣款 |
| `explain_ju_jiu_fan` | `explain_ju_jiu_fan` | `-` | 0.723 | hint_soft | 我的情况是：客户咨询拒就返。补充一下，符合条件用户，在平台提供的借款渠道全部被拒后可申请返现，3天内处理，最高500元，以实际申请结果为准 |
| `explain_tianchuang_credit` | `explain_tianchuang_credit` | `-` | 0.721 | hint_soft | 我的情况是：客户咨询天创信用/贷前必查/借钱必查。补充一下，第三方合作风险自查活动，客服热线4001812600，工作日9:30-12:00，13:30-18:... |
| `explain_zhonghui_insurance` | `explain_zhonghui_insurance` | `-` | 0.655 | hint_soft | 我的情况是：客户咨询众惠保险。补充一下，第三方合作保险活动，众惠财产相互保险客服热线4008106088 |
| `explain_activity_change` | `explain_activity_change` | `-` | 0.622 | hint_soft | 我的情况是：客户反映活动权益变化。补充一下，不同阶段活动权益构成有所差异，以客户权益页面展示为准 |
| `collect_name_then_explain` | `collect_name_then_explain` | `-` | 0.773 | hint_soft | 我的情况是：客户先提供姓名或姓氏。补充一下，客户咨询活动时如先回复我姓XX，以称呼承接并询问具体想了解哪项增值服务，再进入赋强公证、加速卡、拒就返或第三方服务说... |

## 无分支 Skill

`acknowledgement`, `channel_check`, `closing`, `greeting_opening`, `identity_readback`
