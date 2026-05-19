# Skill 匹配优化分析报告

**生成时间**: 2026-04-18
**当前指标**: Skill Top-1 = 50.56% (domain-covered), Top-3 = 79.01%

---

## 🔍 根因分析

### 问题 1：Skill 边界语义纠缠（主因）

从混淆矩阵看，**同一域内的 skill 边界模糊**：

| 混淆对 | 次数 | 根因 |
|--------|------|------|
| `repayment_result_query` → `repayment_status_issue` | 3 | 都是"还款相关查询"，边界不清晰 |
| `repayment_status_issue` ↔ `early_loan_clearance` | 3 | 客户表达混合意图："还不了款"+"能一次性还清吗" |
| `collection_complaint` → `stop_collection` | 2 | 都是催收场景，边界依赖客户情绪而非内容 |
| `overdue_negotiation` → `early_loan_clearance` | 2 | "协商缓几天" vs "提前结清" 语义交叉 |

### 问题 2：Gold 标注过于武断

**错误样本 1：**
```
gold=repayment_status_issue pred=early_loan_clearance
对话: "为什么还不了款呢？我想问一下，借款不能一次性还清吗？提前还清利息怎么算？"
```
→ 客户**同时表达**还款失败问题 + 提前结清意图，两个 skill 都合理

**错误样本 2：**
```
gold=early_loan_clearance pred=repayment_status_issue
对话: "就是刚刚跟你们联系好说那个还款的...因为暂时不用了，就先还掉吧"
```
→ "暂时不用了就先还掉"更像是提前结清，但 gold 标为还款状态问题

**结论**：Gold 标注假设"一对话一意图"，但真实对话往往是**多意图混合**。

### 问题 3：Skill triggers.examples 覆盖不足

当前 `early_loan_clearance` 的 examples：
```yaml
examples:
  - 我要提前还款
  - 我想一次性还完
```

但真实对话是：
```
"呃，喂，为什么还不了款呢？...你们这个借款不能一次性还清吗？...提前还清利息怎么算？"
```

**问题**：
- examples 太"标准"，缺少口语化、混合意图的表达
- 缺少"边界案例"来帮助模型区分相似 skill

### 问题 4：Skill Router prompt 缺少决策边界

当前 prompt 只有：
```
1. 优先延续当前场景
2. 意图切换时选新 skill
3. 无匹配选 none
```

**缺失**：
- 明确的**决策边界规则**（如：`repayment_result_query` vs `repayment_status_issue` 怎么选）
- **多意图场景**处理策略（优先处理哪个意图）
- **决策优先级**（问题解决类 > 查询类 > 请求类？）

---

## 🎯 优化方向（按 ROI 排序）

### 方向 1：明确 Skill 边界定义（高 ROI）

**方案 A：合并相似 Skill**
- `repayment_result_query` + `repayment_status_issue` → 合并为 `repayment_inquiry`（还款查询与异常）
- 理由：两者共享大部分工具和流程，边界依赖客户是否"遇到问题"

**方案 B：补充边界判别规则**

在 skill 定义中增加 `boundary_rules`：

```yaml
# repayment_status_issue.yaml
boundary_rules:
  vs repayment_result_query:
    rule: 客户已还款但遇到异常（失败/未更新/部分扣款）→ 本 skill
          客户仅询问还款是否成功/如何查询 → repayment_result_query
  vs early_loan_clearance:
    rule: 客户先表达还款失败/异常，再问提前结清 → 优先本 skill（先解决问题）
          客户主动提出想一次性结清，无异常表述 → early_loan_clearance
```

### 方向 2：优化 Gold 标注（中 ROI）

**问题**：当前标注假设"一对话一 skill"，但 44% 错误样本是多意图混合

**方案**：
1. **双人交叉标注**：对混淆严重的 89 条样本重新标注
2. **多意图标签**：允许标注 `primary_skill` + `secondary_skills`
3. **边界案例标记**：对模棱两可的对话标记为 `ambiguous`

### 方向 3：增强 Skill Router Prompt（中 ROI）

**当前缺失**：
- 决策边界规则
- 多意图处理策略
- Few-shot 反例

**优化后 prompt 结构**：

```markdown
## 决策边界规则

当候选 skill 语义相近时，按以下规则判断：

| 优先级 | Skill 类型 | 示例 |
|--------|-----------|------|
| 1 | 问题解决类 | repayment_status_issue, deduction_issues |
| 2 | 查询类 | repayment_result_query, bill_date_credit_impact |
| 3 | 请求类 | early_loan_clearance, stop_collection |

**多意图场景**：客户同时表达"还款失败"+"想提前结清" → 优先选择问题解决类 skill

## Few-shot 边界案例

对话: "我昨天还款了，怎么还显示未还款？"
→ skill: repayment_status_issue（已还款但异常）
→ 非 repayment_result_query（不仅是查询）

对话: "还款成功了吗？我想确认一下"
→ skill: repayment_result_query（纯查询，无异常）
```

### 方向 4：扩充 triggers.examples（低 ROI，但必要）

为高频混淆的 skill 添加**边界反例**：

```yaml
# repayment_status_issue.yaml
triggers:
  examples:
    - 还款失败怎么回事  # 标准
    - 钱扣了账单没变  # 标准
    - 我昨天还款了怎么还显示未还款  # 边界：易与 repayment_result_query 混淆
    - 银行卡扣了两百多但只扣了一部分  # 边界：部分扣款
  counter_examples:  # 新增反例
    - 还款成功了吗  # → repayment_result_query
    - 我想提前还清所有贷款  # → early_loan_clearance
```

---

## 📊 预期收益

| 优化方向 | 工作量 | 预期 Top-1 提升 |
|---------|--------|----------------|
| Skill 边界定义 + prompt 规则 | 2-3 天 | +8-12pp |
| Gold 标注审核 | 1-2 天 | +3-5pp |
| 扩充 examples | 1 天 | +2-4pp |

**组合预期**：Skill Top-1 从 50% → 65-70%（在 domain-covered 情况下）

---

## 📋 混淆矩阵详情（最新测试 2026-04-18）

```
Top skill confusions (gold → pred, count):
repayment_result_query → repayment_status_issue ×3
repayment_status_issue → early_loan_clearance ×2
overdue_negotiation → early_loan_clearance ×2
collection_complaint → stop_collection ×2
overpayment_refund → repayment_status_issue ×2
early_loan_clearance → repayment_status_issue ×1
repayment_status_issue → repayment_method_inquiry ×1
repayment_status_issue → stop_collection ×1
repayment_result_query → post_loan_verification ×1
stop_collection → overdue_negotiation ×1
```

---

## 🔧 待办事项

- [ ] 实现 `boundary_rules` 字段到 skill YAML schema
- [ ] 为高频混淆 skill（repayment_status_issue, early_loan_clearance, repayment_result_query）编写边界规则
- [ ] 更新 skill_routing.md prompt，添加决策边界和多意图处理策略
- [ ] 对 89 条测试样本进行双人交叉标注审核
- [ ] 扩充 triggers.examples，添加口语化和边界案例
