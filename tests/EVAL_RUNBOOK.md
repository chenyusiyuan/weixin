# Evaluation Runbook

金融客服话术推荐系统的离线评测入口与操作指南。

> 所有脚本以项目根目录为工作目录运行：`cd /Users/bytedance/Project/weixin`

---

## 数据来源

| 文件 | 规模 | 用途 |
|------|------|------|
| `tests/golden_test.jsonl` | 2846 条 | 主黄金测试集（query + gold_skill + confidence） |
| `tests/golden_mapped.jsonl` | 3000 条 | Stage B 中间产物（映射路径 + verdict） |
| `tests/golden_raw_intent.jsonl` | 3000 条 | Stage A 中间产物（DeepSeek 提取 polished query） |
| `tests/verification/archive/` | 60 batch | 历史 sub-agent 标注产物（归档保留） |
| `tests/.embed_topk_cache.json` | 缓存 | L1 embedding Top-K 结果缓存（避免重跑 bge-m3） |

数据 pipeline：
```
raw_data.csv (3000 行)
  ↓ scripts/extract_intent_via_deepseek.py        (Stage A，~40 min)
tests/golden_raw_intent.jsonl
  ↓ scripts/map_intent_to_skill.py                (Stage B，~5 min)
tests/golden_mapped.jsonl
  ↓ scripts/rebuild_golden_from_batches.py        (Stage D，合入 batch 人工标注 + 应用修正)
tests/golden_test.jsonl                             (最终黄金集)
```

---

## 评测实验

四层评测，彼此独立，建议按顺序跑。

### Exp 1 — L1 域分类召回

**目标**：测 `DomainClassifier`（rule 或 embed）把客户 query 分到正确域的能力。

**运行**：
```bash
# 全量 embed 分类器（推荐）
python tests/eval/exp1_l1_domain.py --source golden --classifier embed --top-k 3

# rule 分类器（仅作基线对比）
python tests/eval/exp1_l1_domain.py --source golden --classifier rule

# 用旧 98 条数据集
python tests/eval/exp1_l1_domain.py --source test --classifier embed --top-k 3
```

**主要参数**：
- `--source {golden,test}` — `golden` 读 `tests/golden_test.jsonl`（2846），`test` 读 `test.jsonl`（已删，留旧逻辑）
- `--classifier {rule,embed}` — rule 零成本但只 Top-1；embed 需要 ollama bge-m3
- `--top-k N` — Top-K 召回指标（embed 专用）
- `--min-confidence F` — golden 模式过滤低置信样本

**决策阈值**：
- Top-3 ≥ 90% → L1 召回合格
- Top-3 < 85% → 需要补规则权重 / 升级 embedding

**当前基线**（embed, 2846 条）：Top-1 = 72.17%, Top-3 = 91.71% ✅

---

### Exp 2 — Skill Router 精排

**目标**：测 `SkillRouter`（LLM）在 L1 召回的候选里选对 Top-1 skill 的能力。

**运行**：
```bash
# 全量 P1（当前版本）
python -u tests/eval/exp2_skill_match.py --source golden --classifier embed \
  --multi-domain-k 3 --concurrency 10 --json /tmp/exp2.json > /tmp/exp2.log 2>&1 &

# 小样本验证（30 条 smoke test）
python tests/eval/exp2_skill_match.py --source golden --classifier embed \
  --multi-domain-k 3 --limit 30 --concurrency 5
```

**主要参数**：
- `--source {golden,test}` — 同 Exp 1
- `--multi-domain-k N` — L1 Top-K 候选域（默认 1，推荐 3 以利用多域召回）
- `--concurrency N` — LLM 并发（默认 10，DeepSeek 正常承受）
- `--limit N` — 截断跑前 N 条（smoke test 用）
- `--json PATH` — 输出完整 per-record 结果 JSON（后续分析用）
- `--fewshot` — 启用 few-shot 检索（需要 `scripts/references/fewshot_corpus.json`）

**耗时**：
- 全量 2846 条 + `concurrency=10` ≈ 30 分钟（Phase 1 缓存命中 <5s，Phase 2 为 LLM 串行瓶颈）
- 首次跑 Phase 1 要加 ~5 分钟填 embed cache

**决策阈值**：
- Top-3 \| domain-covered ≥ 85% → Router 召回合格
- Top-1 \| domain-covered < 70% → 精排需优化（边界/prompt/examples）

**当前 P1 基线**（2846 条 embed + multi-domain-k=3）：
- Top-1 = 67-69%, Top-3 = 83-84%
- Top-1 \| DC = 73-75%, Top-3 \| DC = 91-92%

**幻觉监控**：跑完 `grep -c "unknown skill_id" /tmp/exp2.log`。正常 <0.5%（<15 条/2846）。若 >2% 说明 prompt 里混入了候选外 skill_id。

---

### Exp 3 — 链路分布 + 性能 + 合规

**目标**：跑完整 orchestrator 流程，测路由分布、延迟、合规通过率。

**运行**：
```bash
python tests/eval/exp3_chain_distribution.py
```

**主要指标**：
- Route A/B/C 占比（规则快捷 / LLM 主链 / 长尾）
- P50 / P95 延迟
- Tool 调用次数分布
- 合规通过率（`comp.passed`）
- 按一级分类分桶的延迟/合规

**期望**：Chain A ≥ 10%（规则短路生效）；P95 < 3s；合规 ≥ 95%。

> 当前脚本还依赖旧 `test.jsonl`，golden 模式需后续适配。

---

### Exp 4 — 话术质量 LLM-as-judge

**目标**：抽样 20-30 条，让 LLM 裁判打分（合规/信息完整/语气）。

> 尚未落地。前 3 个实验达标后再做。

---

## 常见操作

### 生成/清理 embedding 缓存
```bash
# 删除缓存强制重建
rm -f tests/.embed_topk_cache.json

# 首次跑会自动生成缓存
python tests/eval/exp2_skill_match.py --source golden --classifier embed --multi-domain-k 3 --limit 10
```

### Skill 定义校验
```bash
python scripts/validate_skills.py
```

### 重建 golden 测试集（如 fewshot_label_mapping 有修正）
```bash
python scripts/map_intent_to_skill.py        # Stage B
python scripts/rebuild_golden_from_batches.py  # Stage D + 应用修正
```

---

## 目录约定

```
tests/
├── EVAL_RUNBOOK.md       # 本文件
├── EVAL_PLAN.md          # 评测方法论设计
├── eval/                 # 四层评测脚本
│   ├── exp1_l1_domain.py
│   ├── exp2_skill_match.py
│   └── exp3_chain_distribution.py
├── unit/                 # pytest 单元测试（非评测）
│   ├── test_branch_evaluator.py
│   └── test_skill_schema.py
├── verification/archive/ # 历史 sub-agent 标注 batch 归档
├── golden_test.jsonl     # 最终黄金集
├── golden_mapped.jsonl   # Stage B 产物
├── golden_raw_intent.jsonl  # Stage A 产物
└── .embed_topk_cache.json   # embedding 缓存
```
