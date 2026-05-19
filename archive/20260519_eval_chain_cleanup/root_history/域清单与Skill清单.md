# 域清单与Skill清单

## 1. 范围与整理原则

- 整理范围：`skills/registry.json` 中登记的 11 个域、54 个 skill，`skills/definitions/*.yaml` 中的详细定义，以及 `sop/` 目录下保留的业务 SOP 资产。
- 映射原则：优先按同名 / 同意图直接映射；若 skill 明确合并多个相邻 SOP 场景，则标注为“一对多合并”；若 skill 没有独立 SOP 文件但显然来自多域共性步骤，则标注为“跨域共性抽取”。
- 结果口径：共 54 个 skill，其中 49 个业务 skill 对应 50 份 QA SOP；另有 5 个“会话流程” skill 是从多个 SOP 的开场、核身、确认、结束等共性节点抽象出来的。
- 映射分类口径：
  - `48` 个 skill 与 `48` 份 QA SOP 为严格一一对应
  - `1` 个 skill 由 `2` 份 QA SOP 合并而来
  - `5` 个 skill 属于相对 SOP 的新增抽象能力

## 2. Skill 域清单

| 域 | Skill 数 | 对应 SOP 目录 | SOP 资产规模 | 备注 |
|---|---:|---|---|---|
| 会话流程 | 5 | `无独立目录（抽象自多域 SOP 共性节点）` | 无独立 QA 文件 | skill新增，跨域通用能力 |
| 账户 | 3 | `sop/账户问题` | 3 份 QA + 1 份流程 | 一一对应 |
| 还款 | 8 | `sop/还款问题` | 9 份 QA + 1 份流程 | 8 个 skill 覆盖 9 份 QA，其中 1 个 skill 为合并映射 |
| 费用 | 9 | `sop/费用问题` | 9 份 QA + 1 份流程 | 一一对应 |
| 业务办理 | 7 | `sop/业务场景办理问题` | 7 份 QA + 1 份流程 | 一一对应 |
| 活动 | 5 | `sop/活动问题` | 5 份 QA + 1 份流程 | 一一对应 |
| 逾期 | 5 | `sop/逾期问题` | 5 份 QA + 1 份流程 | 一一对应 |
| 贷款 | 4 | `sop/贷款问题` | 4 份 QA + 1 份流程 | 一一对应 |
| 会员 | 3 | `sop/会员问题` | 3 份 QA + 1 份流程 | 一一对应 |
| 额度 | 2 | `sop/额度问题` | 2 份 QA + 1 份流程 | 一一对应 |
| 优享卡 | 3 | `sop/优享卡问题` | 3 份 QA + 1 份流程 | 一一对应 |

## 3. 具体 Skill 清单（逐项对应 SOP）

### 3.1 会话流程

- 领域 SOP：无独立目录，主要来自各域 QA 中重复出现的“开头语 / 核身 / 承接 / 结束语”等共性节点。
- 补充参考：`sop/clean/02_cleaned/*.json` 中也能看到这些共性节点被清洗后重复保留下来。

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `greeting_opening` | 开场寒暄 | `direct_reply` / `low` | 会话流程 / 开场寒暄 / 通用 | `各业务 QA 文件中的“开头语”步骤` | 跨域共性抽取；无独立 SOP 文件 |
| `identity_readback` | 核身信息回答 | `direct_reply` / `low` | 会话流程 / 核身回答 / 通用 | `各业务 QA 文件中的“验证用户信息/核身问答”步骤` | 跨域共性抽取；把核身回答单独沉淀为通用会话 skill |
| `acknowledgement` | 应答确认 | `direct_reply` / `low` | 会话流程 / 应答确认 / 通用 | `各业务 QA 文件中的“收到/确认/继续沟通”常见承接话术` | 跨域共性抽取；无独立 SOP 文件 |
| `channel_check` | 会话状态确认 | `direct_reply` / `low` | 会话流程 / 通话确认 / 通用 | `各业务 QA 文件中隐含的“确认会话状态/听得见吗”节点` | 跨域共性抽取；补足 SOP 中弱结构化的通话控制能力 |
| `closing` | 结束语 | `direct_reply` / `low` | 会话流程 / 结束语 / 通用 | `各业务 QA 文件中的“邀评/结束语”步骤` | 跨域共性抽取；无独立 SOP 文件 |

