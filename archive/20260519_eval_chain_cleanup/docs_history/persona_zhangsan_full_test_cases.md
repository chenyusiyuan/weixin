# 张三画像全场景测试题库（含核身层）

> **用途**：全链路测试，覆盖核身流程、主业务场景、边界场景和语义纠缠场景
> 
> **张三画像摘要**：
> - 核身信息：`张三 / 13812345678 / 1234`
> - 基本信息：35岁男性，深圳，账户状态active，风险标签medium
> - 账单状态：当前账单8500元，逾期45天，近期3次扣款失败
> - 贷款情况：豆豆钱50000元(逾期)+信用贷20000元(正常)
> - 会员状态：VIP尊享会员，年费99元，已使用视频会员月卡、音乐会员月卡
> - 额度状态：总额80000元，可用0元，冻结30000元
> - 工单记录：逾期协商(处理中)、费用争议(已解决)、催收投诉(已解决)

---

## 一、核身层测试（Identity Verification Layer）

### 1.1 核身前场景（未核身状态）

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 1 | 你好，我有个问题想问 | greeting_opening | 开场无核身信息 |
| 2 | 喂，在吗 | greeting_opening | 简短开场 |
| 3 | 我的账单怎么还没扣款？ | → 触发核身流程 | 业务诉求触发核身 |
| 4 | 你们怎么老是打电话给我 | → 触发核身流程 | 投诉类触发核身 |
| 5 | 我想查一下我的额度 | → 触发核身流程 | 查询类触发核身 |
| 6 | 帮我把会员退了 | → 触发核身流程 | 业务办理触发核身 |

### 1.2 核身中场景（核身信息提供）

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 7 | 我叫张三 | identity_readback | 仅姓名 |
| 8 | 我是张三，手机号13812345678 | identity_readback | 姓名+手机 |
| 9 | 张三，身份证后四位1234 | identity_readback | 姓名+身份证后四位 |
| 10 | 我的手机号是13812345678 | identity_readback | 仅手机号 |
| 11 | 身份证后四位是1234 | identity_readback | 仅身份证后四位 |
| 12 | 我是这个号的机主，我叫张三，手机13812345678，身份证后四位1234 | identity_readback | 完整核身信息 |
| 13 | 我叫张三，尾号是1234 | identity_readback | 口语化表达 |
| 14 | 张三，138开头的，后四位1234 | identity_readback | 不完整表达 |
| 15 | 我是这个账户的本人，张三，身份证最后四个数字是1234 | identity_readback | 冗长表达 |

### 1.3 核身错误场景

| # | 客户输入 | 期望结果 | 测试点 |
|---|----------|----------|--------|
| 16 | 我叫李四，身份证后四位1234 | 核身失败，提示信息不匹配 | 姓名错误 |
| 17 | 我是张三，手机号13900001111 | 核身失败，提示信息不匹配 | 手机号错误 |
| 18 | 张三，身份证后四位5678 | 核身失败，提示信息不匹配 | 身份证后四位错误 |
| 19 | 我不记得我的身份证号了 | 提示其他核身方式 | 信息缺失 |
| 20 | 这个账号是我朋友的，我帮他问一下 | 提示需本人核身 | 非本人场景 |

### 1.4 核身成功后场景

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 21 | [核身成功] 好的，我现在想问我的账单 | bill_deduction_query | 核身后切换话题 |
| 22 | [核身成功] 没有别的事了，就是确认一下我的信息 | acknowledgement | 核身后无具体诉求 |
| 23 | [核身成功] 刚才说的那个问题帮我处理一下 | → 需上下文回溯 | 引用前置诉求 |
| 24 | [核身成功] 好的我知道了，谢谢 | acknowledgement | 确认后结束 |
| 25 | [核身成功] 没有别的问题了，再见 | closing | 核身后直接结束 |

---

