# 金融客服坐席话术推荐系统 — 技术方案

## 一、原有 Demo 方案的不足

### 1.1 RAG 系统不适配坐席辅助场景

**核心问题：SOP 被拍平为文本 chunk，丢失了决策结构。**

当前方案将 10 个业务域的 SOP 文档（60 份 docx/xlsx）经过 extract → clean → chunk → embed 四步流水线，切成 874 个文本 chunk 存入 Milvus 向量库。每个 chunk 结构为 `{topic, step, user_query, response, notes}`，本质上是一个 QA 对。

这种表示方式导致三个具体问题：

1. **递进式话术无法区分（维新方上次强调）**：同一个场景（如逾期协商），首次、二次、三次沟通的话术模板完全不同，但 RAG 检索只看 query 相似度，无法感知"这是第几轮沟通"，经常返回错误轮次的模板。纯rag无法实现递进式话术

2. **SOP 分支逻辑丢失**：以"无额度查询"为例，真实 SOP 的决策路径是：判断风险等级（低/中/高）→ 决定身份验证级别 → 是否可查额度信息 → 是否可说明原因 → 是否提交工单 → 是否转人工。每个分支对应不同的允许话术集。但切 chunk 后这些分支条件被扁平化，检索时无法还原。

3. **query 与 SOP 的表达鸿沟**：用户说"我那个钱怎么还没退回来"，SOP 写的是"费用退回查询-退款进度确认"。当前 Reranker（`reranker.py`）使用纯 bigram/字符重叠计算相似度（权重 0.65/0.35），无语义理解能力，无法弥合口语与标准话术之间的表达差异。注入了 `llm_client` 但从未使用，`strategy_tags` 参数被显式丢弃（`_ = strategy_tags`）。

### 1.2 整体流程过重，时延不可接受

当前方案的典型 `tool_rag` 请求链路包含 **3 次串行本地 7B 模型推理**：

```
IntentClassifier（LLM调用#1, 1.5-3s）
  → Router（规则, <1ms）
  → ActionExecutor + RagRetriever（并行, ~200ms）
  → Reranker（纯计算, <10ms）
  → ResponseGenerator（LLM调用#2, 1.5-3s, 结构化场景可跳过）
  → ComplianceGate（LLM调用#3, 1-2s, 始终执行）
```

| 链路类型 | LLM 调用次数 | 端到端预估时延 |
|---------|-------------|--------------|
| tool_rag（最常见） | 3 次串行 | 4-8s |
| tool_only + 结构化响应 | 2 次串行 | 2.5-5s |
| direct_reply（最简单） | 1 次 | 1.5-3s |

坐席辅助场景要求 P95 < 1.5-2s，当前链路远超这个上限。其中最大的"冤枉时延"来自合规质检：对于结构化模板生成的应答（已经是预审过的标准话术），仍然走一次 LLM 合规审查。此外 `AnswerabilityChecker` 阈值设为 0.0（实质禁用），`QueryRewriter` 默认关闭（`QUERY_REWRITE_ENABLED=False`），两个组件形同虚设却仍占据链路位置。

### 1.3 错误级联无法自修正 并且链路会不断放大错误

当前系统是严格的串行管道，每一步的输出是下一步的唯一输入：

```
场景匹配 → RAG 模板检索 → Rerank 排序 → LLM 模板填充 → 合规检查
```

任何一个环节出错，后续环节都只能在错误结果上继续工作：

- **场景匹配错误**：IntentClassifier 将"还款失败"错分为"还款咨询"，后续 Router 给出错误的 route_mode，RAG 检索到不相关的模板，ResponseGenerator 在错误模板上填充数据——最终输出的话术完全偏离用户真实需求。
- **RAG 模板失效**：即使场景匹配正确，如果 Reranker（纯字符级）排序失败，把错误模板排在 Top-1，LLM 生成阶段只是在该模板上填充 tool 数据，无法判断"这个模板本身就不对"。
- **LLM 无修正能力**：当前 ResponseGenerator 的 LLM prompt 指令是"根据以下模板和数据生成回复"，模型被明确限制为"模板填充器"角色，不具备"判断模板是否适合当前 query"的能力。

### 1.4 效果强依赖 RAG 质量

当前系统中，RAG 是话术推荐的唯一知识来源。对于 `tool_rag` 和 `rag_only` 路径（合计 23 个场景），如果 RAG 检索失败或返回低质量结果，系统只有两个选择：使用质量差的模板生成不准确的话术，或触发安全兜底话术（过于笼统无法使用）。不存在"RAG 失效时仍能基于场景知识给出合理推荐"的降级路径。

---

## 二、新方案：Skill-based 坐席话术推荐系统

### 2.1 核心思路

**将 RAG 的"运行时检索"转变为 LLM prompt 中的"编译时内嵌"。**

不再是 `query → 向量检索模板 → LLM 填充`，而是将场景定义与 SOP 话术模板合并为 **Skill**，直接嵌入 LLM 上下文，由 LLM 一次完成"场景匹配 + 工具选择 + 话术选择"。

| | 原有 Demo | 新方案 |
|---|---|---|
| 知识载体 | 874 个向量 chunk（Milvus） | Skill JSON（场景+模板+工具一体化） |
| 场景匹配 | ScenarioRecaller + LLM 选择 | LLM 直接从 Skill 列表中匹配 |
| 模板获取 | RAG 检索 + Rerank | Skill 内已包含所有模板（含递进话术） |
| 工具决策 | 场景定义声明 + 并行执行 | Skill 声明 + 并行执行 |
| 话术生成 | LLM 模板填充 | 合规生成 prompt 一次完成 |
| 合规检查 | 规则 + LLM 审核（串行） | 规则审查（并行）+ prompt 约束 |
| 长尾问题 | 强行匹配最近 skill | LLM 自主推理 + 标注"无 SOP 覆盖" |

### 2.2 方案优势

**1. 彻底解决递进式话术问题**

Skill 内按轮次/状态组织多套模板，LLM 看到完整对话上下文后自动选择正确变体。RAG 做不到这个，因为它不感知对话状态。

```json
{
  "skill_id": "overdue_negotiation",
  "templates": {
    "first_contact": "您好，关于您的逾期情况...",
    "second_contact": "您上次提到的还款方案...",
    "third_contact": "我们之前沟通过两次..."
  }
}
```

