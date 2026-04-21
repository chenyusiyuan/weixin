# 系统评估方案 (Evaluation Plan)

基于 `test.jsonl`（98 条真实多轮对话，人工标注）对金融客服话术推荐系统做分层评估。

## 数据情况

`test.jsonl` 每条记录：
- `call_id` — 通话唯一 ID
- `完整对话_原始` / `完整对话_清洗后` — `[坐席]` / `[客户]` 标记的多轮对话全文
- `对话轮次` — 平均 ~30-60 轮
- `一级分类` — 如"催收相关"（域级别标签）
- `二级分类` — 如"催收相关/协商还款"（业务分类）
- `服务标签` — 如"协商还款_期数"（最细粒度）
- `小结名称` / `坐席组` — 辅助信息

---

## 核心难题

1. **没有唯一正确答案**：坐席已经说过的话是 SOP 下的合规输出之一，不是唯一解。系统输出 A、坐席说了 B，A≠B 但都可能正确。不能做字符串 diff。
2. **多轮状态偏移**：让系统逐轮重放会让系统基于自己生成的虚假前文往下走，偏离真实坐席已有的上下文。
3. **成本**：98 条 × 平均 30 轮 × 1-3 s LLM ≈ 1-3 小时一次全量重放，并且烧 API。

能直接复用的硬标签：
- `一级分类` → L1 域分类金标签
- `服务标签` / `二级分类` → Skill 匹配金标签（需要人工写一份 tag → skill_id 映射）
- 对话全文 + 客户第一句 → 路由分布、延迟、合规通过率（客观）

---

## 四层实验设计

四个实验彼此独立，各管一个维度。建议按顺序跑，前面不过关就不往后推。

### Exp 1 — L1 域分类准确率（最先做）

- **目标**：评估 `DomainClassifier`（纯规则关键词）够不够用
- **输入**：每条对话的客户第一句（或前 1-3 句拼接）
- **预测**：`DomainClassifier.classify(query, empty_state)`
- **金标签**：`一级分类` 映射到 10 个业务域（需要手工写映射表，如"催收相关" → "逾期"）
- **指标**：
  - Top-1 Accuracy（主指标）
  - Top-3 Accuracy（若改成多候选召回）
  - Per-domain Precision / Recall / F1
  - Confusion matrix（找易混域）
- **决策阈值**：
  - ≥ 90% → 当前规则够用
  - 80-90% → 补规则权重 + exclude_keywords
  - < 80% → 升级为 embedding / 小模型分类
- **成本**：0 LLM 调用，< 1 分钟跑完

### Exp 2 — Skill 匹配准确率

- **前置**：手工写 `service_tag → skill_id` 映射表（50 skill × ~30 tag，约半小时）
- **输入**：客户第一句
- **流程**：L1 分类 → LLM Skill Router → 预测 `matched_skill_id`
- **金标签**：`服务标签` 映射后的 skill_id
- **指标**：
  - Top-1 / Top-3 Skill Accuracy
  - 按风险级拆分（low/medium/high）
  - 按路由模式拆分（direct_reply / tool_only / tool_rag）
  - Skill Router 平均 confidence
- **决策阈值**：Top-3 ≥ 85% 可接受，< 85% 需要调 Skill Router prompt 或扩 `triggers.examples`
- **成本**：98 × 1 LLM 调用 ≈ 3-5 分钟 + API 费

### Exp 3 — 链路分布与性能（已有雏形）

已经有 `tests/eval_offline.py`，需要扩展：

- **流程**：跑 `orchestrator.handle_turn(session_id, first_customer_msg)`
- **不需要金标签**的指标：
  - `route_a` / `route_b` / `route_c` 占比
  - P50 / P95 / P99 延迟（总耗时、LLM 耗时、工具耗时分桶）
  - Tool 调用次数分布
  - 合规通过率（comp.passed 比例）
  - Handoff 转人工比例
- **按一级分类分桶**：催收相关 vs 还款 vs 费用 的延迟/合规通过率分别看
- **期望**：Chain A 比例 ≥ 10%（验证规则短路生效）；P95 < 3s
- **成本**：98 × 1-2 LLM 调用 ≈ 5-10 分钟

### Exp 4 — 话术质量 LLM-as-judge（抽样、昂贵）

- **前置**：前 3 个实验都达标
- **流程**：抽样 20-30 条，跑系统生成 vs 坐席原话
- **重放方式**（三选一）：
  - **单轮**：仅第一句 → 第一句系统回复
  - **截断重放**（推荐）：把真实前 k 轮（客户+坐席）塞进 `ConversationState` 作为上下文，系统只生成第 k+1 轮的回复。k ∈ {3, 5, 10} 各抽样
  - **完整重放**：只在发版前做 5-10 条，太贵
- **裁判**：Opus / GPT-4 打 3 项分（1-5 分）：
  - 合规性（是否违反 forbidden_expressions）
  - 信息完整性（tool 数据是否正确呈现）
  - 语气自然度（和真实坐席风格接近度）
- **校准**：人工 spot-check 5 条确认裁判稳定性
- **成本**：~30 条 × 2 LLM 调用（系统生成 + 裁判） ≈ 半小时 + API 费

---

## 多轮对话重放的三种策略（按成本升序）

| 策略 | 覆盖实验 | 成本 | 描述 |
|------|---------|------|------|
| **单轮快评** | Exp 1 / 2 | ¥0.1 级 | 只喂客户第一句，评分类和 Skill 匹配 |
| **截断重放** | Exp 3 / 4 | ¥1 级 | 把真实前 k 轮灌进 state，评第 k+1 轮 |
| **完整重放** | Demo 级验证 | ¥10+ 级 | 系统逐轮生成直到对话终止，只做 5-10 条 |

---

## 实施优先级

1. **先做 Exp 1**（20 分钟出结果，0 成本）— 回答"L1 规则分类够不够"
2. **人工写 tag→skill_id 映射表**（半小时）— Exp 2/4 的前置
3. **做 Exp 2**（5 分钟）— 回答"Skill 路由精排准不准"
4. **扩展 Exp 3**（复用现有 eval_offline.py）— 回答"系统跑起来是否健康"
5. **最后做 Exp 4** — 只在前 3 个都过关后做

---

## 脚本规划（待实现）

```
scripts/
├── eval_l1_domain.py           # Exp 1
├── eval_skill_match.py         # Exp 2
├── eval_chain_distribution.py  # Exp 3（扩展 tests/eval_offline.py）
├── eval_script_quality.py      # Exp 4（LLM-as-judge）
└── references/
    ├── domain_gold_mapping.json    # 一级分类 → 10 域
    └── skill_gold_mapping.json     # 服务标签 → skill_id
```

## 关键决策点

- **Chain A/B/C 路由分布**异常偏向 C？→ 说明 Skill Router 置信度阈值过高或 skill triggers 不全
- **L1 错分率高**？→ 先补 `DOMAIN_KEYWORDS` 权重和 exclude，再考虑 embedding
- **合规通过率 < 95%**？→ 检查 forbidden_expressions 是否过严（误伤）或 Agent A prompt 约束不足
- **P95 延迟 > 3s**？→ 检查 tool 并行度和 LLM 温度/max_tokens 配置

---

_最后更新：基于 test.jsonl 98 条真实对话。评估计划独立于 v/ 旧 RAG 架构，只评估当前 Skill-based 系统。_