### 3.2 账户

- 领域流程 SOP：`sop/账户问题/账户问题流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `account_cancellation` | 注销账户 | `tool_only` / `high` | 信息维护 / 注销账户 / 账户 | `sop/账户问题/注销账户QA.xlsx` | 直接一一对应 |
| `deactivated_customer_service` | 已注销客户进线服务 | `tool_only` / `medium` | 信息维护 / 已注销客户 / 账户 | `sop/账户问题/已注销客户进线办理业务QA.xlsx` | 主映射；其中征信/发票等子路径会借用相邻业务 SOP 继续处理 |
| `special_account_cancellation` | 特殊场景注销账户 | `tool_only` / `high` | 信息维护 / 特殊注销 / 账户 | `sop/账户问题/特殊场景注销账号QA.xlsx` | 直接一一对应 |

### 3.3 还款

- 领域流程 SOP：`sop/还款问题/还款问题流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `bill_date_credit_impact` | 账单日还款是否影响征信 | `tool_only` / `medium` | 还款相关 / 征信影响 / 还款 | `sop/还款问题/8.账单日还款是否影响征信？.xlsx` | 直接一一对应 |
| `card_rebinding` | 换绑银行卡 | `direct_reply` / `low` | 还款相关 / 换绑银行卡 / 还款 | `sop/还款问题/7.如何换绑银行卡？.xlsx` | 直接一一对应 |
| `deduction_issues` | 扣款相关问题咨询 | `tool_only` / `medium` | 还款相关 / 扣款问题 / 还款 | `sop/还款问题/9.扣款相关问题咨询.xlsx` | 直接一一对应 |
| `early_deduction` | 未到还款日被提前扣款 | `tool_only` / `medium` | 还款相关 / 提前扣款 / 还款 | `sop/还款问题/6.未到还款日被提前扣款.xlsx` | 直接一一对应 |
| `early_loan_clearance` | 提前清贷需求 | `tool_only` / `high` | 还款相关 / 提前清贷 / 还款 | `sop/还款问题/2.提前清贷需求.xlsx` | 直接一一对应 |
| `repayment_method_inquiry` | 咨询还款方式 | `direct_reply` / `low` | 还款相关 / 还款方式咨询 / 还款 | `sop/还款问题/1.咨询还款方式.xlsx` | 直接一一对应 |
| `repayment_result_query` | 查询还款结果 | `tool_only` / `low` | 还款相关 / 还款结果查询 / 还款 | `sop/还款问题/4.如何查询还款结果？.xlsx` | 直接一一对应 |
| `repayment_status_issue` | 还款状态异常 | `tool_only` / `medium` | 还款相关 / 还款状态异常 / 还款 | `sop/还款问题/3.还款失败怎么处理？.xlsx`；`sop/还款问题/5.已还款怎么没更新？.xlsx` | 一对多合并；skill 站在客户视角统一承接“还款异常/没更新/部分扣款” |

### 3.4 费用