**2. 链路大幅简化，时延显著降低**

从 3 次串行 LLM 调用缩减为 1 次 Skill 路由 + 1 次合规生成。移除 RAG 检索、Reranker、AnswerabilityChecker 等中间环节。

| 链路类型 | 原有 Demo | 新方案 |
|---------|----------|--------|
| 高频场景（规则短路） | 2.5-5s | **< 200ms** |
| 正常场景 | 4-8s | **1-3s** |
| 异常场景（审查失败短路） | 4-8s | **< 1.6s** |

**3. 错误可自修正**

LLM 同时看到用户 query、对话上下文和 Skill 定义，匹配错误时可以自主选择更合适的 Skill 或标记不确定——而不是在错误模板上盲目填充数据。

**4. 消除对 RAG 的强依赖**

Skill 定义直接在 prompt 中，不存在"检索失败"的概念。向量库从"主链路关键依赖"降级为可选的辅助信息源。

**5. 长尾问题诚实处理**

对于不在 Skill 覆盖范围内的问题，不再强行匹配错误模板，与其硬是匹配错误模版，不如使 LLM 基于自身理解 + 真实业务 tool 调用结果生成回答，并明确标注"该回答无 SOP 覆盖，请坐席核实后使用"。

**6. 内置自演进能力**

通过坐席反馈（采纳/修改/拒绝）自动驱动三级演化：长尾问题 → 沉淀为新 Skill → 高频 Skill 硬编码为规则。系统越用越好，不依赖人工持续维护。

---

## 三、系统架构与核心流程

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    坐席推荐面板                            │
│  [推荐话术1] [推荐话术2] [一键发送] [建议操作]             │
│  [匹配场景] [证据来源] [合规状态] [风险提示]               │
│  ⚠️ 无SOP覆盖标记（长尾链路时显示）                       │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              三条链路 · 按场景自动路由                      │
│                                                          │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐     │
│  │ 链路 A   │   │   链路 B     │   │   链路 C     │     │
│  │ 规则短路 │   │ Skill 路由   │   │  长尾自主    │     │
│  │ < 200ms  │   │  1-3s        │   │  1.5-3s      │     │
│  └──────────┘   └──────────────┘   └──────────────┘     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐     │
│  │              反馈闭环 · 自演进引擎               │     │
│  │  长尾 → Skill 沉淀 → 高频硬编码规则              │     │
│  └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Skill 组织方式与数据结构

参考 `~/skill_cloud/appgen` 的 skill 工程化组织模式，将 Skill 定义、执行 prompt、合规规范、校验脚本分层存放，实现"改配置不改代码"的可运营目标。

#### 3.2.1 目录结构

```
fin_copilot/
├── skills/
│   ├── SKILL.md                   ← 主 Skill Routing 的 system prompt 模板
│   ├── registry.json              ← 全量 skill 索引（skill_id → 元数据摘要）
│   │
│   ├── definitions/               ← 每个 skill 的完整定义（一个文件一个 skill）
│   │   ├── overdue_negotiation.yaml
│   │   ├── outstanding_bill_query.yaml
│   │   ├── repayment_failure_bank_card.yaml
│   │   ├── member_cancel.yaml
│   │   └── ...（当前 54 个）
│   │
│   ├── prompts/                   ← 各链路的执行 prompt 模板
│   │   ├── skill_routing.md       ← 链路B: LLM Skill Routing prompt
│   │   ├── compliant_gen.md       ← 链路B: Agent A 合规生成 prompt
│   │   ├── longtail_reasoning.md  ← 链路C: 长尾自主推理 prompt
│   │   └── slot_extraction.md     ← 可选: 槽位提取追加 prompt 片段
│   │
│   ├── references/                ← 规范文档（合规规则、业务规范等）
│   │   ├── compliance/
│   │   │   ├── forbidden_words.json       ← 违禁词列表（可热更新）
│   │   │   ├── key_rules.json             ← 关键业务规则
│   │   │   └── longtail_constraints.json  ← 长尾链路加严约束
│   │   └── business/
│   │       ├── verification_rules.md      ← 身份验证规则
│   │       └── escalation_rules.md        ← 转人工触发规则
│   │
│   └── scripts/                   ← 校验与审查脚本
│       ├── confidence_audit.py    ← Agent B 置信度审查逻辑
│       ├── compliance_check.py    ← 后置规则合规检查
│       └── feedback_collector.py  ← 反馈采集与统计
│
├── agents/                        ← Agent 角色定义
│   ├── skill_router.md            ← Skill Routing Agent 的角色说明
│   ├── compliant_generator.md     ← Agent A 合规生成的角色说明
│   └── longtail_reasoner.md       ← 长尾推理 Agent 的角色说明
│
├── rules/                         ← 链路A 硬编码规则（自动沉淀）
│   ├── rule_engine.json           ← 规则定义（关键词→skill_id→模板）
│   └── rule_versions.json         ← 规则版本与过期管理
│
└── state/                         ← 运行时状态
    └── .copilot_state.json        ← 会话状态追踪
```

**设计要点（借鉴 appgen 模式）：**

- **定义与执行分离**：skill 定义（`definitions/`）只描述"是什么"，prompt 模板（`prompts/`）描述"怎么用"，两者独立维护
- **规范文档独立**：合规规则、业务规范放在 `references/` 中，可被多个 prompt 引用，修改规范不需要改 skill 定义
- **校验脚本化**：Agent B 的审查逻辑和合规检查抽取为独立脚本，可单独测试和迭代
- **Agent 角色声明**：每个 agent 的角色、工具权限、安全边界在 `agents/` 中显式定义

#### 3.2.2 Skill 定义格式（YAML front-matter + 结构化字段）

每个 skill 使用 YAML 格式定义，借鉴 appgen 的 front-matter 模式：