## 二、会话流程场景

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 26 | 您好，请问是客服吗 | greeting_opening | 正式开场 |
| 27 | 有人吗 | channel_check | 通道确认 |
| 28 | 喂喂喂，能听到吗 | channel_check | 多次确认 |
| 29 | 嗯嗯，好的 | acknowledgement | 简单应答 |
| 30 | 明白了，我知道了 | acknowledgement | 理解确认 |
| 31 | 好的好的，我明白了，谢谢 | acknowledgement + closing | 应答+结束倾向 |
| 32 | 没有别的问题了，谢谢你们 | closing | 礼貌结束 |
| 33 | 好的就这样吧，挂了 | closing | 口语化结束 |
| 34 | 那就这样，bye | closing | 英文结束 |

---

## 三、账单与扣款场景

### 3.1 基础查询

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 35 | 查一下我账单 | bill_deduction_query | 简短表达 |
| 36 | 我这期账单多少钱 | bill_deduction_query | 金额查询 |
| 37 | 帮我看看我账单扣款情况 | bill_deduction_query | 扣款情况 |
| 38 | 我最近有没有扣款 | bill_deduction_query | 近期扣款 |
| 39 | 今天有没有扣我的钱 | bill_deduction_query | 当日扣款 |
| 40 | 你们今天扣了我多少钱 | bill_deduction_query | 质疑扣款金额 |

### 3.2 扣款异常场景（语义纠缠重点）

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 41 | 为什么扣款失败 | deduction_issues | 扣款失败询问 |
| 42 | 我银行卡有钱怎么没扣成功 | deduction_issues | 扣款失败+余额充足 |
| 43 | 今天早上怎么又从我这边扣款了？扣了274元 | bill_deduction_query | 语义边界：质疑vs查询 |
| 44 | 你们后台扣了我八十多块钱，这是什么 | bill_deduction_query | 陌生扣款查询 |
| 45 | 为什么我银行卡扣款失败了 | deduction_issues | 扣款失败原因 |
| 46 | 扣款失败了是什么原因 | deduction_issues | 失败原因询问 |
| 47 | 我的银行卡被扣了钱，帮我看看是什么 | bill_deduction_query | 不明扣款 |
| 48 | 刚才扣了我一笔钱，是怎么回事 | bill_deduction_query | 突然扣款 |
| 49 | 为什么没到还款日就提前扣款了 | early_deduction | 提前扣款质疑 |
| 50 | 还没到还款日怎么就扣我钱了 | early_deduction | 提前扣款 |

---

## 四、还款场景

### 4.1 还款方式

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 51 | 怎么还款 | repayment_method_inquiry | 还款方式 |
| 52 | 我能怎么还款，有哪些方式 | repayment_method_inquiry | 还款方式询问 |
| 53 | 给我发个还款二维码 | repayment_method_inquiry | 二维码请求 |
| 54 | 对公账号是多少 | repayment_method_inquiry | 对公账号 |
| 55 | 我要换绑银行卡 | card_rebinding | 换卡 |
| 56 | 怎么更换还款银行卡 | card_rebinding | 换卡操作 |
| 57 | 我的银行卡失效了，怎么换 | card_rebinding | 卡失效换卡 |

### 4.2 还款状态（语义纠缠重点）

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 58 | 我还了钱，帮我查下到没到 | repayment_result_query | 还款结果查询 |
| 59 | 我刚还的钱，查一下结果 | repayment_result_query | 还款结果 |
| 60 | 还款成功了吗 | repayment_result_query | 成功确认 |
| 61 | 我已经还款了，为什么APP还没更新 | repayment_status_issue | 状态未更新 |
| 62 | 钱扣了但账单没变 | repayment_status_issue | 扣款后状态异常 |
| 63 | 还款失败了怎么办 | repayment_status_issue | 还款失败处理 |
| 64 | 我还款一直失败 | repayment_status_issue | 持续失败 |
| 65 | 系统只扣了一部分，还剩一些没扣 | repayment_status_issue | 部分扣款 |
| 66 | 我刚才还了5000，还剩多少没还 | repayment_result_query | 部分还款查询 |

### 4.3 提前还款

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 67 | 我想提前还款 | early_loan_clearance | 提前还款 |
| 68 | 我要把贷款一次性还清 | early_loan_clearance | 一次性结清 |
| 69 | 提前结清要多少钱 | early_loan_clearance | 结清金额 |
| 70 | 我想提前还款，顺便减免一下费用 | early_loan_clearance | 多意图：还款+减免 |

