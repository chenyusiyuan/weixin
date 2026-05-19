# Skill Routing 分析报告（2026-04-19）

## 背景

基于最新离线评测结果：

### Exp 1: L1 Domain Classifier（2026-04-17）
- Samples: 95
- Overall accuracy: 65.26% (62/95)
- Top-3 recall: 90.53% (86/95)

### Exp 2: Skill Match（2026-04-18 最新）
- Samples: 89
- Domain covered (L1 Top-3): 91.01% (81/89)
- Skill Top-1 accuracy: 50.56% (45/89)
- Skill Top-3 accuracy: 71.91% (64/89)
- Skill Top-1 | domain-covered: 55.56% (45/81)
- Skill Top-3 | domain-covered: 79.01% (64/81)

按风险级别：
- low (n=9): Top-1=22.22%, Top-3=66.67%
- medium (n=34): Top-1=38.24%, Top-3=61.76%
- high (n=46): Top-1=65.22%, Top-3=80.43%

---

## 结论摘要

当前问题更像是 **Skill Router 在 domain 已覆盖前提下的精排能力不足**，而不是单纯的标注数据质量问题。

更准确地说，现阶段最可能的主因是：
1. **skill 定义边界重叠严重**
2. **router prompt / 候选判别机制不够“可区分”**
3. **评测输入仅用客户第一句，信息量不足**
4. **部分 gold 映射可能有噪声，但更像次要因素**

我的判断不是“标注问题”或“skill/prompt 问题”二选一，而是：
- **主因优先怀疑 skill 边界 + prompt 排序能力**
- **次因再看服务标签到 skill_id 的映射质量**

---

## 为什么更像精排问题，而不是纯标注问题

从结果形态看：
- L1 的 `Top-3 recall = 90.53%`
- Skill 在 `domain-covered` 条件下，`Top-3 = 79.01%`
- 但 `Top-1 = 55.56%`

这说明：
- 正确域大多数已经被召回
- 正确 skill 也经常已经进入候选范围
- 但模型无法稳定排到第一

这是一种很典型的“**召回尚可，精排不足**”形态。

如果主要问题是标注脏，通常会看到：
- Top-3 也会明显更差
- 或者出现大量“人工都难以判断唯一 gold”的样本

但你当前的结果更像是：**候选里有答案，但同域内多个相近 skill 很难区分**。

---

## 仓库证据与支持判断

### 1. 评测计划本身将 Skill Router 问题指向 prompt / examples
`tests/EVAL_PLAN.md` 中明确写了：
- Skill Match 的决策阈值：`Top-3 ≥ 85% 可接受，< 85% 需要调 Skill Router prompt 或扩 triggers.examples`
- 当前实际 `Skill Top-3 = 71.91%`，`domain-covered Top-3 = 79.01%`，尚未达标

这与当前观察到的问题一致：更像 router prompt 或 skill triggers/examples 设计不足。

### 2. 多个 skill 存在高语义重叠
在 `skills/definitions/` 下可以看到一些明显的重叠簇：

#### 征信相关
- `skills/definitions/credit_inquiry.yaml`
- `skills/definitions/credit_modification.yaml`
- `skills/definitions/cancel_credit_authorization.yaml`

这些 skill 都会频繁出现“征信”“额度”“删除/修改”等接近表述，但客户真实表达时经常混在一起，比如：
- “征信上这个能删吗”
- “额度能不能关掉，不想影响征信”
- “你们帮我把征信改掉”

如果 skill 没有明确写出“什么时候选我，不选相邻 skill”，LLM 很容易在同域内误排。

#### 退款相关
- `skills/definitions/fee_refund_tier1.yaml`
- `skills/definitions/fee_refund_tier2.yaml`
- `skills/definitions/member_refund.yaml`
- `skills/definitions/premium_card_refund.yaml`
- `skills/definitions/refund_value_added_service.yaml`
- `skills/definitions/loan_dispute_refund.yaml`
- `skills/definitions/overpayment_refund.yaml`

“退款/退费/退钱”在多个 skill 中共享，是典型的高混淆簇。

#### 催收 / 逾期相关
- `skills/definitions/stop_collection.yaml`
- `skills/definitions/collection_complaint.yaml`
- `skills/definitions/overdue_negotiation.yaml`

“不要再打电话了”“我要投诉”“能不能协商分期”在真实表达中常常出现在同一段对话里，边界不清会显著影响 Top-1。

---

## 最可能的 5 类根因

### 根因 1：Skill 边界定义重叠，缺少判别式约束
当前 definitions 更像“描述 skill 是什么”，但还不够像“告诉 router 为什么是我而不是隔壁 skill”。