```yaml
# definitions/overdue_negotiation.yaml
---
skill_id: overdue_negotiation
name: 逾期协商还款
description: >
  客户因逾期问题来电，希望协商还款方案、申请减免或延期。
  包含首次/二次/三次沟通的递进话术，需要查询客户档案、
  账单信息和历史工单。
domain: 逾期问题
intent_hierarchy:
  l1: 催收相关
  l2: 协商还款
  l3: 逾期
route_mode: tool_rag    # 原 demo 中的路由模式，用于兼容迁移
risk_level: high
---

# 触发条件
triggers:
  keywords: ["逾期", "协商", "还不上", "延期", "减免", "分期", "没钱还"]
  examples:
    - "我现在没钱还，能不能商量一下"
    - "逾期了想协商还款方案"
    - "能不能减免一些利息"
    - "我想申请延期还款"
  exclude_keywords: ["还款成功", "已还清"]   # 防止误匹配

# 所需工具
tools:
  required:
    - get_customer_profile
    - get_bill_and_repayment_plan
  optional:
    - query_ticket    # 有历史工单时调用

# 递进话术模板（按沟通轮次组织）
templates:
  first_contact:
    script: >
      您好{customer_name}，我这边查看到您目前有一笔{overdue_amount}元
      的逾期账单，逾期{overdue_days}天。请问您目前的还款困难主要是
      什么原因呢？
    required_slots: [customer_name, overdue_amount, overdue_days]
    next_step: "了解客户困难原因，评估还款能力"

  second_contact:
    script: >
      您之前提到的情况我们已经记录了。目前您的账单金额为
      {overdue_amount}元，我们可以为您提供以下方案...
    required_slots: [overdue_amount]
    next_step: "提供具体还款方案选项"

  third_contact:
    script: >
      我们之前已经沟通过两次了，为了尽快帮您解决，建议...
    required_slots: []
    next_step: "推动客户做出还款决定或升级处理"

# 分支条件（不同业务状态走不同模板变体）
branch_conditions:
  - condition: "overdue_days <= 30"
    variant: "mild_overdue"
    note: "轻度逾期，以提醒和协助为主"
  - condition: "overdue_days > 30 and overdue_days <= 90"
    variant: "moderate_overdue"
    note: "中度逾期，引导制定还款计划"
  - condition: "overdue_days > 90"
    variant: "severe_overdue"
    note: "重度逾期，可能涉及法务提醒，需谨慎措辞"

# 合规规则（该 skill 专属）
compliance:
  forbidden_expressions: ["保证", "承诺减免", "一定可以", "绝对"]
  required_disclaimer: "具体方案以实际审批结果为准"
  must_include_when:
    - condition: "overdue_days > 90"
      text: "如长期未还款，可能会影响您的个人征信记录"

# 转人工条件
escalation:
  - trigger: "客户明确要求投诉"
  - trigger: "客户情绪激动且已沟通两轮以上"
  - trigger: "涉及法律诉讼相关问题"

# 兜底话术
fallback:
  answer: "关于您的逾期问题，我需要进一步了解您的情况，请稍候为您转接专员处理。"
  next_step: "转接逾期处理专员"
```

#### 3.2.3 Skill 索引（registry.json）

全量 skill 的轻量索引，用于 L1 分类器域内筛选和 LLM Skill Routing 的候选列表构建：

```json
{
  "version": "2026-04-09",
  "total_skills": 54,
  "domains": {
    "逾期问题": {
      "skills": [
        {
          "skill_id": "overdue_negotiation",
          "name": "逾期协商还款",
          "risk_level": "high",
          "route_mode": "tool_rag",
          "keywords_preview": ["逾期", "协商", "还不上"]
        },
        {
          "skill_id": "collection_complaint",
          "name": "催收投诉",
          "risk_level": "high",
          "route_mode": "tool_rag",
          "keywords_preview": ["投诉", "催收", "骚扰"]
        }
      ]
    },
    "还款问题": { "skills": ["..."] },
    "会员问题": { "skills": ["..."] }
  }
}
```

**加载策略：** L1 分类器确定域后，从 registry.json 取该域的 skill_id 列表，再从 `definitions/` 中加载完整定义传入 LLM prompt。不需要一次加载全部 54 个 skill。

#### 3.2.4 Prompt 模板文件示例

`prompts/skill_routing.md`（LLM Skill Routing 的 system prompt）：

```markdown
---
name: skill_routing
description: 从候选 skill 列表中匹配最合适的 skill
tools: []
---

你是金融客服坐席辅助系统的场景匹配引擎。

## 任务
根据客户对话内容，从候选场景列表中选择最匹配的场景。

## 候选场景
{candidate_skills}

## 客户对话上下文
{sliding_window}

## 历史摘要
{summary}

## 当前状态
- 当前场景：{current_skill_id}
- 本场景沟通轮次：{turn_in_skill}
- 已收集信息：{collected_slots}
- 风险标签：{risk_flags}

## 输出要求
选择最匹配的场景，如无合适场景请选择 "none"。
输出 JSON：
{
  "skill_id": "场景ID 或 none",
  "template_variant": "模板变体名",
  "confidence": 0.0-1.0,
  "tools_needed": [],
  "extracted_slots": {},
  "reasoning": "一句话选择理由"
}
```

### 3.3 三条链路详细流程

#### 链路 A：规则短路（高频确定性场景，目标 < 200ms）

适用于匹配模式固定、话术确定、无需 LLM 的高频场景（如账单查询、还款日期查询、会员状态查询）。

```
用户输入
  │
  ▼
L0 输入预处理（脱敏/归一化, <10ms）
  │
  ▼
L1 规则匹配引擎（正则/关键词/精确匹配, <5ms）
  │ 命中规则 → 直接定位 skill_id
  ▼
Tool 并行执行（asyncio.gather, <100ms）
  │
  ▼
模板槽位填充（Jinja2 模板引擎, <5ms）
  │
  ▼
规则合规检查（禁用词正则 + 关键规则, <5ms）
  │
  ▼
输出推荐话术
```

**规则短路的进入条件**：该 skill 经过坐席反馈验证，采纳率 >= 90% 且匹配频率进入 Top-N。规则从真实流量数据中自动沉淀，不是人为预设。

#### 链路 B：Skill 路由（标准场景，目标 1-3s）

适用于大部分场景，是系统的主链路。

