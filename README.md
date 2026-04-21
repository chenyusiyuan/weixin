# 金融客服坐席话术推荐系统 (Financial Customer Service Copilot)

一个为人工客服坐席提供实时话术推荐、工具辅助数据查询和合规检查的 Copilot 系统。采用 Skill-based 架构，通过三链路自动路由实现高效精准的场景匹配。

## 架构概览

```
客户消息 → L0 预处理 → 规则引擎匹配?
  ├─ YES → Chain A: 规则短路 (<200ms, 零LLM, 模板+工具数据)
  └─ NO  → L1 域分类 → LLM Skill 路由
              ├─ 匹配 (confidence ≥ θ) → Chain B: 技能路由 (1-5s, 2次LLM)
              └─ 无匹配               → Chain C: 长尾兜底 (安全回复)

涉及个人账户数据的链路会先进入 Identity Verification Gate（核身层），
通过后再执行原始业务查询；产品通用咨询、问候等低风险问题不触发核身。
```

- **Chain A** — 零 LLM。规则命中 → 工具执行 → Jinja2 模板填充 → 合规检查。覆盖高频确定性场景。
- **Chain B** — 主链路。L1 域分类 → LLM Skill 路由 → Agent B 置信审计 (纯规则, <10ms) + 工具并行执行 → Agent A 合规生成 → 后置合规检查。
- **Chain C** — 兜底。无 SOP 覆盖场景返回安全回复，强制免责声明。

## 技术栈

- **语言:** Python 3.11+
- **框架:** FastAPI + Pydantic v2 + asyncio + httpx
- **LLM:** DeepSeek / Qwen / 任意 OpenAI 兼容 API
- **模板:** Jinja2 (话术槽位填充)
- **Skill 定义:** YAML (PyYAML)

## 目录结构

```
fin_copilot/                    # 主应用包
├── config.py                   # 配置 (pydantic-settings, 从 .env 加载)
├── main.py                     # FastAPI 入口 + 组件装配
├── cli_demo.py                 # CLI 交互演示
├── orchestrator.py             # 三链路主编排器
├── models/                     # Pydantic 数据模型
│   ├── conversation.py         # ConversationState (三层上下文)
│   ├── skill.py                # SkillDefinition, SkillMatch
│   ├── response.py             # CopilotResponse
│   ├── audit.py                # ConfidenceAuditResult
│   └── tool_io.py              # ToolCallResult
├── context/                    # 三层上下文管理
│   ├── sliding_window.py       # Layer 1: 最近 6-8 轮对话
│   ├── rolling_summary.py      # Layer 2: 规则摘要 (≤300字, 无LLM)
│   ├── structured_state.py     # Layer 3: 意图/槽位/工具缓存/风险标签
│   └── context_manager.py      # 统一上下文编排
├── skills/
│   └── loader.py               # YAML Skill 加载器
├── routing/
│   ├── rule_engine.py          # Chain A: 关键词规则引擎
│   ├── domain_classifier.py    # L1: 10业务域 + 会话流程关键词分类器
│   └── skill_router.py         # Chain B: LLM Skill 路由
├── agents/
│   ├── compliant_generator.py  # Agent A: 合规话术生成
│   ├── confidence_auditor.py   # Agent B: 纯规则置信审计 (<10ms)
│   └── longtail_reasoner.py    # Chain C: 长尾兜底 (Phase 1 占位)
├── compliance/
│   └── rule_checker.py         # 6层后置合规检查
├── llm/
│   └── client.py               # Async OpenAI 兼容 LLM 客户端
├── routers/
│   └── gateway.py              # FastAPI 路由
└── utils/
    ├── trace.py                # trace_id 生成
    └── template_engine.py      # Jinja2 模板填充

skills/                         # Skill 知识层 (配置, 非代码)
├── registry.json               # 54 个 Skill 索引 (按域分组)
├── definitions/                # 每个 Skill 一个 YAML 文件
├── prompts/                    # LLM Prompt 模板
└── references/compliance/      # 违禁词、业务规则 (可热更新)

rules/
└── rule_engine.json            # Chain A 规则 (6 条预置)

tools/                          # 业务工具 (Mock 数据)
├── registry.py                 # 工具注册表 (11 个工具)
├── executor.py                 # 异步并行执行器
└── *.py                        # 各工具 handler
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 LLM

创建 `.env` 文件:

```env
LLM_API_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=deepseek-chat
```

支持任意 OpenAI 兼容 API (DeepSeek / Ollama / OpenAI 等)。

### 3. 启动 API 服务

```bash
uvicorn fin_copilot.main:app --host 0.0.0.0 --port 8000
```

### 4. 调用接口

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "s1", "user_text": "怎么还款"}'
```

