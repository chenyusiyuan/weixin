# 金融客服坐席话术推荐系统

这是一个面向人工客服坐席的金融客服 Copilot。系统不直接替代客服，而是在客户来电/在线咨询过程中识别业务场景、匹配 SOP/Skill、查询必要工具数据，并生成合规话术建议。

当前项目已经整理成 Skill-based 链路：SOP 被沉淀为结构化 Skill，运行时通过规则短路、混合召回、LLM 路由、工具执行和合规生成完成话术推荐。

## 先看哪里

| 目的 | 文件 |
|---|---|
| 当前评测链路、数据、报告、归档索引 | `docs/当前评测链路与归档索引.md` |
| 离线评测怎么跑 | `tests/EVAL_RUNBOOK.md` |
| 当前多轮小结到 skill 映射 | `scripts/references/merged_intent_skill_mapping.json` |
| 小结类别与 SOP/skill 错配审计 | `docs/小结标注_sop映射错配审计.md` |
| Skill-based 方案原始说明 | `docs/skill-based方案.md` |
| 当前项目说明长文档 | `docs/项目说明文档.md` |
| 历史文档、旧报告、中间产物 | `archive/20260519_eval_chain_cleanup/` |

## 主链路

```text
客户输入
  -> Gateway /api/chat
  -> Orchestrator
  -> L0 预处理、上下文读取、短追问/问候/核身判断
  -> Chain A 规则短路?
       是: RuleEngine -> Skill -> ToolExecutor -> 模板/生成 -> 合规检查
       否: Hybrid Recall -> SkillRouter -> Skill -> 工具/审计/生成 -> 合规检查
  -> 无有效 Skill 时进入 Chain C 长尾兜底
  -> 写回会话上下文
  -> 返回坐席话术建议
```

三条链路的定位：

| 链路 | 入口 | 作用 |
|---|---|---|
| Chain A | `rules/rule_engine.json` | 高频确定性场景，规则直接命中 skill，降低 LLM 成本和误判 |
| Chain B | `fin_copilot/routing/*` | 主链路，先召回候选 skill，再由 LLM Router 精排 |
| Chain C | `fin_copilot/agents/longtail_reasoner.py` | 无 SOP 覆盖或低置信时安全兜底，不强行装作标准业务 |

默认主链路是 Hybrid Recall：

```text
EmbeddingDomain TopK + SkillCos TopM + keyword/prior score
  -> candidate cap
  -> LLM SkillRouter
```

## 运行时代码结构

```text
fin_copilot/
├── main.py                         # FastAPI 应用入口与组件装配
├── orchestrator.py                 # 三链路主编排器
├── config.py                       # 路径、LLM、embedding、路由参数
├── routers/gateway.py              # /api/chat 网关
├── context/                        # 滑动窗口、滚动摘要、结构化状态
├── routing/                        # 规则、域分类、embedding 域分类、skill router
├── skills/loader.py                # Skill YAML 加载
├── agents/                         # 合规生成、置信审计、长尾推理
├── compliance/                     # 后置规则合规检查
├── knowledge/value_added.py         # 活动/增值服务结构化知识检索
├── llm/client.py                   # OpenAI-compatible LLM client
└── models/                         # Conversation / Skill / Response / Tool IO 模型
```

```text
skills/
├── registry.json                   # 54 个 skill，11 个域
├── definitions/*.yaml              # 每个 skill 一个定义文件
├── prompts/skill_routing.md         # Router prompt
├── prompts/compliant_gen.md         # 话术生成 prompt
└── prompts/boundary_rules.yaml      # 高频混淆边界规则

rules/rule_engine.json              # Chain A 规则，当前 9 条

tools/
├── registry.py                      # 已注册 9 个 mock 业务工具
├── executor.py                      # 工具并行执行与缓存
└── get_*.py                         # 账单、额度、会员、通话、短信、退款、停催等查询
```

## Skill 与 SOP

当前系统以 skill 为业务执行粒度：

1. `skills/registry.json` 定义 skill 所属域和索引。
2. `skills/definitions/*.yaml` 定义触发词、示例、排除词、工具、模板、分支和合规要求。
3. `sop/` 保存原始 SOP/知识资产。
4. 活动/增值服务类的产品知识被结构化到 `sop/structured/`，由 `fin_copilot/knowledge/value_added.py` 检索后注入生成链路。

新增或调整 skill 时，通常要同步检查：

```bash
python3 scripts/validate_skills.py
python3 -m pytest tests/unit/test_skill_schema.py
```

## 核身与工具

核身由 `Orchestrator` 统一处理，不散落在单个 skill 或工具中。

基本原则：

- 查询账户、账单、还款结果、退款记录、额度、短信、通话等个人数据前需要核身。
- 产品通用咨询、问候、结束语等低风险问题不触发核身。
- 核身流程优先处理姓名、手机号、身份证后四位，避免被普通业务路由打断。

已注册工具主要包括：

| 工具 | 作用 |
|---|---|
| `get_customer_profile` | 客户画像 |
| `get_bill_and_repayment_plan` | 账单与还款计划 |
| `get_loan_service_info` | 贷款服务信息 |
| `get_membership_service_info` | 会员服务信息 |
| `get_quota_service_info` | 额度服务信息 |
| `get_call_history` | 通话记录 |
| `get_sms_history` | 短信记录 |
| `get_stop_collection_history` | 停催记录 |
| `get_refund_history` | 退款/退费记录 |

## API 与本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

配置 `.env`：

```env
LLM_API_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=deepseek-chat
```

启动服务：

```bash
uvicorn fin_copilot.main:app --host 0.0.0.0 --port 8000
```