```
用户输入
  │
  ▼
L0 输入预处理（脱敏/归一化, <10ms）
  │
  ▼
L1 轻量分类器（确定业务域, <50ms）
  │ 10 个 L1 域：会员/额度/还款/贷款/费用/活动/业务/账户/逾期/优享卡
  │ 缩小范围：只将该域内 4-8 个 skill 传入下一步
  ▼
Step 1: LLM Skill Routing（0.5-1.5s）
  │ 输入：用户 query + 对话上下文 + 域内 skill 列表
  │ 输出：skill_id + 选择的模板变体 + 需要的 tools
  │
  ├──────────────────────────────────────┐
  │                                      │
  ▼                                      ▼
Tool 并行执行（<100ms）          Agent B: 置信度审查（<10ms）
  │                               │
  │                          置信度 ≥ θ ?
  │                          ├─ No → 立即返回 fallback（短路）
  │                          └─ Yes ↓
  ▼                                │
Agent A: 合规生成（0.5-1.5s） ◄────┘
  │ 输入：skill 模板 + tool 数据
  │      + 该 skill 的合规红线
  │      + 必须包含的免责声明
  │ 输出：话术 + next_step_hint
  │
  ▼
后置规则合规（禁用词正则, <5ms）
  │
  ▼
输出推荐话术（带合规状态 + 证据来源）
```

#### 链路 C：长尾自主推理 + 轻量 RAG 辅助（无 Skill 覆盖场景，目标 1.5-3s）

适用于 Skill 库中无匹配或置信度过低的问题。引入轻量 RAG 检索作为辅助信息源，为 LLM 自主推理提供 SOP 参考片段，但 RAG 不在主链路上——与 Tool 执行并行，零额外时延。

```
Step 1 LLM Skill Routing 结果：无匹配 / 置信度 < θ
  │
  ├──────────────────────┬─────────────────────┐
  │                      │                     │
  ▼                      ▼                     ▼
轻量 RAG 检索       Tool 执行（如需）      构建长尾 Prompt
(Milvus Top-3,       (<100ms)              (读取上下文层)
 <100ms)                 │                     │
  │                      │                     │
  └──────────┬───────────┘                     │
             │                                 │
             ▼                                 │
  组装完整 prompt ◄────────────────────────────┘
  (query + 上下文 + tool数据 + RAG参考片段)
             │
             ▼
  LLM 自主推理（1-2s）
  │ 指令：参考以下SOP片段但不必拘泥于模板
  │       如信息不足请如实说明
  │
  ▼
生成回答 + 附加元数据
  │ {
  │   "answer": "...",
  │   "matched_skill": null,
  │   "rag_references": ["chunk_id_1", "chunk_id_2"],
  │   "warning": "⚠️ 该回答无SOP覆盖，请坐席核实后使用",
  │   "tools_called": ["get_bill_and_repayment_plan"]
  │ }
  │
  ▼
后置规则合规（加严模式, <5ms）
  │ 额外约束：
  │ - 禁止说"我可以帮你操作"，只能说"建议您..."
  │ - 强制附加"以上信息仅供参考，具体以业务确认为准"
  │
  ▼
输出推荐话术（带 ⚠️ 无SOP标注 + RAG参考来源）
```

**轻量 RAG 的定位：** RAG 在长尾链路中是"参考文献"而非"话术模板"。LLM prompt 中明确区分：

```
## SOP 参考片段（仅供参考，不必照搬）
{rag_top3_chunks}
```

LLM 可以自主判断是否采用、采用多少，不受模板约束。即使 RAG 返回结果不相关，也不会影响生成质量——最差情况等于没有 RAG，回退到纯 LLM 自主推理。

**轻量 RAG vs 原有主链路 RAG 的区别：**

| 维度 | 原有主链路 RAG（已移除） | 长尾辅助 RAG |
|------|----------------------|-------------|
| 检索方式 | Milvus 向量 + fallback 字符匹配 | Milvus 单次向量检索 |
| Reranker | 3D 加权启发式 reranker | 不需要，取 Top-3 直接用 |
| 结果用途 | 作为 LLM 的生成模板（必须准确） | 作为参考（不准确也不致命） |
| Top-K | 5 + rerank 到 2 | 3 即可（减少 prompt 长度） |
| 对准确率要求 | 高（错了就生成错误话术） | 低（LLM 自主判断是否采用） |
| 基础设施 | 复用 | 复用现有 874 chunks + Milvus |

**时延影响：** RAG 检索（<100ms）与 Tool 执行（<100ms）并行，在 LLM 调用前全部就绪。总时延 = Skill Routing(1s) + LLM推理(1-2s) = 2-3s，与无 RAG 时完全相同。

### 3.4 Agent B：并行置信度审查

Agent B 是纯规则/结构校验，不使用 LLM，在 <10ms 内完成。它与 Tool 执行并行启动，在 Agent A 生成之前就做出"通过/短路"决策。

**审查维度：**

| 检查项 | 扣分权重 | 说明 |
|--------|---------|------|
| Skill 匹配置信度 < 0.7 | -0.3 | LLM Skill Routing 输出的 confidence 过低 |
| 域不一致 | -0.4 | L1 分类器的域 vs skill 所属域不匹配 |
| 模板槽位缺失 | -0.2 x 缺失数 | 模板需要的槽位 vs tool 返回的数据有缺口 |
| 递进状态不匹配 | -0.2 | skill 要求的轮次 vs 实际会话轮次不一致 |
| Tool 执行失败 | -0.5 | 关键 tool 调用失败 |
| 关键词无交叉 | -0.15 | query 中不包含 skill 的任何核心关键词 |
| RAG 交叉验证不一致 | -0.1 / +0.1 | 轻量 RAG Top-1 的 category 与 skill 的 domain 是否一致（一致加分，不一致扣分） |

```
初始分 = 1.0 -> 逐项扣分 -> 最终分

score >= 0.5 -> 审查通过，Agent A 继续生成
score <  0.5 -> 审查失败，立即返回 fallback（不等 Agent A）
```

**关键效果：** 审查失败时提前短路，异常场景反而比正常场景更快返回。

### 3.5 Agent A：合规生成

Agent A 使用专门设计的 prompt，将合规约束内嵌到生成过程中，实现"生成即合规"：

```
你是金融客服坐席助手。请根据以下信息生成合规话术。

## 匹配场景
{skill.display_name}（{skill.skill_id}）

## 标准话术模板
{skill.templates[current_turn].script}

## 工具查询结果
{tool_results}

## 客户上下文
{conversation_summary}

## 合规红线（绝对禁止）
{skill.compliance_rules.forbidden}

## 必须包含的内容
{skill.compliance_rules.required_disclaimer}

请直接输出话术，不要解释。输出格式：
{"answer": "...", "next_step_hint": "..."}
```

后置的规则合规（12 个禁用语正则 + 关键业务规则）作为最终兜底，延迟 < 5ms。