---

## 五、逾期与催收场景

### 5.1 逾期协商

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 71 | 我现在还不上，能不能延期 | overdue_negotiation | 延期请求 |
| 72 | 我想协商还款方案 | overdue_negotiation | 协商请求 |
| 73 | 能不能分期还 | overdue_negotiation | 分期请求 |
| 74 | 我想申请二次分期 | overdue_negotiation | 二次分期 |
| 75 | 我实在没钱，能不能宽限几天 | overdue_negotiation | 宽限请求 |
| 76 | 能不能减免一点利息 | overdue_negotiation | 减免请求 |
| 77 | 我想还本金，利息能不能免了 | overdue_negotiation | 免息请求 |
| 78 | 我之前申请的协商还在处理吗 | overdue_negotiation | 工单状态查询 |

### 5.2 催收投诉（语义纠缠重点）

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 79 | 你们的催收电话太多了 | collection_complaint | 催收频率投诉 |
| 80 | 催收一天打十几个电话，烦死了 | collection_complaint | 频率+情绪 |
| 81 | 催收态度很差，我要投诉 | collection_complaint | 态度投诉 |
| 82 | 催收威胁我，说要上门 | collection_complaint | 威胁投诉 |
| 83 | 催收打电话给我家里人，侵犯隐私 | collection_complaint | 通讯录投诉 |
| 84 | 催收发短信骂我，太恶劣了 | collection_complaint | 短信投诉 |
| 85 | 我的账单已经处理完了，为什么还在打电话？ | collection_complaint | 语义边界：已处理vs投诉 |
| 86 | 为什么平台在催我还款，但我已经没有借款了？ | collection_complaint | 错误催收投诉 |
| 87 | 催收说我欠钱，但我根本没借过 | collection_complaint | 身份争议 |

### 5.3 停催请求（语义纠缠重点）

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 88 | 不要再打电话催我了 | stop_collection | 停催请求 |
| 89 | 请停止催收，不要再打电话了 | stop_collection | 明确停催 |
| 90 | 帮我停催15天 | stop_collection | 限期停催 |
| 91 | 我要求停止一切催收行为 | stop_collection | 全面停催 |
| 92 | 请停止催收，包括发送短信和威胁 | stop_collection | 停催+情绪词 |
| 93 | 能不能暂时停几天催收 | stop_collection | 暂停催收 |
| 94 | 不要打我电话了，我会自己处理 | stop_collection | 口语化停催 |
| 95 | 我已经协商了，为什么还在催？ | collection_complaint | 协商后仍催收 |

### 5.4 核实贷后信息

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 96 | 刚才给我打电话的是你们的人吗 | post_loan_verification | 身份核实 |
| 97 | 那个催收员是不是真的 | post_loan_verification | 真伪核实 |
| 98 | 给我一个对公还款账号 | repayment_method_inquiry vs post_loan_verification | 语义边界 |
| 99 | 你们说的对公账号是真的吗 | post_loan_verification | 账号核实 |
| 100 | 有个人说他是调解中心的，帮我核实一下 | post_loan_verification | 机构核实 |

---

## 六、费用场景

### 6.1 费用咨询

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 101 | 我这个费用怎么算的 | fee_consultation_tier1 | 费用计算 |
| 102 | 担保费是什么意思 | fee_consultation_tier1 | 担保费说明 |
| 103 | 服务费为什么这么高 | fee_consultation_tier1 | 服务费质疑 |
| 104 | 帮我查一下费用明细 | fee_detail_query | 费用明细 |
| 105 | 我想知道本金和利息各多少 | fee_detail_query | 本金利息 |
| 106 | 综合费率是多少 | fee_detail_query | 综合费率 |
| 107 | 为什么我的账户里有一个叫东富的条目？ | fee_detail_query | 陌生条目查询 |