### 5. CLI 交互演示

```bash
python -m fin_copilot.cli_demo
```

### 6. 离线评估

```bash
python tests/eval_offline.py
```

## 核身层与 Mock 数据

当前实现中，核身层位于 `fin_copilot/orchestrator.py`，在 Chain A/B/C 业务路由选中 Skill 后统一判断是否需要拦截。判断原则：

- 中高风险或明确涉及账户数据查询/办理的 Skill，需要先核身。
- 低风险产品介绍类 Skill 即使声明了工具，也不会仅因工具存在而核身。
- 低风险 Skill 只有当客户话术包含“我的、查询、账单、订单、扣款、还款结果、额度、退款、记录、短信”等个人账户查询信号时才核身。
- 核身中优先处理核身输入，避免被普通业务路由打断。

核身状态机：

```text
not_started → asking_name → asking_phone → asking_id → passed
                                               └────→ failed（多次错误转人工）
```

本地测试画像在 `tools/mock_data.py` 中维护：

| customer_id | 姓名 | 手机号 | 身份证后四位 | 典型画像 |
|-------------|------|--------|--------------|----------|
| C100 | 张三 | 13812345678 | 1234 | 逾期客户，有扣款失败、停催和催收投诉记录 |
| C101 | 李四 | 13900001111 | 5678 | 正常优质客户，有会员退费到账记录 |
| C102 | 王五 | 18600002222 | 9012 | 新用户，额度冻结，有退款处理中记录 |

坐席辅助判断信息已补齐以下只读工具，并接入工具注册表：

| 工具 | 说明 |
|------|------|
| `get_call_history` | 进线/通话记录 |
| `get_sms_history` | 系统短信记录 |
| `get_stop_collection_history` | 停催申请记录 |
| `get_refund_history` | 退费/退款记录 |

建议回归用例：

```text
1. 个人账户查询：我要查询账单扣款情况 → 张三 → 13812345678 → 1234，应核身通过并继续回答原问题。
2. 核身失败：姓名/手机号/身份证后四位错误，应停留在当前核身步骤；多次失败后转人工。
3. 产品咨询：会员是什么，有什么权益，应直接返回通用介绍，tools=[]，不进入核身。
4. 问候：你好，应直接寒暄，不进入核身。
```

## API

### POST /api/chat

请求:
```json
{
  "session_id": "会话ID",
  "user_text": "客户消息",
  "channel": "online",
  "customer_id": ""
}
```

响应:
```json
{
  "output_type": "bot_reply",
  "answer": "推荐话术",
  "next_step_hint": "建议下一步",
  "matched_skill_id": "overdue_negotiation",
  "confidence": 0.95,
  "route": "route_b",
  "compliance_passed": true,
  "latency_ms": 4500,
  "trace_id": "tr-1713000000000-abc12345"
}
```

### GET /api/health

健康检查，返回 `{"status": "ok"}`。

## 合规检查 (6 层)

1. **全局违禁词** — 16 个禁用表达 (含排除规则)
2. **Skill 级违禁** — 每个 Skill 独立的禁用表达
3. **超权检测** — 涉及减免/免息必须附免责声明
4. **长尾加严** — 禁止操作承诺, 强制免责后缀
5. **PII 泄露检测** — 身份证/手机号/银行卡号 regex
6. **免责声明自动补充** — 缺失时自动追加

## 域划分 (10 个业务域 + 1 个会话流程域)

业务域：会员、额度、还款、贷款、费用、活动、业务办理、账户、逾期、优享卡

会话流程域：问候、确认、身份回读、渠道核验、结束语等非业务咨询链路。

## 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LLM_API_URL` | `http://localhost:11434/v1` | LLM API 地址 |
| `LLM_API_KEY` | `ollama` | API Key |
| `LLM_MODEL` | `qwen2.5:7b` | 模型名称 |
| `SLIDING_WINDOW_SIZE` | `8` | 滑动窗口轮数 |
| `SUMMARY_MAX_LENGTH` | `300` | 摘要最大字数 |
| `TOOL_CACHE_TTL` | `300` | 工具缓存过期秒数 |
| `CONFIDENCE_THRESHOLD` | `0.5` | Agent B 审计通过阈值 |
| `ROUTING_TEMPERATURE` | `0.1` | Skill 路由温度 |
| `GENERATION_TEMPERATURE` | `0.3` | 话术生成温度 |