### 3.6 反馈闭环与自演进机制

#### 反馈采集（零额外操作成本）

从坐席自然行为中推断反馈信号，不增加任何额外按钮：

| 坐席行为 | 推断信号 |
|---------|---------|
| 点击"发送"推荐话术 | 隐式 accept |
| 修改后发送 | 隐式 modify（diff 自动计算） |
| 未操作推荐、手动输入回复 | 隐式 reject |

#### 三级自演进

```
长尾问题（链路C, LLM自主推理）
    │
    │ 同类 query 出现 >= 5次 且 accept/modify率 >= 60%
    ▼
自动生成 Skill 草稿 -> 运营审核 -> 加入 Skill 库（链路B）
    │
    │ 该 skill 采纳率 >= 90% 且匹配频率进入 Top-N
    ▼
提取匹配规则 -> 硬编码到规则引擎（链路A, 规则短路）
```

**流量分布随时间自然迁移：**

| 时间 | 长尾（链路C） | Skill（链路B） | 规则（链路A） |
|------|-------------|---------------|-------------|
| 初期 | 40% | 50% | 10% |
| 3 月后 | 15% | 55% | 30% |
| 6 月后 | 5% | 45% | 50% |

#### 现有 Skill 持续优化

- **reject 率 > 30%**：触发条件可能有误，调整 trigger_keywords/examples
- **modify 率 > 50%**：话术模板不准，用坐席修改版更新模板
- **特定轮次 reject 多**：递进话术设计有问题，调整该轮次模板

#### 硬编码规则的安全机制

每条规则附带版本和过期时间，防止 SOP 更新后规则过时：

- 3 个月后自动降级回 Skill 链路重新验证
- 采纳率低于阈值（如 0.85）时自动降级
- SOP 更新时可批量失效相关规则

---

## 四、关键设计决策

### 4.1 为什么不继续用 RAG 作为主链路

| 维度 | RAG 方案 | Skill 方案 |
|------|---------|-----------|
| 递进话术 | 无法感知对话轮次，返回错误模板 | Skill 内按轮次组织，LLM 自动选 |
| 分支逻辑 | chunk 丢失决策条件 | Skill 内可描述分支 |
| 查询失败 | 检索质量差时全链路崩溃 | 不存在检索失败，Skill 在 prompt 中 |
| 维护成本 | 修改 SOP 需重跑 embed pipeline | 修改 Skill JSON 即可 |
| 长尾问题 | 强行匹配不相关模板 | 坦诚标注无覆盖，LLM 自主推理 |

RAG 不是被"替代"，而是从主链路退出。当 Skill 定义不足以覆盖某些需要丰富背景知识的场景时，可以保留为补充信息源。

### 4.2 为什么 Agent B 用规则而非 LLM

1. **GPU 资源争抢**：Agent A 和 Agent B 并行时如果都用 LLM，在单卡上实际时延约等于串行的 1.3-1.5 倍
2. **审查逻辑可枚举**：置信度、域一致性、槽位完整性、tool 状态都是结构化检查
3. **速度优势**：规则审查 <10ms，远早于 Agent A 的 LLM 生成完成，可实现"提前短路"

### 4.3 为什么需要 L1 分类器

54 个 Skill 全部放入一次 LLM 调用约 5K-10K tokens。在 7B 模型上上下文过长导致匹配精度下降、推理时延线性增长。

L1 分类器（10 分类，<50ms）将范围缩小到 4-8 个 Skill，LLM prompt 仅需 1K-3K tokens，匹配精度和时延均显著改善。

### 4.4 长尾链路的安全边界

LLM 自主推理时没有 Skill 约束，需要额外的安全控制：

| 控制项 | 规则 |
|--------|------|
| Tool 白名单 | 仅允许只读查询（get_customer_profile, get_bill_and_repayment_plan, get_call_history, get_sms_history, get_stop_collection_history, get_refund_history, query_ticket 等） |
| Tool 黑名单 | 禁止任何写操作（提交工单、修改账户、发起退款） |
| 输出约束 | 禁止输出具体金额承诺、利率数字、减免方案 |
| 话术限制 | 禁止说"我可以帮你操作"，只能说"建议您..." |
| 强制后缀 | 所有回答附加"以上信息仅供参考，具体以业务确认为准" |

### 4.5 核身层进入条件（当前实现）

核身层不是单独靠关键词规则决定，而是在 Chain A 规则命中或 Chain B/C 选中 Skill 后统一判断。判断函数位于 `fin_copilot/orchestrator.py::_skill_requires_identity`，核心原则如下：

| 场景 | 是否核身 | 说明 |
|------|----------|------|
| 问候、结束语、纯通话状态确认 | 否 | 不进入 Skill 工具查询 |
| 低风险产品介绍，如"会员是什么"、"增值服务是什么" | 否 | 即使 Skill YAML 中声明了个性化工具，也不因工具存在而核身 |
| 低风险 Skill 但用户问"我的/查询/账单/订单/扣款/还款结果/额度/退款/记录/短信" | 是 | 命中个人账户查询信号 |
| 中高风险查询或办理类 Skill | 是 | 涉及账户数据、工单、还款、额度、贷款等真实业务信息 |
| 长尾链路需要只读工具获取账户事实 | 是 | 核身后才执行工具并暴露账户事实 |

核身状态机：

```text
not_started
  → asking_name        # 校验 VERIFICATION_DB.real_name
  → asking_phone       # 校验手机号与姓名候选匹配
  → asking_id          # 校验身份证后四位；也支持完整身份证号提取后四位
  → passed             # 写入 customer_id、verified、masked name/phone，并回放 pending_query
  → failed             # 多次失败转人工
```

实现细节：

- 初始业务问题保存到 `ConversationState.customer.pending_query`，核身通过后自动重新处理原问题。
- 核身进行中时优先处理核身输入，避免被普通业务路由抢走。
- 客户可输入"上一步"回退一步，或输入"跳过核身"退出；退出后只能处理不需要核身的通用咨询。
- 一次性输入"姓名 + 手机号 + 身份证后四位/完整身份证号"可直接完成核身。

当前 mock 用户画像：