### 6.2 退费请求

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 108 | 我要退服务费 | fee_refund_tier1 | 退费请求 |
| 109 | 这笔费用我不认可，要退给我 | fee_refund_tier1 | 费用争议退费 |
| 110 | 担保费能不能退 | fee_refund_tier1 | 特定费用退费 |
| 111 | 我要求全部退费 | fee_refund_tier1 | 全额退费 |
| 112 | 你们乱收费，我要投诉到监管 | fee_refund_tier2 | 升级退费 |
| 113 | 这笔费用必须给我退，不然我投诉 | fee_refund_tier2 | 强硬退费 |
| 114 | 我申请的退费还没到账 | fee_refund_status | 退费进度 |
| 115 | 退费什么时候到账 | fee_refund_status | 到账时间 |

---

## 七、会员场景

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 116 | 我会员有什么权益 | member_consultation | 权益查询 |
| 117 | VIP会员能干什么 | member_consultation | VIP权益 |
| 118 | 我的会员什么时候到期 | member_consultation | 到期时间 |
| 119 | 我要取消会员 | member_cancel | 取消会员 |
| 120 | 会员我不想要了 | member_cancel | 口语化取消 |
| 121 | 帮我把会员退了 | member_cancel | 退会员 |
| 122 | 我想退会员费 | member_refund | 退会员费 |
| 123 | 会员扣了我99块钱，我要退 | member_refund | 扣费后退费 |
| 124 | 我没用过会员权益，能退吗 | member_refund | 未使用退费 |

---

## 八、额度场景

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 125 | 我的额度为什么是0 | no_quota_issue | 额度为零 |
| 126 | 我怎么没有额度了 | no_quota_issue | 额度消失 |
| 127 | 额度被冻结了怎么办 | no_quota_issue | 额度冻结 |
| 128 | 为什么我的额度不能用 | no_quota_issue | 额度不可用 |
| 129 | 你们最高能贷多少 | quota_consultation | 最高额度 |
| 130 | 我能申请多少额度 | quota_consultation | 可申请额度 |
| 131 | 额度怎么提升 | quota_consultation | 提额 |
| 132 | 我能提额吗 | quota_consultation | 提额询问 |

---

## 九、贷款场景

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 133 | 我想贷款怎么申请 | loan_consultation | 贷款申请 |
| 134 | 借款需要什么条件 | loan_consultation | 借款条件 |
| 135 | 我能再借一笔吗 | loan_consultation | 再次借款 |
| 136 | 我的贷款什么时候放款 | disbursement_progress | 放款进度 |
| 137 | 钱怎么还没到账 | disbursement_progress | 到账查询 |
| 138 | 这笔贷款我不想要了 | loan_termination | 贷款解约 |
| 139 | 能不能取消这笔贷款 | loan_termination | 取消贷款 |
| 140 | 我在外地，能不能放款 | remote_disbursement | 异地放款 |

---

## 十、征信场景

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 141 | 你们这个上征信吗 | credit_inquiry | 征信上报 |
| 142 | 我的逾期会不会影响征信 | credit_inquiry | 逾期影响 |
| 143 | 征信上有你们的记录，是怎么回事 | credit_inquiry | 征信记录 |
| 144 | 我想解除征信上的关注状态 | credit_modification | 征信修改 |
| 145 | 帮我把征信记录删掉 | credit_modification | 删除记录 |
| 146 | 征信显示有逾期，但我已经还清了 | credit_modification | 还清后记录 |
| 147 | 逾期一天会影响信用记录吗 | bill_date_credit_impact | 逾期天数影响 |
| 148 | 还款日当天还算逾期吗 | bill_date_credit_impact | 还款日边界 |

---

## 十一、账户与业务办理

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 149 | 我要注销账户 | account_cancellation | 注销账户 |
| 150 | 帮我把账号注销了 | account_cancellation | 口语化注销 |
| 151 | 我的账户已经注销了，为什么还收到短信 | deactivated_customer_service | 已注销进线 |
| 152 | 我要注销授信额度 | cancel_credit_authorization | 注销授信 |
| 153 | 帮我开一份结清证明 | clearance_certificate | 结清证明 |
| 154 | 我要调取贷款合同 | contract_retrieval | 合同调取 |
| 155 | 给我开个发票 | invoice_issuance | 发票开具 |
| 156 | 能开其他证明吗 | other_certificate | 其他证明 |

