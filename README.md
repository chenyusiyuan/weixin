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
| 前后端 Demo 工作台 | `fin_copilot/main.py`、`static/demo/` |
| LLM 模型配置 | `config/llm_profiles.json` |
| golden 多模型批处理 | `run_golden_model_matrix.sh` |
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
├── main.py                         # FastAPI 应用入口、组件装配、/demo 静态页挂载
├── orchestrator.py                 # 三链路主编排器
├── config.py                       # 路径、LLM、embedding、路由参数
├── routers/gateway.py              # /api/chat 网关
├── routers/demo.py                 # /api/demo/* 工作台接口
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

static/demo/
├── index.html                       # 坐席工作台页面，由 FastAPI 直接服务
├── app.js                           # 会话、模型、客户注入、数据后台交互
└── styles.css                       # 工作台样式
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

## 前后端与本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

LLM 模型配置以 `config/llm_profiles.json` 为主。每个 profile 同时配置 `api_url`、`model`、`timeout`，API key 默认从 `.env` 的 `LLM_API_KEY` 读取；如果 profile 自己写了 `api_key`，则使用 profile 内配置。

最小 `.env`：

```env
LLM_API_KEY=your-api-key
```

`LLM_API_URL` / `LLM_MODEL` / `LLM_TIMEOUT` 仍保留为兼容 fallback，但日常切模型应改 `config/llm_profiles.json` 或在请求/评测命令里传 profile id。

启动服务：

```bash
uvicorn fin_copilot.main:app --host 0.0.0.0 --port 8000
```

后端入口：

| 地址 | 用途 |
|---|---|
| `GET /api/health` | 基础健康检查 |
| `POST /api/chat` | 生产式对话网关 |
| `GET /demo` | 本地坐席 Demo 工作台 |
| `GET /demo-assets/*` | Demo 前端静态资源 |
| `GET /api/demo/health?probe=true` | Demo 健康检查，可探测 LLM/Embedding |
| `GET /api/demo/llm-profiles` | 返回 `config/llm_profiles.json` 中可选模型 |
| `POST /api/demo/chat/stream` | Demo 流式对话，返回 NDJSON 事件 |
| `GET/POST/PUT/DELETE /api/demo/data/{resource}` | mock 数据后台 |
| `GET /api/demo/tools`、`/skills`、`/rules` | 查看工具、skill、规则配置 |

生产式调用示例：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "s1",
    "user_text": "怎么对公还款",
    "llm_profile_id": "deepseek-v4-flash"
  }'
```

前端 Demo 不需要单独构建。启动 FastAPI 后浏览器打开：

```text
http://localhost:8000/demo
```

Demo 工作台能力：

- 对话页：新建会话、选择模型、发送客户原话、查看 route / skill / tools / trace。
- 模型选择：来自 `/api/demo/llm-profiles`；会话开始后模型会固定，避免同一通电话中途切模型。
- 客户注入：可一键注入 `C100` / `C101` / `C102`，用于跳过真实核身、直接测试业务链路。
- 数据后台：编辑 `customers`、账单、会员、额度、退款、停催等 mock 数据，并可重置为默认数据。

CLI 手工演示：

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
python3 tests/eval/merged_multi_turn_skill_recall.py \
  --route-mode router \
  --model deepseek-v4-flash \
  --llm-timeout 120 \
  --concurrency 8
```

快速 smoke：

```bash
python3 tests/eval/merged_multi_turn_skill_recall.py --route-mode skill-cos --limit 20
python3 tests/eval/merged_multi_turn_skill_recall.py \
  --route-mode router \
  --model qwen3.6-flash \
  --llm-timeout 120 \
  --limit 20
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

## Golden 模型批处理

当前多轮 golden 批处理优先使用根目录脚本：

```bash
# 只打印每个模型的一行完整命令，不发起模型请求
bash run_golden_model_matrix.sh

# 跑单个模型
LIMIT=20 bash run_golden_model_matrix.sh run qwen3.6-flash

# 顺序跑 config/llm_profiles.json 里的全部模型
bash run_golden_model_matrix.sh run-all
```

这个脚本中的每一行都显式传入：

```text
--model <config 中的 profile id 或 model 名>
--llm-timeout <本次批处理 timeout>
--concurrency <适合该模型批跑的并发>
--no-llm-audit-one-to-many
```

输出目录默认是：

```text
tests/reports/golden_model_matrix_<timestamp>/<model>/
```

模型选择规则：

- `--model` 会在 `config/llm_profiles.json` 里按 profile id 优先匹配，其次按 `model` 字段匹配。
- 命中后使用同一个 profile 中的 `api_url`、`api_key`、`model`。
- `--llm-timeout` 只覆盖本次 batch 的 timeout，不回写配置文件。
- 未知模型会直接失败，并打印当前 config 中所有可用 profile。
- route cache key 已包含 profile id、model、api_url、timeout，避免不同模型复用同一份预测缓存。

DeepSeek 专用的历史 profile 脚本仍保留：

```bash
bash scripts/run_multiturn_model_profiles.sh
bash scripts/run_multiturn_model_profiles.sh run flash_full_fast
bash scripts/run_multiturn_model_profiles.sh run pro_safe
```

如果要跑旧单 query 的完整三阶段 wrapper，也可以传同样的模型参数：

```bash
MODEL=deepseek-v4-flash LLM_TIMEOUT=120 bash scripts/run_golden_full_eval.sh

# 先看 Exp2/Exp3 实际命令，不消耗模型调用
DRY_RUN=1 MODEL=deepseek-v4-flash LLM_TIMEOUT=120 bash scripts/run_golden_full_eval.sh
```

## 旧单 query 评测

旧评测入口仍保留，用于看单 query 的 L1/L2/L3 能力：

```bash
MODEL=deepseek-v4-flash LLM_TIMEOUT=120 bash scripts/run_golden_full_eval.sh
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
bash -n run_golden_model_matrix.sh scripts/run_multiturn_model_profiles.sh
bash -n scripts/run_golden_full_eval.sh
```

## 接手建议

1. 先看 `docs/当前评测链路与归档索引.md`，确认当前数据和报告位置。
2. 看 `scripts/references/merged_intent_skill_mapping.json`，理解 golden 小结如何映射到 skill。
3. 用 `tests/EVAL_RUNBOOK.md` 选择多轮电话评测或旧单 query 评测。
4. 修改 skill 前先跑 `scripts/validate_skills.py`。
5. 历史报告只在需要追溯时看 `archive/20260519_eval_chain_cleanup/`，日常不要从归档目录作为当前口径继续开发。