| customer_id | 姓名 | 手机号 | 身份证后四位 | 测试画像 |
|-------------|------|--------|--------------|----------|
| C100 | 张三 | 13812345678 | 1234 | 逾期客户，账单扣款失败，存在停催/催收投诉记录 |
| C101 | 李四 | 13900001111 | 5678 | 正常优质客户，存在会员退费到账记录 |
| C102 | 王五 | 18600002222 | 9012 | 新用户，额度冻结，存在退款处理中记录 |

---

## 五、与原有 Demo 的资产复用关系（保留/重构/移除）

新方案不是推倒重来，而是对现有 demo 进行有选择的复用与重构。

### 直接复用

| 资产 | 复用方式 |
|------|---------|
| 54 个 Skill 定义 | 已迁移为 `skills/definitions/*.yaml` + `skills/registry.json` |
| Tool 调度框架（tools/ + action_executor.py） | 完整复用，并行执行、统一接口、部分失败降级 |
| 合规规则层（12 禁用词 + 3 关键规则） | 作为后置规则合规基础，扩展到 Skill 级 compliance_rules |
| 身份验证流程 | 重构为姓名 -> 手机号 -> 身份证后四位的三步核身状态机，并按 Skill 风险/查询意图触发 |
| 工程骨架（FastAPI + pydantic + asyncio + httpx） | 完整复用 |
| 链路追踪（chain_debug + trace_logger） | 复用并扩展为全链路可观测 |

### 重构转化

| 原有模块 | 转化为 |
|---------|-------|
| 25+ 个 _build_*_response 方法 | Jinja2 模板引擎 + Skill JSON 中的 template 字段 |
| ScenarioRecaller 的 embedding 基础设施 | L1 分类器的备选 fallback |
| 874 个 SOP chunk | Skill JSON 中 templates + compliance_rules 的数据来源 |
| Router 规则决策树 | 链路 A 规则短路引擎的基础 |

### 移除

| 模块 | 原因 |
|------|------|
| RAG 检索主链路（Milvus 向量检索） | 从主链路退出 |
| Reranker（纯字符级） | 不再需要 |
| AnswerabilityChecker（阈值=0.0） | 由 Agent B 置信度审查替代 |
| QueryRewriter（默认关闭） | 由 L0 输入预处理替代 |
| ComplianceGate 中的 LLM 审核 | 由 Agent A prompt 内嵌合规 + 规则审查替代 |

---

## 六、上下文管理与信息传递

坐席辅助系统面对的是多轮、长周期对话（平均 70 轮，最长 265 轮）。上下文管理决定了每个模块能"看到"多少有效信息、以什么粒度看到、以及如何避免上下文膨胀导致的精度下降和时延增长。

### 6.1 上下文分层存储架构

系统维护三层上下文，粒度从细到粗，生命周期从短到长：

```
┌────────────────────────────────────────────────────────────┐
│ Layer 1: 滑动窗口（Short-Term Memory）                      │
│                                                              │
│ 内容：最近 N 轮原始对话（坐席+客户发言）                      │
│ 窗口大小：N = 6-8 轮（约 12-16 条消息）                      │
│ 生命周期：随对话滑动，超出窗口的轮次自动丢弃                  │
│ 用途：传给 LLM Skill Routing 和 Agent A 合规生成              │
│ 格式：                                                       │
│   [                                                          │
│     {"role": "customer", "text": "...", "turn": 15},         │
│     {"role": "agent", "text": "...", "turn": 15},            │
│     ...                                                      │
│   ]                                                          │
└────────────────────────────────────────────────────────────┘
                         │
                    溢出轮次 → 压缩进 Layer 2
                         │
┌────────────────────────▼───────────────────────────────────┐
│ Layer 2: 滚动摘要（Mid-Term Memory）                        │
│                                                              │
│ 内容：对滑出窗口的对话进行增量式摘要                          │
│ 更新频率：每滑出一轮更新一次（追加式，非全量重写）             │
│ 长度控制：摘要上限 300 字，超出时压缩旧段落                   │
│ 生命周期：整个会话期间                                       │
│ 用途：传给 LLM 作为历史背景，传给 Agent B 做状态校验          │
│ 格式：                                                       │
│   "客户来电咨询逾期协商。已完成身份验证（张*明，尾号3456）。   │
│    客户表示因失业导致还款困难，首次协商未达成一致，            │
│    客户要求减免部分利息。当前处于第二次沟通。"                 │
└────────────────────────────────────────────────────────────┘
                         │
                    结构化信息提取 → 写入 Layer 3
                         │
┌────────────────────────▼───────────────────────────────────┐
│ Layer 3: 结构化状态（Long-Term Structured State）            │
│                                                              │
│ 内容：从对话中提取的关键业务字段，确定性存储                   │
│ 更新方式：规则提取为主，必要时 LLM 辅助                       │
│ 生命周期：整个会话期间 + 可持久化到 Redis                     │
│ 用途：所有模块共享的"事实源"                                  │
│ 格式：                                                       │
│   {                                                          │
│     "session_id": "...",                                     │
│     "customer": {                                            │
│       "name_masked": "张*明",                                │
│       "phone_masked": "138****5678",                         │
│       "id_last4": "3456",                                    │
│       "verified": true,                                      │
│       "verification_level": "full"                           │
│     },                                                       │
│     "intent": {                                              │
│       "current_skill_id": "overdue_negotiation",             │
│       "domain": "逾期问题",                                  │
│       "turn_in_skill": 2,                                    │
│       "intent_shifts": ["greeting->overdue_negotiation"]     │
│     },                                                       │
│     "slots": {                                               │
│       "overdue_amount": 5680.00,                             │
│       "overdue_days": 45,                                    │
│       "overdue_reason": "失业",                              │
│       "customer_request": "减免利息",                        │
│       "repayment_ability": "暂无收入"                        │
│     },                                                       │
│     "tool_cache": {                                          │
│       "get_customer_profile": {"data": {...}, "ts": "..."},  │
│       "get_bill_and_repayment_plan": {"data": {...}, "ts": "..."} │
│     },                                                       │
│     "risk_flags": ["emotional", "overdue_45d"],              │
│     "compliance_state": {                                    │
│       "disclaimer_given": true,                              │
│       "forbidden_triggered": []                              │
│     },                                                       │
│     "ask_count": 1,                                          │
│     "total_turns": 15                                        │
│   }                                                          │
└────────────────────────────────────────────────────────────┘
```

### 6.2 各模块的上下文消费关系