---

## 十二、增值服务与优享卡

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 157 | 我要取消增值服务 | cancel_value_added_service | 取消增值服务 |
| 158 | 加速卡怎么取消 | cancel_value_added_service | 加速卡取消 |
| 159 | 退增值服务费 | refund_value_added_service | 退增值服务费 |
| 160 | 赋强公证是什么 | value_added_service_inquiry | 增值服务咨询 |
| 161 | 加速卡有什么用 | value_added_service_inquiry | 加速卡咨询 |
| 162 | 我要取消优享卡 | premium_card_cancel | 取消优享卡 |
| 163 | 优享卡是什么 | premium_card_inquiry | 优享卡咨询 |
| 164 | 退优享卡费用 | premium_card_refund | 退优享卡费 |
| 165 | 轻享卡怎么退 | light_card_cancel_refund | 轻享卡退费 |

---

## 十三、停止营销

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 166 | 不要给我打营销电话了 | stop_marketing | 停止营销 |
| 167 | 别再给我发广告短信 | stop_marketing | 停止广告 |
| 168 | 关闭营销推送 | stop_marketing | 关闭推送 |
| 169 | 不要让我借钱，我不需要 | stop_marketing | 口语化停营销 |

---

## 十四、语义边界与混淆测试（重点）

### 14.1 催收簇混淆测试

| # | 客户输入 | 期望 skill_id | 备注 |
|---|----------|---------------|------|
| 170 | 请停止催收，不要打电话了 | stop_collection | 明确停催 |
| 171 | 你们催收打太多电话了，我要投诉 | collection_complaint | 明确投诉 |
| 172 | 催收态度不好，能不能不要打了 | collection_complaint + stop_collection | 多意图混合 |
| 173 | 我的账单处理完了为什么还打电话？ | collection_complaint | 已处理+投诉 |
| 174 | 请停止催收，包括发送短信和威胁 | stop_collection | 停催+情绪词干扰 |
| 175 | 催收一天打十几遍，能不能停一下 | stop_collection | 频率+停催 |
| 176 | 我要投诉催收，让他们不要再打了 | collection_complaint | 投诉主诉求 |
| 177 | 帮我核实一下刚才打电话的是不是你们的人 | post_loan_verification | 身份核实 |

### 14.2 扣款簇混淆测试

| # | 客户输入 | 期望 skill_id | 备注 |
|---|----------|---------------|------|
| 178 | 今天扣了我274元，帮我看看是什么 | bill_deduction_query | 查询性质 |
| 179 | 怎么又扣我钱了，我都不知道是什么 | deduction_issues | 质疑性质 |
| 180 | 为什么扣款失败了 | deduction_issues | 失败原因 |
| 181 | 我还款失败了，帮我看看 | repayment_status_issue | 还款失败 |
| 182 | 钱扣了但账单没更新 | repayment_status_issue | 状态异常 |
| 183 | 我查一下刚才那笔扣款 | bill_deduction_query | 中性查询 |
| 184 | 众安保险怎么又扣我钱了 | deduction_issues | 陌生扣款 |
| 185 | 我银行卡被扣了钱是什么情况 | bill_deduction_query | 不明扣款 |

### 14.3 征信簇混淆测试

| # | 客户输入 | 期望 skill_id | 备注 |
|---|----------|---------------|------|
| 186 | 我的征信显示有逾期记录 | credit_inquiry | 查询性质 |
| 187 | 帮我把征信记录删了 | credit_modification | 修改诉求 |
| 188 | 逾期一天会影响征信吗 | bill_date_credit_impact | 影响咨询 |
| 189 | 我想解除征信上的关注状态 | credit_modification | 修改诉求 |
| 190 | 征信上显示我有欠款，但我已经还清了 | credit_modification | 修改诉求 |
| 191 | 我的征信报告有问题，帮我看看 | credit_inquiry | 查询性质 |

### 14.4 多意图混合测试