常见问题：
- 有关键词，但没有相邻 skill 的排除规则
- 有 examples，但 examples 多是同义表达扩写，不是区分性对照样例
- 定义了意图，但没有定义“最小判别特征”

结果就是：
- Top-3 能进候选
- Top-1 不稳定

### 根因 2：`triggers.examples` 更像召回样本，不像排序样本
评测计划中已经提示：若 Skill Top-3 不达标，应优先调 `Skill Router prompt` 或扩 `triggers.examples`。

问题在于，如果 examples 只是堆更多同义句，通常更利于“召回”，未必更利于“排序”。

真正对精排有帮助的是：
- 和相邻 skill 的**对比样本**
- 明确表达“这句话为什么是 A，不是 B”

### 根因 3：部分 skill 的设计粒度偏“流程阶段”，而不是“首句意图”
例如：
- `fee_refund_tier1`
- `fee_refund_tier2`

这两个 skill 的差异更像服务处理阶段 / 升级阶段，而不一定是客户首句能稳定表达出来的主意图。

如果 Exp 2 的输入仅为“客户第一句”，那模型很难只凭第一句判断：
- 是普通退费
- 还是升级到二线/高阶内诉的退费

这种设计会天然压低 Skill Match 的上限。

### 根因 4：评测输入过弱，只用“客户第一句”不足以支撑细粒度 skill 判别
`tests/EVAL_PLAN.md` 中 Exp 2 的输入是“客户第一句”。

这对于评估粗粒度 intent 可以，但对细 skill 路由未必够：
- 有些 skill 依赖机构类型
- 有些 skill 依赖是否已结清
- 有些 skill 依赖是否已投诉升级
- 有些 skill 依赖是否非本人借款

这些信息很多在第一句并不会出现。

这意味着：
- 模型不是一定“不会判”
- 也可能是“当前输入不够判”

### 根因 5：高风险 skill 准确率更高，说明强边界 / 强约束定义是有效的
你当前结果里：
- high: Top-1=65.22%
- medium: Top-1=38.24%
- low: Top-1=22.22%

这反而提供了一个很有价值的信号：
- 高风险 skill 因为合规要求强、边界清晰、触发词更明显，所以更容易判对
- low / medium skill 往往更泛、更像日常咨询类，边界松散，所以更容易混淆

这说明：**边界清晰度与可判别性是当前效果的关键变量**。

---

## 标注数据质量要不要查？要，但优先级次于边界设计

### 需要重点检查的 3 类标注问题

#### 1. `服务标签 -> skill_id` 映射是否存在系统性噪声
根据 `tests/EVAL_PLAN.md`，Skill Match 依赖人工写的 `service_tag -> skill_id` 映射。

这个环节很容易出问题：
- 原始服务标签粒度和 skill 粒度不一致
- 一个服务标签可能对应多个可接受 skill
- 一些 gold skill 是“主处理方案”，但客户首句只暴露了上位意图

#### 2. 单标签评测假设可能过强
某些客户首句本身就是多意图：
- “别催了，我也想协商分期”
- “你们退钱，不然我要投诉”

若评测只允许一个 gold skill，会把“合理的次优意图命中”都算成错。

#### 3. 整通电话标签与第一句输入时点不一致
`服务标签` 很可能描述的是“整通电话最终处理主题”，而不是“第一句能判断出的意图”。

如果客户第一句只是：
- 开场抱怨
- 状态确认
- 含糊咨询

但最终通话被标成一个细粒度服务标签，那么“首句预测细 skill”天然会受损。

---

## 优化方向（按优先级排序）

## P0：先做错例分桶，不要立刻盲改 prompt

建议先把当前错例拆成几类：
1. **同域相邻 skill 误判**
2. **输入信息不足，首句不可判**
3. **gold 映射可争议 / 多个 skill 都合理**
4. **明显 router 排序错误**

尤其应该输出高频 confusion pair，例如：
- `credit_inquiry` ↔ `credit_modification`
- `cancel_credit_authorization` ↔ `credit_modification`
- `fee_refund_tier1` ↔ `fee_refund_tier2`
- `stop_collection` ↔ `collection_complaint`
- `overdue_negotiation` ↔ `stop_collection`

如果错例主要集中在这些 pair，就说明应该优先改边界定义，而不是先扩数据量。

---

## P1：重写 skill 定义，让它们“可判别”

建议为每个 skill 增加 3 类结构化字段：

### 1. `choose_when`
明确：出现哪些核心证据时优先选择该 skill。

### 2. `do_not_choose_when`
明确：当出现哪些信号时，不应选该 skill，而应该让给相邻 skill。

### 3. `disambiguation_questions`
当信息不足时，应该补问哪些问题来区分相邻 skill。