不同模块需要不同粒度的上下文。精确控制每个模块"看到什么"，既避免信息不足导致误判，也避免信息过载导致 LLM 注意力分散。

| 模块 | 消费的上下文层 | 具体字段 | 为什么只需要这些 |
|------|--------------|---------|----------------|
| **L0 输入预处理** | Layer 1（最近 2 轮） | 上一轮坐席发言 + 客户发言 | 指代消解只需最近上下文（"那个" → 指代上一轮提到的事物） |
| **L1 分类器** | Layer 3.intent | current_skill_id, domain | 分类器只需知道当前域做 bias，不需要看原始对话 |
| **LLM Skill Routing** | Layer 1 + Layer 2 + Layer 3.intent/slots | 滑动窗口 + 摘要 + 当前 skill + 已收集槽位 | LLM 需要足够上下文理解用户意图，但不需要 tool_cache 原始数据 |
| **Agent B 置信度审查** | Layer 3 | intent, slots, tool_cache, risk_flags | 纯结构化校验，不需要原始对话文本 |
| **Agent A 合规生成** | Layer 1（最近 3 轮）+ Layer 2 + Layer 3.slots/compliance_state | 近期对话 + 摘要 + 槽位数据 + 合规历史 | 生成话术需要语境，但只需近期语境 + 摘要，不需要全量历史 |
| **长尾链路 LLM** | Layer 1 + Layer 2 + Layer 3.customer/slots | 滑动窗口 + 摘要 + 客户信息 + 槽位 | 自主推理需要较完整的上下文 |
| **后置规则合规** | Layer 3.compliance_state/risk_flags | 合规状态 + 风险标签 | 规则检查只需结构化字段 |

### 6.3 滑动窗口管理

```
对话总轮次: T1  T2  T3  T4  T5  T6  T7  T8  T9  T10 T11 ...
                                          │              │
窗口（N=6）:                               └──── 当前窗口 ─┘
                                          T6  T7  T8  T9  T10 T11

T5 滑出窗口时:
  1. T5 的关键信息提取 -> 写入 Layer 3（槽位/意图/风险）
  2. T5 的对话文本 -> 追加压缩进 Layer 2 摘要
  3. T5 从 Layer 1 移除
```

**窗口大小选择依据：**

- 6-8 轮覆盖一个完整的"问题-澄清-解决"交互周期
- 对应约 600-1200 tokens（中文），不会挤占 Skill 定义的 prompt 空间
- 过小（<4轮）会丢失多轮追问上下文；过大（>10轮）对 7B 模型造成注意力稀释

### 6.4 滚动摘要策略

摘要不使用 LLM 生成（避免额外时延），而是采用规则 + 模板拼接：

```python
def update_summary(summary: str, exiting_turn: Turn, state: StructuredState) -> str:
    """当一轮滑出窗口时，增量更新摘要"""

    # 1. 提取该轮的关键事件
    events = []
    if exiting_turn.has_intent_shift:
        events.append(f"客户话题从{exiting_turn.prev_intent}转为{exiting_turn.new_intent}")
    if exiting_turn.new_slots:
        slot_desc = "、".join(f"{k}={v}" for k, v in exiting_turn.new_slots.items())
        events.append(f"获取到信息：{slot_desc}")
    if exiting_turn.tool_called:
        events.append(f"查询了{','.join(exiting_turn.tool_called)}")
    if exiting_turn.has_risk_flag:
        events.append(f"客户表现出{exiting_turn.risk_flag}情绪")
    if exiting_turn.verification_completed:
        events.append("完成身份验证")

    # 2. 无关键事件的轮次不写入摘要（过滤噪声）
    if not events:
        return summary

    # 3. 追加到摘要
    new_line = f"第{exiting_turn.turn_num}轮：{'；'.join(events)}。"
    summary = summary + new_line

    # 4. 长度控制：超出上限时压缩最早的段落
    if len(summary) > 300:
        # 保留最近 2/3，压缩最早 1/3 为一句概括
        split_point = len(summary) // 3
        old_part = summary[:split_point]
        recent_part = summary[split_point:]
        summary = f"早期对话：{_compress_to_one_line(old_part)}。" + recent_part

    return summary
```

**设计要点：**
- 只记录"事件"不记录"原文"，摘要保持精简
- 无事件轮次不入摘要，避免 "客户说嗯、坐席说好的" 这类噪声
- 超长时对早期内容二次压缩，确保摘要不膨胀

### 6.5 结构化状态的提取与更新

Layer 3 的结构化状态是所有模块共享的"事实源"。更新采用规则优先、LLM 辅助的策略：

**规则提取（覆盖 90% 场景，零时延）：**

| 字段 | 提取规则 |
|------|---------|
| customer.verified | 身份验证流程完成时置 true |
| intent.current_skill_id | Skill Routing 输出 |
| intent.turn_in_skill | 同一 skill 连续匹配时 +1，切换 skill 时重置为 1 |
| slots.overdue_amount | 从 tool_cache 中 get_bill 结果提取 |
| slots.overdue_days | 同上 |
| slots.overdue_reason | 关键词匹配客户发言（"失业/生病/资金周转/没钱"等） |
| risk_flags | 规则检测（情绪关键词、逾期天数阈值、投诉关键词） |
| tool_cache | Tool 执行结果直接写入，附带时间戳 |
| compliance_state | 合规检查结果写入 |

**LLM 辅助提取（仅长尾场景，约 10%）：**

当规则无法从客户发言中提取槽位时（如"我之前跟你们说过我的情况了"），可在 Skill Routing 的 LLM 调用中附带要求提取关键信息，复用同一次 LLM 调用，不增加额外时延：

```
... (Skill Routing prompt 末尾追加)

同时，请从对话中提取以下信息（如有）：
- customer_request: 客户的核心诉求
- overdue_reason: 逾期原因
- repayment_ability: 客户自述的还款能力

输出格式：
{
  "skill_id": "...",
  "template_variant": "...",
  "tools_needed": [...],
  "extracted_slots": {"customer_request": "...", ...}
}
```

### 6.6 Tool 缓存与新鲜度管理

Tool 调用结果存入 Layer 3 的 tool_cache，避免同一会话内重复调用相同 tool：

