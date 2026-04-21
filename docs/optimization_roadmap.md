# 优化路线图

**更新日期**：2026-04-20
**当前指标**：Skill Top-1 = 68.80%（P0）/ 67-69%（P1，500 样本），Top-3 = 83-84%

---

## 判断框架

| 指标区间 | 状态 | 动作 |
|---|---|---|
| Top-3 \| DC ≥ 90% | 召回合格 | 不动 L1 / 召回层 |
| Top-1 \| DC < 75% | 精排不足 | 聚焦 Router 边界 / prompt |
| 单句输入天花板 ~75-80% | 输入不足 | 升级到前 2-3 句上下文 |

---

## 已完成

| 阶段 | 做法 | 收益 |
|---|---|---|
| 基线 | 98 → 2846 条黄金集 | 样本从 98 扩到 2846 |
| P0-2 | 补 Top-5 "→ none" skill 的 examples | **+1.2pp Top-1** |
| P0-3 | Router prompt 强制择一 | 减少 none 输出 |
| P1-1 | 动态簇判别规则（3 簇） | 还款方式簇错例 -32% |

---

## 待办（按 ROI 排序）

### P1-2 — 补剩余判别簇
**ROI**：中 · 工作量 0.5 天 · 预期 +1-2pp Top-1

为 `boundary_rules.yaml` 补充 3 个簇：
- **征信簇**（credit_inquiry / credit_modification / bill_date_credit_impact）：查询 vs 修改 vs 征信影响咨询
- **会员簇**（member_consultation / member_refund / member_cancel）：咨询 vs 退款 vs 取消
- **账户注销簇**（account_cancellation / cancel_credit_authorization / deactivated_customer_service）：注销账户 vs 注销授信额度

运营可直接编辑 `skills/prompts/boundary_rules.yaml`，无需改代码。

---

### P2 — 输入增强（前 2-3 句 vs 首句）
**ROI**：高 · 工作量 1 天 · 预期 +3-5pp Top-1

**假设**：单句输入对细粒度 skill 判别信息不足。如"因为减免政策要有的"单句无法判断，但加上客户前一句上下文就清晰了。

**落地**：
1. 在 `golden_test.jsonl` 中额外存 `primary_query_context`（前 2 句）
2. 修 `exp2_skill_match.py`，加 `--input-mode {first_sentence, first_2, first_3}` 对比
3. A/B 跑三组，看 Top-1 提升幅度
4. 若 V3（前 2-3 句）明显好于 V1，则**生产 pipeline 也切到前 2-3 句**

---

### P3 — 硬负样本扩充 + few-shot 增强
**ROI**：中 · 工作量 1-2 天 · 预期 +2-3pp Top-1

现状：
- `scripts/references/fewshot_corpus.json` 已经存在 few-shot 样本
- SkillRouter 支持 `FewShotRetriever`，但评测默认没开（`--fewshot` flag）

**落地**：
1. 先测 `--fewshot --fewshot-k 5` 相比无 few-shot 有多大收益
2. 若有效，从 2846 golden 里挑 Top 混淆对的**对照样本**补进 corpus
3. 尤其补 `collection_complaint ↔ stop_collection` 这类 P1 解决不了的

---

### P4 — 让 none 合理化
**ROI**：低 · 工作量 0.5 天 · 预期 +0.5-1pp Top-1

P1 后仍有 ~15 条错例是 `gold → none`，说明少数 query 就是"有点像但不够像"。

**落地**：
- Router prompt 增加"如果 confidence < 0.3，显式返回 none"
- 让 orchestrator 的 Chain C（长尾推理）接手处理这些
- 当前 Top-1 指标按严格匹配计算，这部分让给 Chain C 更合理

---

### P5 — Gold 质量复核
**ROI**：依赖上面 P0-P4 的收益瓶颈 · 工作量 0.5 天

若 P1-P3 都做完还停在 ~75%，说明评测集本身噪声显著。

**抽样方案**：
1. 从错例里随机抽 30 条
2. 人工复核 4 件事：
   - gold 是否唯一合理
   - 模型预测是否也合理
   - 是否应允许多标签（primary + secondary）
   - 是否仅凭首句就无法判

若 ≥25% 错例被判"多标签合理 / gold 可争议 / 首句不可判" → 评测指标本身需要重构（如 Top-1 允许多 gold）。

---

## 不推荐做

- ❌ 预路由规则快捷匹配（已尝试，覆盖仅 3%，边缘收益不够）
- ❌ 调 `CONFIDENCE_THRESHOLD`（只影响 Agent B 审核，不影响 Router Top-1）
- ❌ 继续优化 L1（Top-3 已达 91.71%，不是瓶颈）
- ❌ 优化 low-risk / direct_reply 类（合规风险低，投入产出低）

---

## 执行建议

**立即**：P1-2（补剩余判别簇）——工作量最小
**本周**：P2（输入增强 A/B）——收益最高
**下周**：P3（few-shot 增强）——和 P1-P2 正交
**阻塞后**：P5（gold 复核）——根据 P2/P3 结果决定

---

## 中长期方向

系统层面的重构（不在当前迭代）：
- **两阶段路由**：L1 → coarse intent cluster → pairwise rerank 同簇 skill
- **拒识信号**：主动识别"首句不可判"，触发补问而非错判
- **多 gold 评测**：允许 secondary_skills 标注，符合真实业务多意图的客观现实
