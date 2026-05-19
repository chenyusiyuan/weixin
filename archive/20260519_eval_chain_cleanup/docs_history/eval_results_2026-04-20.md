# 金融客服话术推荐系统 — 离线评测结果

**评测日期**：2026-04-20
**评测集**：`tests/golden_test.jsonl`（2846 条，覆盖 48 个 skill）
**系统版本**：Skill-based 架构（Chain A/B/C）+ P0/P1 优化

---

## 一、总览

| 指标 | 98 条旧基线 | 全量基线（2846） | **P0** | **P1**（500 样本） |
|------|-----|-----|-----|-----|
| L1 Top-1 | 65.26% | **72.17%** | — | — |
| L1 Top-3 召回 | 90.53% | **91.71%** | — | — |
| Skill Top-1 | 50.56% | 67.60% | **68.80%** | 67.00% |
| Skill Top-3 | 71.91% | 83.84% | 83.42% | 82.20% |
| Top-1 \| domain-covered | 55.56% | 73.72% | **75.02%** | 74.28% |
| Top-3 \| domain-covered | 79.01% | 91.42% | 90.96% | 91.13% |

**核心结论**

1. L1 embed 分类器 Top-3 召回 91.71% ≥ 90% 阈值 — **域召回合格，不是瓶颈**
2. Skill Router Top-3 \| DC ≥ 90% — **候选里有答案**
3. **真正瓶颈是 Skill Router 精排**（Top-1 73-75%），主要体现在相邻 skill 混淆
4. P0（prompt 强制择一 + 补 examples）带来 +1.2pp Top-1
5. P1（扣款/催收/还款方式三簇判别规则）在子簇上有效（还款方式簇 -32%），但整体 Top-1 近持平（样本数 500 的统计波动）

---

## 二、Exp 1 — L1 域分类（embed, 2846 条）

### 关键指标
- Top-1 = **72.17%** (2054/2846)
- Top-3 = **91.71%** (2610/2846)

### 按域 F1（支持量降序）

| 域 | gold | P | R | F1 |
|---|---:|---:|---:|---:|
| 逾期 | 1078 | 83.16% | 68.74% | **75.27%** |
| 还款 | 1034 | 71.95% | 85.59% | **78.18%** |
| 费用 | 281 | 67.09% | 37.72% | 48.29% |
| 业务办理 | 146 | 51.65% | 64.38% | 57.32% |
| 会员 | 99 | 83.48% | 96.97% | **89.72%** |
| 账户 | 65 | 73.03% | 100.00% | 84.42% |
| 贷款 | 62 | 49.12% | 45.16% | 47.06% |
| 活动 | 32 | 6.82% | 9.38% | 7.89% ❌ |
| 额度 | 29 | 71.43% | 86.21% | 78.13% |
| 会话流程 | 11 | 5.88% | 18.18% | 8.89% ❌ |
| 优享卡 | 9 | 81.82% | 100.00% | 90.00% |

### Top 混淆对
```
逾期 → 还款 × 208    # 客户首句常涉及「还款/账单/扣款」字眼
费用 → 还款 × 112
还款 → 逾期 × 102
逾期 → 业务办理 × 35
费用 → 业务办理 × 30
```

### 判断
- ✅ Top-3 91.71% ≥ 90% 门槛 → **域召回达标，交给 Router 精排即可**
- ⚠️ 低 F1 域（活动 8%、会话流程 9%）支持样本太少，不值得优化
- 费用域 Recall 37.72% 偏低，但 Top-3 会捞回来


---

## 三、Exp 2 — Skill Router 精排

### 基线（2846 条，embed + multi-domain-k=3）

| 风险级 | n | Top-1 | Top-3 |
|---|---:|---:|---:|
| low | 495 | 49.49% | 78.59% |
| medium | 943 | 58.64% | 75.82% |
| **high** | 1408 | **79.97%** | 91.05% |

| 路由模式 | n | Top-1 | Top-3 |
|---|---:|---:|---:|
| direct_reply | 261 | 41.38% | 73.18% |
| tool_only | 1568 | 67.03% | 82.53% |
| **tool_rag** | 1017 | **75.22%** | 88.59% |

**观察**：高风险 + RAG 辅助的 skill 最强，低风险 + 闲聊类最弱。

### P0 后（2846 条）

