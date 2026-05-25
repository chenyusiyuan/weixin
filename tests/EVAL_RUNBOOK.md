# Evaluation Runbook

金融客服话术推荐系统的离线评测入口。

工作目录：

```bash
cd /Users/bytedance/Project/weixin
```

## 当前测试集

| 文件 | 规模 | 用途 |
|---|---:|---|
| `golden_test.jsonl` | 295 通 | 当前真实电话多轮评测集，call 级 `gold_intents + queries` |
| `raw_test.jsonl` | 2846 条 | 旧单 query golden，字段为 `query/gold_skill/confidence` |
| `原始300条数据.jsonl` | 297 通原始电话 | 多轮评测集来源，原 `merged.jsonl` 改名后文件 |
| `3000条raw data.jsonl` | 2846 条 | 旧单 query 数据快照，当前与 `raw_test.jsonl` 内容一致 |
| `标注维度.xlsx` | - | 小结类别标注维度来源 |
| `scripts/references/merged_intent_skill_mapping.json` | 27 类 | 小结类别到一个或多个 skill 的映射表 |

历史中间产物已经归档到：

```text
archive/20260519_eval_chain_cleanup/
```

## 多轮真实电话评测

这是当前更贴近真实电话链路的主评测。

```bash
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode router --concurrency 8
```

快速 smoke：

```bash
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode skill-cos --limit 20
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode router --limit 20
```

计分逻辑：

- 每通电话有 `K = len(gold_intents)` 个小结标注。
- 对该电话的每条客户 query 路由出一个 skill。
- 聚合一通电话内出现次数最多的 TopK skill。
- `gold_intents` 通过 `scripts/references/merged_intent_skill_mapping.json` 映射到一个或多个可接受 skill。
- 如果 gold 的 K 个意图中命中 N 个，则该通电话得分为 `N / K`。
- 总准确率为所有电话得分求和后除以样本数。
- 默认直接按映射表计分，不再跑 LLM audit；如需额外复核一对多映射命中，可显式加 `--llm-audit-one-to-many`。

当前映射重算口径：

```text
tests/reports/merged_mapping_recalc_from_previous_20260519/summary_after_empty_only_patch.json
```

当前复用的历史预测结果：

```text
tests/reports/merged_multi_turn_after_corporate_repay_tuning_20260427/query_predictions.jsonl
```

## 旧单 query 评测

旧评测入口仍保留，用于看 L1/L2/L3 的单 query 能力。

```bash
bash scripts/run_golden_full_eval.sh
```

常用环境变量：

```bash
CONCURRENCY=4 bash scripts/run_golden_full_eval.sh
RUN_EXP3=0 bash scripts/run_golden_full_eval.sh
SKILL_COS_TOP_M=12 MAX_CANDIDATES=20 bash scripts/run_golden_full_eval.sh
```

底层脚本：

| 实验 | 脚本 | 目标 |
|---|---|---|
| Exp1 | `tests/eval/exp1_l1_domain.py` | L1 域分类 Top1/TopK |
| Exp2 | `tests/eval/exp2_skill_match.py` | Skill Router Top1/Top3 |
| Exp3 | `tests/eval/exp3_chain_distribution.py` | 完整链路分布、延迟、合规 |

## 数据构建入口

多轮数据构建：

```bash
python3 scripts/prepare_merged_turn_labeling_chunks.py
python3 scripts/merge_merged_turn_labels.py
python3 scripts/export_raw_scorable_queries.py
python3 scripts/apply_raw_query_split_decisions.py
python3 scripts/export_merged_raw_eval_dataset.py
```

旧单 query 数据构建：

```bash
python3 scripts/export_golden_test.py
python3 scripts/rebuild_golden_from_batches.py
```

注意：多轮打标和 query 拆分的旧中间产物已归档。如果要完全复现旧构建过程，先看：

```text
archive/20260519_eval_chain_cleanup/data_intermediate/merged_turn_filter/
```

## 映射与错配文档

| 文件 | 用途 |
|---|---|
| `scripts/references/merged_intent_skill_mapping.json` | 正式小结到 skill 映射表 |
| `docs/小结标注_sop映射错配审计.md` | 小结类别与 SOP/skill 的错配审计 |
| `docs/golden小结类别_sop特殊标注全量样本.json` | 特殊标注类别的全量样本 |
| `docs/golden小结类别_sop逐条复核_20260519.md` | 当前逐条复核结果 |
| `docs/golden小结类别_sop高优先级疑点_20260519.md` | 人工确认清单，不直接写回 golden |

## 校验

```bash
python3 scripts/validate_skills.py
python3 -m pytest tests/unit/test_skill_schema.py tests/unit/test_value_added_knowledge.py
python3 -m json.tool scripts/references/merged_intent_skill_mapping.json >/dev/null
```

完整文件结构和归档说明见：

```text
docs/当前评测链路与归档索引.md
```