| # | 客户输入 | 期望 skill_id | 备注 |
|---|----------|---------------|------|
| 192 | 我想提前还款，顺便问一下费用能减免吗 | early_loan_clearance | 提前还款为主 |
| 193 | 我要取消会员，退会员费 | member_cancel | 取消为主 |
| 194 | 我已经还款了，为什么还在催收 | collection_complaint | 投诉为主 |
| 195 | 我想协商还款，能停催几天吗 | overdue_negotiation | 协商为主 |
| 196 | 扣款失败了，帮我换张卡 | card_rebinding | 换卡为主 |
| 197 | 我要注销账户，顺便开个结清证明 | account_cancellation | 注销为主 |

---

## 十五、口语化与不规范表达测试

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 198 | 那个...我这个月还不上了咋办 | overdue_negotiation | 口语化协商 |
| 199 | 就是我钱不够，能晚点还不 | overdue_negotiation | 方言化表达 |
| 200 | 那个催收打电话烦死了 | collection_complaint | 口语化投诉 |
| 201 | 钱扣了没显示咋回事 | repayment_status_issue | 口语化状态问题 |
| 202 | 那个会员费能退不 | member_refund | 口语化退费 |
| 203 | 我额度没了是咋回事 | no_quota_issue | 口语化额度问题 |
| 204 | 能不能少还点利息 | overdue_negotiation | 口语化减免 |
| 205 | 你们这收费太高了吧 | fee_consultation_tier1 | 口语化费用质疑 |

---

## 十六、信息不充分场景测试

| # | 客户输入 | 期望 skill_id | 测试点 |
|---|----------|---------------|--------|
| 206 | 因为减免政策要有的 | overdue_negotiation | 缺少上下文 |
| 207 | 电话响一声就挂断了 | collection_complaint | 信息不完整 |
| 208 | 我遇到了同样的情况 | → 需追问具体问题 | 缺少具体诉求 |
| 209 | 我想咨询一下 | → 需追问具体问题 | 过于笼统 |
| 210 | 有个问题想问 | → 需追问具体问题 | 无具体问题 |

---

## 十七、连续对话流程测试

### 流程1：核身 → 账单查询 → 协商还款

| 序号 | 客户输入 | 期望 skill_id |
|------|----------|---------------|
| 1 | 你好 | greeting_opening |
| 2 | 我叫张三，手机号13812345678，身份证后四位1234 | identity_readback |
| 3 | 我想查一下我的账单 | bill_deduction_query |
| 4 | 我现在还不上，能协商分期吗 | overdue_negotiation |
| 5 | 好的，我知道了，谢谢 | acknowledgement + closing |

### 流程2：核身 → 投诉催收 → 停催

| 序号 | 客户输入 | 期望 skill_id |
|------|----------|---------------|
| 1 | 喂，有人吗 | channel_check |
| 2 | 我是张三，13812345678，尾号1234 | identity_readback |
| 3 | 你们催收电话太多了，我要投诉 | collection_complaint |
| 4 | 能不能停催几天 | stop_collection |
| 5 | 好的，就这样，再见 | closing |

### 流程3：核身 → 费用查询 → 退费

| 序号 | 客户输入 | 期望 skill_id |
|------|----------|---------------|
| 1 | 你好，我有个问题 | greeting_opening |
| 2 | 张三，13812345678，1234 | identity_readback |
| 3 | 我的费用明细帮我查一下 | fee_detail_query |
| 4 | 服务费我不认可，能退吗 | fee_refund_tier1 |
| 5 | 好的，我知道了 | acknowledgement |

---

## 测试覆盖统计

| 分类 | 测试条数 |
|------|----------|
| 核身层 | 25 |
| 会话流程 | 9 |
| 账单与扣款 | 16 |
| 还款场景 | 20 |
| 逾期与催收 | 30 |
| 费用场景 | 15 |
| 会员场景 | 9 |
| 额度场景 | 8 |
| 贷款场景 | 8 |
| 征信场景 | 8 |
| 账户与业务办理 | 8 |
| 增值服务与优享卡 | 9 |
| 停止营销 | 4 |
| 语义边界与混淆 | 28 |
| 口语化表达 | 8 |
| 信息不充分场景 | 5 |
| 连续对话流程 | 15 |
| **总计** | **225** |

---

*文档生成时间：2026-04-21*