### 示例
以征信相关簇为例：
- “我要查会不会上征信” → `credit_inquiry`
- “我要删除征信逾期记录” → `credit_modification`
- “我要把授信额度注销掉” → `cancel_credit_authorization`

这种“对比式样例”对精排的帮助远大于继续补大量同义表达。

---

## P2：把“流程阶段 skill”改为“父 skill + 子状态”

像 `fee_refund_tier1` / `fee_refund_tier2` 这种如果本质差异在处理阶段，而不是首句意图，建议考虑：

- 首句先统一路由到父 skill，例如 `fee_refund`
- 再根据：
  - 是否已一线处理
  - 是否明确升级诉求
  - 是否投诉升级
  - 是否超权限

进入 tier1 / tier2 子流程

这样可以显著减少“首句细分过度”导致的误判。

---

## P3：改 Skill Router 的判别方式，而不是只改 wording

当前更建议做的是“判别式路由”，而不是“更长的 prompt”。

可以尝试的方式：

### 方案 A：排除式推理
让模型输出：
- Top-1 skill
- Top-2/Top-3 候选
- 为什么不是另外两个最像的 skill

这会逼迫模型显式区分近邻 skill。

### 方案 B：两阶段路由
- 第一阶段：先做 coarse intent cluster
- 第二阶段：在 cluster 内做 pairwise rerank

这种方案通常对“同域近邻 skill”有明显帮助。

---

## P4：升级评测输入，比较“首句 vs 前 2~3 轮摘要”

建议做一个输入 A/B 测试：
- V1：客户第一句
- V2：客户前两句
- V3：前 2~3 轮摘要

如果 V3 相比 V1 明显提升，而 prompt 不变，则说明：
- 当前主要瓶颈不是模型能力
- 而是输入信息不足

这能帮助你避免在错误方向上过度优化 prompt。

---

## P5：不要泛泛扩数据，要补“硬负样本”

当前如果要补数据，优先补：
- 每个高混淆 skill 的正例
- 与相邻 skill 的负例 / 对照例

例如 `stop_collection`：
- 正例：明确要求停止催收
- 负例 1：其实是在投诉催收方式 → `collection_complaint`
- 负例 2：其实是在请求延期/分期 → `overdue_negotiation`

目标不是增加覆盖，而是**增加边界锐度**。

---

## 如何快速判断“到底是不是标注问题”

建议做一个低成本人工复核实验：

### 抽样方案
- 从 Skill Top-1 错例中抽 30 条

### 每条复核 4 件事
1. 当前 gold 是否唯一合理
2. 模型预测是否也合理
3. 是否应该允许多标签
4. 是否仅凭第一句根本无法判断

### 判断标准
如果 >25% 的错例被判定为以下任一情况：
- 预测也合理
- gold 不唯一
- 首句不可判

那么评测集或 gold 映射就需要重构。

如果大多数错例都能一致认定 gold 唯一且模型明显选错，那么问题主要还是在 skill 边界与 router 上。

---

## 我对问题优先级的判断

当前最值得优先排查的顺序：

1. **Skill 边界定义是否重叠，是否缺少排除规则**
2. **Skill Router prompt / rerank 机制是否足够判别式**
3. **Exp 2 输入是否过弱（仅首句）**
4. **service_tag -> skill_id 映射是否存在噪声**
5. **是否需要扩更多测试数据**

也就是说：

> 现在不是先盲目扩测试集的时候，
> 而是应该先通过错例结构分析明确“错在哪一层”。

否则新增样本大概率只会重复放大现有混淆。

---

## 建议的下一步执行顺序

### 第一步：做 confusion matrix
输出 Top-1 错误中最常见的前 10 个 skill 混淆对。

### 第二步：对每个混淆对补判别规则
为高频混淆 skill 对补：
- `choose_when`
- `do_not_choose_when`
- 对比样例
- 反例样例

### 第三步：审视是否存在“流程阶段 skill”
把首句无法稳定判定的 tier / stage skill 折叠成父 skill + 子流程。

### 第四步：做输入信息量 A/B 测试
比较：
- 首句
- 前两句
- 前 2~3 轮摘要

### 第五步：抽样人工复核 30 条错例
判断：
- 有多少是真错
- 有多少是 gold 可争议
- 有多少是输入不足

---

## 总结

一句话总结：

> 你的问题更像“domain 召回已经够了，但同域 skill 精排不够锐”，
> 主因优先在 skill 边界和 router 判别机制，
> 标注质量需要检查，但更像第二优先级。

因此最值得优先做的不是盲目扩测试集，而是：
- 先做错例分桶
- 找高频混淆对
- 强化 skill 判别边界
- 再决定补哪些数据