- 领域流程 SOP：`sop/费用问题/费用流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `bill_deduction_query` | 查询账单扣款情况 | `tool_only` / `medium` | 费用相关 / 账单扣款查询 / 费用 | `sop/费用问题/7.查询账单扣款情况.xlsx` | 直接一一对应 |
| `fee_consultation_tier1` | 费用咨询（一线） | `tool_only` / `medium` | 费用相关 / 费用咨询 / 费用 | `sop/费用问题/1.费用咨询（一线）.xlsx` | 直接一一对应 |
| `fee_consultation_tier2` | 费用咨询（二线/高阶内诉） | `tool_rag` / `medium` | 费用相关 / 费用咨询(二线) / 费用 | `sop/费用问题/2.费用咨询（内诉：二线&高阶）.xlsx` | 直接一一对应 |
| `fee_detail_query` | 查询费用明细及综合费率 | `tool_only` / `medium` | 费用相关 / 费用明细查询 / 费用 | `sop/费用问题/6.查询费用明细（待还&已还）及综合费率.xlsx` | 直接一一对应 |
| `fee_refund_status` | 退费未到账情况咨询 | `tool_only` / `low` | 费用相关 / 退费进度 / 费用 | `sop/费用问题/5.退费未到账情况咨询.xlsx` | 直接一一对应 |
| `fee_refund_tier1` | 要求退费（一线） | `tool_only` / `medium` | 费用相关 / 要求退费 / 费用 | `sop/费用问题/3.要求退费（一线）.xlsx` | 直接一一对应 |
| `fee_refund_tier2` | 要求退费（二线/高阶内诉） | `tool_rag` / `high` | 费用相关 / 要求退费(二线) / 费用 | `sop/费用问题/4.要求退费（内诉：二线&高阶）.xlsx` | 直接一一对应 |
| `loan_dispute_refund` | 借款争议特殊场景退费 | `tool_only` / `high` | 费用相关 / 借款争议 / 费用 | `sop/费用问题/9.借款争议（特殊场景退费）.xlsx` | 直接一一对应 |
| `overpayment_refund` | 客户对公转账出错退溢余 | `tool_only` / `medium` | 费用相关 / 退溢余 / 费用 | `sop/费用问题/8.客户对公转账出错相关咨询（退溢余）.xlsx` | 直接一一对应 |

### 3.5 业务办理

- 领域流程 SOP：`sop/业务场景办理问题/业务办理流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `cancel_credit_authorization` | 注销授信额度 | `tool_only` / `high` | 业务办理 / 注销授信额度 / 业务办理 | `sop/业务场景办理问题/注销授信额度QA.xlsx` | 直接一一对应 |
| `clearance_certificate` | 开具结清证明 | `tool_only` / `medium` | 业务办理 / 开具结清证明 / 业务办理 | `sop/业务场景办理问题/开具结清证明QA.xlsx` | 直接一一对应 |
| `contract_retrieval` | 调取合同 | `tool_only` / `medium` | 业务办理 / 调取合同 / 业务办理 | `sop/业务场景办理问题/调取合同QA.xlsx` | 直接一一对应 |
| `credit_inquiry` | 征信问题咨询 | `tool_rag` / `high` | 业务办理 / 征信咨询 / 业务办理 | `sop/业务场景办理问题/征信问题咨询QA.xlsx` | 直接一一对应 |
| `credit_modification` | 修改征信 | `tool_only` / `high` | 业务办理 / 修改征信 / 业务办理 | `sop/业务场景办理问题/修改征信QA.xlsx` | 直接一一对应 |
| `invoice_issuance` | 发票开具 | `tool_only` / `medium` | 业务办理 / 发票开具 / 业务办理 | `sop/业务场景办理问题/发票开具QA.xlsx` | 直接一一对应 |
| `other_certificate` | 开具其他证明 | `tool_only` / `medium` | 业务办理 / 开具其他证明 / 业务办理 | `sop/业务场景办理问题/开具其他证明QA.xlsx` | 直接一一对应 |

### 3.6 活动

- 领域流程 SOP：`sop/活动问题/活动问题流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `cancel_value_added_service` | 取消增值服务 | `tool_only` / `medium` | 营销活动 / 取消增值服务 / 活动 | `sop/活动问题/2.怎么取消增值服务QA.xlsx` | 直接一一对应 |
| `light_card_cancel_refund` | 轻享卡取消退费 | `tool_only` / `medium` | 营销活动 / 轻享卡取消退费 / 活动 | `sop/活动问题/5.怎么取消(退)轻享卡QA.xlsx` | 直接一一对应；SOP 本身已把取消与退费合并 |
| `refund_value_added_service` | 退增值服务费 | `tool_only` / `medium` | 营销活动 / 退增值服务费 / 活动 | `sop/活动问题/3.怎么退增值服务费QA.xlsx` | 直接一一对应 |
| `stop_marketing` | 停止营销 | `direct_reply` / `low` | 营销活动 / 停止营销 / 活动 | `sop/活动问题/4.停止营销QA.xlsx` | 直接一一对应 |
| `value_added_service_inquiry` | 增值服务咨询 | `direct_reply` / `low` | 营销活动 / 增值服务咨询 / 活动 | `sop/活动问题/1.增值服务咨询QA.xlsx` | 直接一一对应 |

### 3.7 逾期

- 领域流程 SOP：`sop/逾期问题/逾期问题流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `close_pre_reminder` | 关闭预提醒服务 | `tool_only` / `low` | 催收相关 / 关闭预提醒 / 逾期 | `sop/逾期问题/关闭预提醒服务QA.xlsx` | 直接一一对应 |
| `collection_complaint` | 投诉催收 | `tool_rag` / `high` | 催收相关 / 投诉催收 / 逾期 | `sop/逾期问题/投诉催收QA.xlsx` | 直接一一对应 |
| `overdue_negotiation` | 协商还款 | `tool_rag` / `high` | 催收相关 / 协商还款 / 逾期 | `sop/逾期问题/协商还款QA.xlsx` | 直接一一对应 |
| `post_loan_verification` | 核实贷后信息 | `tool_only` / `medium` | 催收相关 / 核实贷后信息 / 逾期 | `sop/逾期问题/核实贷后信息QA.xlsx` | 直接一一对应 |
| `stop_collection` | 要求停催 | `tool_rag` / `high` | 催收相关 / 要求停催 / 逾期 | `sop/逾期问题/要求停催QA.xlsx` | 直接一一对应 |