```
tool_cache 策略：
├─ 写入：每次 tool 执行成功后写入，附带时间戳
├─ 读取：下次需要同一 tool 时先查缓存
├─ 失效：
│   ├─ TTL 过期（默认 300s，可按 tool 配置）
│   ├─ 意图切换时清除不相关 tool 的缓存
│   └─ 坐席手动触发刷新
└─ 传递：tool_cache 数据用于：
    ├─ Agent A 合规生成（作为话术中的业务数据源）
    ├─ Agent B 审查（检查槽位完整性）
    └─ 结构化状态更新（提取 slots）
```

### 6.7 上下文在三条链路中的完整传递流

#### 链路 A（规则短路）

```
输入 → L0 预处理（读 Layer1 最近2轮做指代消解）
     → 规则匹配（读 Layer3.intent 做 bias）
     → Tool 执行（读 Layer3.tool_cache 做缓存判断，写入新结果）
     → 模板填充（读 Layer3.slots + tool_cache 填充槽位）
     → 规则合规（读 Layer3.compliance_state + risk_flags）
     → 更新 Layer3（写入本轮结果）
     → 更新 Layer1（追加本轮对话）
```

**特点：** 全程只读写结构化状态，不消费摘要，不调用 LLM。

#### 链路 B（Skill 路由）

```
输入 → L0 预处理（读 Layer1 最近2轮）
     → L1 分类器（读 Layer3.intent.domain）
     → LLM Skill Routing:
     │   传入 = {
     │     sliding_window: Layer1（最近6-8轮）,
     │     summary: Layer2,
     │     current_state: {
     │       skill_id: Layer3.intent.current_skill_id,
     │       turn_in_skill: Layer3.intent.turn_in_skill,
     │       collected_slots: Layer3.slots,
     │       risk_flags: Layer3.risk_flags
     │     },
     │     candidate_skills: [域内4-8个skill定义]
     │   }
     │   输出 = skill_id + template_variant + tools + extracted_slots
     │
     ├→ Tool 执行（读 Layer3.tool_cache，写入新结果）
     ├→ Agent B 审查（读 Layer3 全量结构化状态）
     │
     └→ Agent A 合规生成:
          传入 = {
            recent_turns: Layer1（最近3轮）,
            summary: Layer2,
            template: 匹配到的skill模板,
            tool_data: Layer3.tool_cache,
            slots: Layer3.slots,
            compliance_rules: skill.compliance_rules,
            compliance_history: Layer3.compliance_state
          }

     → 后置规则合规（读 Layer3.compliance_state）
     → 更新 Layer3（本轮 intent/slots/tool_cache/compliance）
     → 更新 Layer1（追加本轮对话）
     → 更新 Layer2（如有轮次滑出窗口）
```

#### 链路 C（长尾自主 + 轻量 RAG 辅助）

```
输入 → L0 预处理（读 Layer1 最近2轮）
     → LLM Skill Routing → 无匹配
     → 并行启动：
     │   ├─ 轻量 RAG 检索（Milvus Top-3，复用现有 874 chunks，<100ms）
     │   ├─ Tool 执行（LLM 自主决定，读写 Layer3.tool_cache，<100ms）
     │   └─ 构建长尾 prompt（读取上下文层）
     → 长尾 LLM:
          传入 = {
            sliding_window: Layer1（最近6-8轮）,
            summary: Layer2,
            customer_info: Layer3.customer,
            collected_slots: Layer3.slots,
            rag_references: RAG Top-3 片段（标注为"仅供参考"）,
            tool_results: Layer3.tool_cache,
            available_tools: [只读tool列表及描述],
            compliance_constraints: [长尾专用加严规则]
          }
     → 后置规则合规（加严模式，读 Layer3）
     → 更新 Layer3（本轮结果，skill_id 标记为 null，记录 rag_chunk_ids）
     → 更新 Layer1 + Layer2
```

**RAG 与 Tool 并行执行，不增加链路时延。** RAG 结果作为 LLM 的参考材料传入，LLM 自主判断是否采用。

### 6.8 意图切换时的上下文处理

当 IntentGuard 检测到意图切换（如从"还款咨询"切到"投诉催收"）时，上下文需要特殊处理：

```
意图切换触发：
├─ Layer 1（滑动窗口）: 保留不变，LLM 需要看到切换前的对话
├─ Layer 2（摘要）: 追加"客户话题转为XXX"事件
├─ Layer 3（结构化状态）:
│   ├─ intent: 更新 current_skill_id，turn_in_skill 重置为 1
│   ├─ intent_shifts: 追加切换记录
│   ├─ slots: 保留通用槽位（customer_name, phone），清除场景专属槽位
│   ├─ tool_cache: 保留客户档案类缓存，清除业务类缓存
│   └─ risk_flags: 保留不变（情绪/投诉标记跨场景有效）
└─ 不清除验证状态（身份验证跨场景有效）
```

### 6.9 上下文大小控制与 prompt 预算

7B 模型在 4K-8K 上下文长度下表现最佳。需要严格控制各部分的 token 预算：

| Prompt 区块 | Token 预算 | 说明 |
|-------------|-----------|------|
| 系统指令 + 合规规则 | ~300 tokens | 固定开销 |
| Skill 候选列表（4-8 个） | ~800-1500 tokens | L1 分类器缩小范围后 |
| 滑动窗口（6-8 轮） | ~600-1200 tokens | 实际对话内容 |
| 滚动摘要 | ~150-300 tokens | 压缩后的历史 |
| 结构化状态摘要 | ~100-200 tokens | 仅传入关键字段 |
| Tool 结果 | ~200-400 tokens | 结构化 JSON |
| 输出空间预留 | ~500 tokens | 生成回答 |
| **合计** | **~2650-4400 tokens** | 7B 模型舒适区间 |

如果接近上限，按优先级裁剪：先缩减 Skill 候选数量 → 减少窗口轮数 → 压缩摘要。

---

## 七、时延对比总结

| 场景类型 | 原有 Demo | 新方案 | 降幅 |
|---------|----------|--------|------|
| 高频确定性（账单/还款日/会员查询） | 2.5-5s | < 200ms | 90%+ |
| 标准 Skill 匹配 | 4-8s | 1-3s | 60-70% |
| 异常/审查失败 | 4-8s | < 1.6s（提前短路） | 70-80% |
| 长尾无覆盖 | 4-8s（错误匹配） | 1.5-3s（正确标注） | 效果提升 + 时延持平 |