调用接口：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "s1", "user_text": "怎么对公还款"}'
```

CLI 演示：

```bash
python3 -m fin_copilot.cli_demo
```

## 当前评测数据

| 文件 | 规模 | 用途 |
|---|---:|---|
| `golden_test.jsonl` | 295 通 | 当前真实电话多轮 golden，call 级 `gold_intents + queries` |
| `raw_test.jsonl` | 2846 条 | 旧单 query golden，字段为 `query/gold_skill/confidence` |
| `原始300条数据.jsonl` | 297 通 | 多轮电话原始来源，原 `merged.jsonl` 改名后文件 |
| `3000条raw data.jsonl` | 2846 条 | 旧单 query 数据快照，当前与 `raw_test.jsonl` 内容一致 |
| `标注维度.xlsx` | - | 小结类别标注维度 |
| `scripts/references/merged_intent_skill_mapping.json` | 27 类 | 小结类别到一个或多个 skill 的映射 |

当前 `golden_test.jsonl` 只补了原始空 gold 的 2 通电话，其余标注保持原始 golden 口径。疑似漏标样本只放在人工复核文档里，不直接写回评测集。

## 多轮电话评测

主评测入口：

```bash
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode router --concurrency 8
```

快速 smoke：

```bash
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode skill-cos --limit 20
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode router --limit 20
```

计分逻辑：

1. 每通电话有 `K = len(gold_intents)` 个真实业务意图。
2. 对该电话内每条客户 query 路由出一个 skill。
3. 按一通电话内 skill 出现次数聚合，取 TopK。
4. 如果 K 个 gold intent 命中 N 个，则该通电话得分 `N / K`。
5. 总准确率为所有电话得分求和后除以样本数。

当前复用的历史预测结果：

```text
tests/reports/merged_multi_turn_after_corporate_repay_tuning_20260427/query_predictions.jsonl
```

当前映射重算结果：

```text
tests/reports/merged_mapping_recalc_from_previous_20260519/summary_after_empty_only_patch.json
```

## 旧单 query 评测

旧评测入口仍保留，用于看单 query 的 L1/L2/L3 能力：

```bash
bash scripts/run_golden_full_eval.sh
```

底层实验：

| 实验 | 脚本 | 目标 |
|---|---|---|
| Exp1 | `tests/eval/exp1_l1_domain.py` | L1 域分类 Top1/TopK |
| Exp2 | `tests/eval/exp2_skill_match.py` | Skill Router Top1/Top3 |
| Exp3 | `tests/eval/exp3_chain_distribution.py` | 完整链路分布、延迟、合规 |

## 数据构建链路

多轮电话数据构建：

```text
原始300条数据.jsonl
  -> scripts/prepare_merged_turn_labeling_chunks.py
  -> scripts/merge_merged_turn_labels.py
  -> scripts/export_raw_scorable_queries.py
  -> scripts/apply_raw_query_split_decisions.py
  -> scripts/export_merged_raw_eval_dataset.py
  -> golden_test.jsonl
```

旧单 query 数据构建：

```text
raw_data.csv / 3000条raw data.jsonl
  -> scripts/extract_intent_via_deepseek.py
  -> scripts/map_intent_to_skill.py
  -> scripts/rebuild_golden_from_batches.py
  -> raw_test.jsonl
```

多轮打标、query 拆分、旧 batch 标注等中间产物已经归档：

```text
archive/20260519_eval_chain_cleanup/data_intermediate/
```

## 映射表与人工复核

当前正式映射表：

```text
scripts/references/merged_intent_skill_mapping.json
```

映射原则是：

```text
一个 golden 小结类别 -> 一个或多个可接受 skill_id
```

也就是说允许一对多，但不把多个小结合成一个 gold 类别。这个映射用于解决标注小结粒度与 SOP/skill 粒度不一致的问题，例如“账单信息查询”“存对公还款”“营销活动/新活动咨询”等粗标签。

相关复核文件：

| 文件 | 用途 |
|---|---|
| `docs/小结标注_sop映射错配审计.md` | 小结类别与 SOP/skill 的错配审计 |
| `docs/golden小结类别_sop特殊标注全量样本.json` | 特殊类别的全量样本证据 |
| `docs/golden小结类别_sop逐条复核_20260519.md` | 当前逐条复核与计分 |
| `docs/golden小结类别_sop高优先级疑点_20260519.md` | 人工确认清单，不自动写回 golden |

## 报告与归档

`tests/reports/` 当前只保留仍会使用的两类报告：

```text
tests/reports/merged_multi_turn_after_corporate_repay_tuning_20260427/
tests/reports/merged_mapping_recalc_from_previous_20260519/
```

历史文档、旧报告、中间产物、缓存和日志已经归档到：

```text
archive/20260519_eval_chain_cleanup/
```

归档明细：

```text
archive/20260519_eval_chain_cleanup/manifest.json
```

## 常用校验

```bash
python3 scripts/validate_skills.py
python3 -m pytest tests/unit/test_skill_schema.py tests/unit/test_value_added_knowledge.py
python3 -m json.tool scripts/references/merged_intent_skill_mapping.json >/dev/null
python3 tests/eval/merged_multi_turn_skill_recall.py --help
bash -n scripts/run_golden_full_eval.sh
```

## 接手建议

1. 先看 `docs/当前评测链路与归档索引.md`，确认当前数据和报告位置。
2. 看 `scripts/references/merged_intent_skill_mapping.json`，理解 golden 小结如何映射到 skill。
3. 用 `tests/EVAL_RUNBOOK.md` 选择多轮电话评测或旧单 query 评测。
4. 修改 skill 前先跑 `scripts/validate_skills.py`。
5. 历史报告只在需要追溯时看 `archive/20260519_eval_chain_cleanup/`，日常不要从归档目录作为当前口径继续开发。