### 3.8 贷款

- 领域流程 SOP：`sop/贷款问题/贷款问题流程梳理11.27.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `disbursement_progress` | 放款进度查询 | `tool_only` / `low` | 申请咨询 / 放款进度 / 贷款 | `sop/贷款问题/放款进度查询QA.xlsx` | 直接一一对应 |
| `loan_consultation` | 贷款咨询 | `tool_only` / `low` | 申请咨询 / 贷款咨询 / 贷款 | `sop/贷款问题/贷款咨询QA.xlsx` | 直接一一对应 |
| `loan_termination` | 贷款解约 | `tool_only` / `high` | 申请咨询 / 贷款解约 / 贷款 | `sop/贷款问题/贷款解约QA.xlsx` | 直接一一对应 |
| `remote_disbursement` | 异地放款 | `tool_only` / `medium` | 申请咨询 / 异地放款 / 贷款 | `sop/贷款问题/异地放款QA.xlsx` | 直接一一对应 |

### 3.9 会员

- 领域流程 SOP：`sop/会员问题/会员问题流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `member_cancel` | 取消会员 | `tool_only` / `medium` | 会员服务 / 取消会员 / 会员 | `sop/会员问题/2.怎么取消会员（先享后付）？.xlsx` | 直接一一对应 |
| `member_consultation` | 会员咨询 | `tool_only` / `low` | 会员服务 / 会员咨询 / 会员 | `sop/会员问题/1.什么是会员（会员咨询）？.xlsx` | 直接一一对应 |
| `member_refund` | 退会员费用 | `tool_only` / `medium` | 会员服务 / 退会员费用 / 会员 | `sop/会员问题/3.怎么退会员费用？.xlsx` | 直接一一对应 |

### 3.10 额度

- 领域流程 SOP：`sop/额度问题/额度问题流程梳理12.3.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `no_quota_issue` | 无额度问题 | `tool_only` / `medium` | 产品与信息 / 额度问题 / 无额度 | `sop/额度问题/无额度问题QA.xlsx` | 直接一一对应 |
| `quota_consultation` | 额度咨询 | `tool_only` / `low` | 产品与信息 / 额度咨询 / 额度 | `sop/额度问题/额度咨询QA.xlsx` | 直接一一对应 |

### 3.11 优享卡

- 领域流程 SOP：`sop/优享卡问题/优享卡流程梳理.docx`

| skill_id | Skill 名称 | 路由 / 风险 | 意图层级 | 对应 SOP | 映射关系 |
|---|---|---|---|---|---|
| `premium_card_cancel` | 取消优享卡 | `tool_only` / `medium` | 优享卡服务 / 取消优享卡 / 优享卡 | `sop/优享卡问题/2.怎么取消优享卡？.xlsx` | 直接一一对应 |
| `premium_card_inquiry` | 优享卡咨询 | `tool_only` / `low` | 优享卡服务 / 优享卡咨询 / 优享卡 | `sop/优享卡问题/1.咨询优享卡是什么？有什么权益？.xlsx` | 直接一一对应 |
| `premium_card_refund` | 退优享卡费用 | `tool_only` / `medium` | 优享卡服务 / 退优享卡费用 / 优享卡 | `sop/优享卡问题/3.怎么退优享卡费用？.xlsx` | 直接一一对应 |

## 