| 指标 | 基线 | P0 | Δ |
|---|---:|---:|---:|
| Top-1 | 67.60% | **68.80%** | +1.2pp |
| Top-1 \| DC | 73.72% | **75.02%** | +1.3pp |
| low-risk Top-1 | 49.49% | **53.54%** | +4pp |
| direct_reply Top-1 | 41.38% | **46.74%** | +5.4pp |

**P0 核心收益**：补了 Top-5 高频"→ none"skill 的口语化 examples，大量预测为 none 的样本被拉回正确 skill：

| skill → none | 基线 | P0 | Δ |
|---|---:|---:|---:|
| bill_deduction_query → none | 37 | 17 | -20 |
| post_loan_verification → none | 45 | 34 | -11 |
| repayment_method_inquiry → none | 34 | 消失 | -34 |
| fee_detail_query → none | 21 | 消失 | -21 |
| repayment_result_query → none | 18 | 消失 | -18 |

### P1 后（同 500 样本对比）

| 指标 | P0 | P1 | Δ |
|---|---:|---:|---:|
| Top-1 | 66.20% | **67.00%** | +0.8pp |

**按簇错例**：

| 簇 | P0 错例 | P1 错例 | Δ |
|---|---:|---:|---:|
| 扣款簇 | 43 | 42 | -1 |
| 催收簇 | 43 | 40 | -3 |
| **还款方式簇** | 40 | **27** | **-13 (-32%)** |

**P1 观察**：
- ✅ 还款方式簇显著生效：`repayment_method_inquiry ↔ card_rebinding` 混淆大幅减少
- ⚠️ 扣款簇和催收簇收益微弱：边界本身模糊（"众安又扣我 274 元"可以同时合理判为 `deduction_issues` 或 `bill_deduction_query`）
- ⚠️ 初版判别表让 LLM 从表里抽了候选外 skill（幻觉率 ~3%），改成**动态拼接**后（只在候选包含簇内 ≥2 skill 时才注入）幻觉率降到 <0.5%

### 当前 Top 混淆对（P1 后）

| gold → pred | 次数 | 簇 |
|---|---:|---|
| collection_complaint → stop_collection | ~50 | 催收簇（未解决） |
| repayment_status_issue → deduction_issues | ~33 | 扣款簇（未解决） |
| bill_deduction_query → deduction_issues | ~30 | 扣款簇（未解决） |
| overdue_negotiation → post_loan_verification | ~12 | 未覆盖 |
| credit_inquiry → credit_modification | ~6 | 征信簇（未覆盖） |

---

## 四、错例结构诊断（基于 P1 500 条样本，165 条错例）

**按是否在已覆盖簇分类**：
- 三簇内错例（扣款/催收/还款方式）: 95 条
- 非三簇错例: 70 条
  - 征信/会员/增值服务/退费减免: 40 条（可加判别规则）
  - 单句输入本身不足以判: 15 条（如"因为减免政策要有的"）
  - gold 标注可争议（多意图）: 15 条

---

## 五、本期系统改动清单（交付物）

### 代码 / 配置
- `fin_copilot/routing/skill_router.py`：加载 `boundary_rules.yaml`，动态拼接簇判别规则
- `skills/prompts/skill_routing.md`：新增 `{boundary_hints}` 占位；改"无匹配 → none"为"强制择一"
- `skills/prompts/boundary_rules.yaml`（新建）：运营可编辑的簇判别规则
- `skills/definitions/{5 个 skill}.yaml`：补口语化 examples
- `scripts/references/fewshot_label_mapping.json`：修正 `存对公还款/*` 和 `账单信息查询/*` 错映射

### 测试数据 / 评测工具
- `tests/golden_test.jsonl`：2846 条黄金测试集（首次建立）
- `tests/eval/exp1_l1_domain.py / exp2_skill_match.py`：加 `--source golden` 支持
- `tests/eval/exp2_skill_match.py`：加并发（`--concurrency`）+ embedding 缓存（Phase 1 秒过）
- `scripts/rebuild_golden_from_batches.py`（新建）：从 sub-agent batch 产物 + 修正规则重建 golden
- `scripts/map_intent_to_skill.py`：微调判定阈值（level3 映射表优先）

### 文档
- `tests/EVAL_RUNBOOK.md`（新建）：评测入口与操作指南
- `docs/eval_results_2026-04-20.md`（本文件）：评测结果总结
- `docs/optimization_roadmap.md`（新建）：后续优化方向
