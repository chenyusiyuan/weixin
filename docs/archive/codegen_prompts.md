# 金融客服坐席话术推荐系统 — 代码实现方案

> 本文档是可直接执行的分阶段实现 prompt。每个 Phase 拆分为独立的实现任务，每个任务包含：目标、前置依赖、输入/输出规范、实现要点、验收标准。
>
> **技术栈：** Python 3.11+ / FastAPI / Pydantic v2 / asyncio / httpx / Jinja2 / PyYAML
> **LLM：** Qwen2.5:7b (Ollama, OpenAI-compatible API)
> **向量库：** Milvus Lite (仅链路 C 辅助 RAG)
> **现有代码：** `/Users/bytedance/Project/weixin/v/` (fin_agent + rag)

---

## Phase 1 总览：基础验证（2-4 周）

**目标：** 实现三条链路的最小可用版本，验证 Skill-based 方案的可行性。

**不做：** L1 分类器训练（用规则+embedding fallback）、反馈闭环、链路 C RAG 辅助、Redis 持久化、推理加速。

**验收标准：**
- Skill 匹配 TOP1 准确率 >= 80%（基于 test.jsonl 人工评估）
- 链路 A 时延 < 200ms
- 链路 B 时延 < 3s
- 合规通过率 >= 96%

**目录结构（最终产出）：**

```
/Users/bytedance/Project/weixin/
├── fin_copilot/
│   ├── __init__.py
│   ├── config.py                      # 全局配置（pydantic-settings）
│   ├── main.py                        # FastAPI 入口
│   ├── cli_demo.py                    # CLI 演示入口
│   │
│   ├── models/                        # Pydantic 数据模型
│   │   ├── __init__.py
│   │   ├── conversation.py            # ConversationState (Layer 1/2/3)
│   │   ├── skill.py                   # SkillDefinition, SkillMatch
│   │   ├── tool_io.py                 # ToolResults
│   │   ├── response.py                # CopilotResponse
│   │   └── audit.py                   # ConfidenceAuditResult
│   │
│   ├── context/                       # 三层上下文管理
│   │   ├── __init__.py
│   │   ├── sliding_window.py          # Layer 1: 滑动窗口
│   │   ├── rolling_summary.py         # Layer 2: 滚动摘要
│   │   ├── structured_state.py        # Layer 3: 结构化状态
│   │   └── context_manager.py         # 统一上下文管理器
│   │
│   ├── routing/                       # 链路路由
│   │   ├── __init__.py
│   │   ├── rule_engine.py             # 链路 A: 规则短路引擎
│   │   ├── domain_classifier.py       # L1 域分类（Phase1 用规则实现）
│   │   └── skill_router.py            # 链路 B: LLM Skill Routing
│   │
│   ├── agents/                        # Agent 实现
│   │   ├── __init__.py
│   │   ├── compliant_generator.py     # Agent A: 合规生成
│   │   ├── confidence_auditor.py      # Agent B: 置信度审查
│   │   └── longtail_reasoner.py       # 链路 C: 长尾推理（Phase2）
│   │
│   ├── orchestrator.py                # 主编排器（三条链路调度）
│   │
│   ├── tools/                         # 业务工具（从 v1 复用）
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── executor.py                # 并行执行器
│   │   ├── customer_profile.py
│   │   ├── bill_plan.py
│   │   ├── loan_service.py
│   │   ├── membership_service.py
│   │   ├── quota_service.py
│   │   ├── ticket_query.py
│   │   └── mock_customer_data.py
│   │
│   ├── compliance/                    # 合规模块
│   │   ├── __init__.py
│   │   └── rule_checker.py            # 后置规则合规检查
│   │
│   ├── llm/                           # LLM 客户端（从 v1 复用）
│   │   ├── __init__.py
│   │   └── client.py
│   │
│   ├── routers/                       # API 路由
│   │   ├── __init__.py
│   │   └── gateway.py
│   │
│   └── utils/                         # 工具函数
│       ├── __init__.py
│       ├── trace.py                   # 链路追踪
│       └── template_engine.py         # Jinja2 模板引擎
│
├── skills/                            # Skill 知识层（配置，不是代码）
│   ├── registry.json
│   ├── definitions/
│   │   ├── overdue_negotiation.yaml
│   │   ├── outstanding_bill_query.yaml
│   │   └── ... (20 个 Phase1 Skill)
│   ├── prompts/
│   │   ├── skill_routing.md
│   │   ├── compliant_gen.md
│   │   └── longtail_reasoning.md
│   └── references/
│       └── compliance/
│           ├── forbidden_words.json
│           └── key_rules.json
│
├── rules/                             # 链路 A 规则
│   └── rule_engine.json
│
└── tests/
    ├── test_orchestrator.py
    ├── test_skill_router.py
    ├── test_confidence_auditor.py
    ├── test_compliance.py
    └── test_context_manager.py
```

---

## Phase 1 · 任务 1：项目脚手架 + 数据模型

### 目标
创建 v2 项目结构，定义所有核心数据模型，迁移可复用的 v1 模块。

### 前置依赖
无（首个任务）

### 实现要点

**1.1 创建项目目录**

按上述目录结构创建 `/Users/bytedance/Project/weixin/`。

**1.2 config.py**

从 v1 的 `fin_agent/config.py` 迁移，调整以下配置：

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # LLM
    LLM_API_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL: str = "qwen2.5:7b"
    MOCK_MODE: bool = False

    # Embedding (复用，仅链路 C 和 L1 fallback 使用)
    EMBED_API_URL: str = "http://localhost:11434/api/embed"
    EMBED_MODEL: str = "bge-m3"

    # Skill
    SKILL_DEFINITIONS_DIR: str = "skills/definitions"
    SKILL_REGISTRY_PATH: str = "skills/registry.json"
    SKILL_PROMPTS_DIR: str = "skills/prompts"

    # Context
    SLIDING_WINDOW_SIZE: int = 8          # Layer 1 窗口轮数
    SUMMARY_MAX_LENGTH: int = 300         # Layer 2 摘要上限字数
    TOOL_CACHE_TTL: int = 300             # Layer 3 tool cache TTL 秒

    # Routing
    CONFIDENCE_THRESHOLD: float = 0.5     # Agent B 通过阈值
    RULE_ENGINE_PATH: str = "rules/rule_engine.json"

    # Compliance
    FORBIDDEN_WORDS_PATH: str = "skills/references/compliance/forbidden_words.json"
    KEY_RULES_PATH: str = "skills/references/compliance/key_rules.json"

    # Session
    SESSION_TTL_SECONDS: int = 3600

    # Debug
    CHAIN_DEBUG_ENABLED: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**1.3 核心数据模型 — models/conversation.py**

定义三层上下文的数据结构（这是整个系统的状态核心）：

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Message(BaseModel):
    role: str          # "customer" | "agent"
    text: str
    turn: int
    timestamp: datetime = Field(default_factory=datetime.now)

class CustomerInfo(BaseModel):
    name_masked: str = ""
    phone_masked: str = ""
    id_last4: str = ""
    verified: bool = False
    verification_level: str = "none"  # none | phone | full

class IntentState(BaseModel):
    current_skill_id: Optional[str] = None
    domain: Optional[str] = None
    turn_in_skill: int = 0
    intent_shifts: list[str] = Field(default_factory=list)

class ToolCacheEntry(BaseModel):
    data: dict
    ts: datetime

class ComplianceState(BaseModel):
    disclaimer_given: bool = False
    forbidden_triggered: list[str] = Field(default_factory=list)

class ConversationState(BaseModel):
    """三层上下文的统一容器"""
    session_id: str
    # Layer 1: 滑动窗口
    messages: list[Message] = Field(default_factory=list)
    # Layer 2: 滚动摘要
    summary: str = ""
    # Layer 3: 结构化状态
    customer: CustomerInfo = Field(default_factory=CustomerInfo)
    intent: IntentState = Field(default_factory=IntentState)
    slots: dict = Field(default_factory=dict)
    tool_cache: dict[str, ToolCacheEntry] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    compliance_state: ComplianceState = Field(default_factory=ComplianceState)
    ask_count: int = 0
    total_turns: int = 0
```

**1.4 models/skill.py**

```python
from pydantic import BaseModel
from typing import Optional

class SkillTriggers(BaseModel):
    keywords: list[str] = []
    examples: list[str] = []
    exclude_keywords: list[str] = []

class SkillTemplate(BaseModel):
    script: str
    required_slots: list[str] = []
    next_step: str = ""

class SkillCompliance(BaseModel):
    forbidden_expressions: list[str] = []
    required_disclaimer: str = ""
    must_include_when: list[dict] = []

class SkillDefinition(BaseModel):
    skill_id: str
    name: str
    description: str = ""
    domain: str
    intent_hierarchy: dict = {}       # {l1, l2, l3}
    route_mode: str = "rag_only"
    risk_level: str = "low"
    triggers: SkillTriggers = Field(default_factory=SkillTriggers)
    tools: dict = Field(default_factory=dict)  # {required: [], optional: []}
    templates: dict[str, SkillTemplate] = {}
    branch_conditions: list[dict] = []
    compliance: SkillCompliance = Field(default_factory=SkillCompliance)
    escalation: list[dict] = []
    fallback: dict = {}

class SkillMatch(BaseModel):
    """LLM Skill Routing 的输出"""
    skill_id: str
    template_variant: str = "first_contact"
    confidence: float = 0.0
    tools_needed: list[str] = []
    extracted_slots: dict = {}
    reasoning: str = ""
```

**1.5 models/response.py**

```python
from pydantic import BaseModel
from typing import Optional

class CopilotResponse(BaseModel):
    output_type: str = "bot_reply"   # bot_reply | followup | handoff | fallback
    answer: str = ""
    next_step_hint: str = ""
    matched_skill_id: Optional[str] = None
    matched_skill_name: Optional[str] = None
    confidence: float = 0.0
    route: str = ""                  # route_a | route_b | route_c
    warning: Optional[str] = None    # 链路 C 的 ⚠️ 标注
    rag_references: list[str] = []
    tools_called: list[str] = []
    trace_id: str = ""
    compliance_passed: bool = True
```

**1.6 models/audit.py**

```python
from pydantic import BaseModel

class ConfidenceAuditResult(BaseModel):
    score: float
    passed: bool
    reasons: list[str] = []
    fallback_type: str = ""  # "" | "safe_reply" | "handoff"
```

**1.7 复用 v1 模块**

不再依赖或复制 `v1` 模块。

- LLM 客户端在新工程中重新实现
- tool handler 在新工程中重新实现
- tracing / utils 按新目录结构实现

### 验收标准
- 当前根目录下的项目目录结构完整
- 所有 model 可导入，`python -c "from fin_copilot.models.conversation import ConversationState"` 无报错
- config 可从 .env 加载
- 新实现的 tool handler 可在当前工程中正常调用

---

## Phase 1 · 任务 2：Skill 定义编写 + 加载器

### 目标
将 v1 的 ScenarioDefinition（51 个场景）中 Top-20 高频场景转化为 Skill YAML，实现 Skill 加载器和 registry.json。

### 前置依赖
任务 1（models/skill.py 已定义）

### 实现要点

**2.1 从 v1 registry.py 提取场景数据**

基于 `/Users/bytedance/Project/weixin/skill-based方案.md`、`/Users/bytedance/Project/weixin/技术方案设计文档.md` 与现有业务资料，整理 Top-20 高频场景（按 route_mode 优先级：tool_only > tool_rag > rag_only > direct_reply，覆盖高频业务场景）。

Phase 1 优先转化的 20 个场景（覆盖主要业务）：

```
# tool_only（高频查询）
outstanding_bill_query, repayment_due_date_query, overdue_date_query,
member_status_query, member_cancel, quota_query, loan_status_query,
fee_detail_query, premium_card_status_query, repayment_result_query

# tool_rag（需要话术模板）
overdue_negotiation, repayment_failure_bank_card, early_settlement_request,
collection_complaint, refund_request, member_consultation

# direct_reply（简单固定回复）
greeting, farewell, manual_service_request, unknown_query
```

**2.2 YAML 转化规则**

对每个 ScenarioDefinition，按以下映射生成 YAML：

```
ScenarioDefinition          →  Skill YAML
─────────────────              ──────────
scenario_id                 →  skill_id
display_name                →  name
l1 / l2 / l3               →  intent_hierarchy.l1/l2/l3
category_cn                 →  domain
examples                    →  triggers.examples
keywords                    →  triggers.keywords
actions                     →  tools.required
route_mode                  →  route_mode
direct_reply_answer         →  templates.default.script (direct_reply 场景)
fallback_answer             →  fallback.answer
fallback_next_step          →  fallback.next_step
description                 →  description
```

**对于 tool_rag 场景**，还需从根目录 `sop/` 下的 SOP 数据中提取该场景对应 category 的话术与知识片段，将其整理为 `templates` 中的 script。对于逾期协商等需要递进话术的场景，从 SOP 中提取首次/二次/三次模板。

**2.3 Skill 加载器实现**

```python
# fin_copilot/routing/skill_loader.py

import yaml
from pathlib import Path
from functools import lru_cache
from fin_copilot.models.skill import SkillDefinition

class SkillLoader:
    """按需加载 Skill 定义"""

    def __init__(self, definitions_dir: str, registry_path: str):
        self._definitions_dir = Path(definitions_dir)
        self._registry = self._load_registry(registry_path)
        self._cache: dict[str, SkillDefinition] = {}

    def _load_registry(self, path: str) -> dict:
        """加载 registry.json，构建 domain -> [skill_id] 索引"""
        with open(path) as f:
            return json.load(f)

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        """按 ID 加载单个 Skill（带缓存）"""
        if skill_id in self._cache:
            return self._cache[skill_id]
        path = self._definitions_dir / f"{skill_id}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        skill = SkillDefinition(**data)
        self._cache[skill_id] = skill
        return skill

    def get_skills_by_domain(self, domain: str) -> list[SkillDefinition]:
        """按域加载该域下所有 Skill（供 LLM Skill Routing 使用）"""
        domain_info = self._registry.get("domains", {}).get(domain, {})
        skill_ids = [s["skill_id"] for s in domain_info.get("skills", [])]
        return [self.get_skill(sid) for sid in skill_ids if self.get_skill(sid)]

    def get_all_skill_ids(self) -> list[str]:
        """获取所有已注册的 skill_id"""
        ids = []
        for domain_info in self._registry.get("domains", {}).values():
            ids.extend(s["skill_id"] for s in domain_info.get("skills", []))
        return ids
```

**2.4 registry.json 生成**

编写脚本从已完成的 YAML 自动生成 registry.json：

```python
# scripts/build_registry.py
# 扫描 skills/definitions/*.yaml，提取元数据，按 domain 分组输出 registry.json
```

### 验收标准
- 20 个 Skill YAML 文件存在且格式合法
- `SkillLoader.get_skill("overdue_negotiation")` 返回正确的 SkillDefinition
- `SkillLoader.get_skills_by_domain("逾期问题")` 返回该域下所有 skill
- registry.json 包含 20 个 skill 的索引

---

## Phase 1 · 任务 3：三层上下文管理

### 目标
实现 Layer 1 滑动窗口、Layer 2 滚动摘要、Layer 3 结构化状态的完整生命周期管理。

### 前置依赖
任务 1（ConversationState 已定义）

### 实现要点

**3.1 context/sliding_window.py — Layer 1**

```python
class SlidingWindow:
    """管理最近 N 轮对话的滑动窗口"""

    def __init__(self, max_turns: int = 8):
        self.max_turns = max_turns

    def add_turn(self, state: ConversationState, customer_msg: str, agent_msg: str):
        """添加一轮对话，返回被滑出的消息（如有）"""
        turn = state.total_turns + 1
        state.total_turns = turn
        state.messages.append(Message(role="customer", text=customer_msg, turn=turn))
        state.messages.append(Message(role="agent", text=agent_msg, turn=turn))

        # 计算当前窗口中的轮次数
        exited = []
        turns_in_window = set(m.turn for m in state.messages)
        while len(turns_in_window) > self.max_turns:
            oldest_turn = min(turns_in_window)
            exited_msgs = [m for m in state.messages if m.turn == oldest_turn]
            state.messages = [m for m in state.messages if m.turn != oldest_turn]
            turns_in_window.discard(oldest_turn)
            exited.extend(exited_msgs)
        return exited

    def get_recent(self, state: ConversationState, n_turns: int | None = None) -> list[Message]:
        """获取最近 n 轮消息"""
        if n_turns is None:
            return state.messages
        turns = sorted(set(m.turn for m in state.messages))[-n_turns:]
        return [m for m in state.messages if m.turn in set(turns)]

    def format_for_prompt(self, state: ConversationState, n_turns: int | None = None) -> str:
        """格式化为 LLM prompt 文本"""
        msgs = self.get_recent(state, n_turns)
        lines = []
        for m in msgs:
            role_label = "客户" if m.role == "customer" else "坐席"
            lines.append(f"[{role_label}] {m.text}")
        return "\n".join(lines)
```

**3.2 context/rolling_summary.py — Layer 2**

```python
class RollingSummary:
    """基于规则的增量式滚动摘要（不使用 LLM）"""

    def __init__(self, max_length: int = 300):
        self.max_length = max_length

    def update(self, state: ConversationState, exited_messages: list[Message],
               prev_intent: str | None, new_intent: str | None,
               new_slots: dict | None, tools_called: list[str] | None,
               risk_flag: str | None, verification_completed: bool = False):
        """当消息滑出窗口时更新摘要"""
        events = []
        turn_num = exited_messages[0].turn if exited_messages else 0

        if prev_intent and new_intent and prev_intent != new_intent:
            events.append(f"客户话题从{prev_intent}转为{new_intent}")
        if new_slots:
            slot_desc = "、".join(f"{k}={v}" for k, v in new_slots.items())
            events.append(f"获取到信息：{slot_desc}")
        if tools_called:
            events.append(f"查询了{'、'.join(tools_called)}")
        if risk_flag:
            events.append(f"客户表现出{risk_flag}情绪")
        if verification_completed:
            events.append("完成身份验证")

        if not events:
            return  # 无关键事件不写入摘要

        new_line = f"第{turn_num}轮：{'；'.join(events)}。"
        state.summary += new_line

        # 长度控制
        if len(state.summary) > self.max_length:
            split = len(state.summary) // 3
            old_part = state.summary[:split]
            recent_part = state.summary[split:]
            # 简单压缩：取前50字+省略号
            compressed = old_part[:50] + "..." if len(old_part) > 50 else old_part
            state.summary = f"早期：{compressed} " + recent_part
```

**3.3 context/structured_state.py — Layer 3**

```python
from datetime import datetime, timedelta

class StructuredStateManager:
    """Layer 3 结构化状态的更新与查询"""

    def __init__(self, tool_cache_ttl: int = 300):
        self.tool_cache_ttl = tool_cache_ttl

    def update_intent(self, state: ConversationState, skill_id: str | None, domain: str | None):
        """更新意图状态"""
        prev_skill = state.intent.current_skill_id
        if skill_id == prev_skill and skill_id is not None:
            state.intent.turn_in_skill += 1
        else:
            if prev_skill and skill_id:
                state.intent.intent_shifts.append(f"{prev_skill}->{skill_id}")
            state.intent.current_skill_id = skill_id
            state.intent.domain = domain
            state.intent.turn_in_skill = 1
            # 意图切换：清除场景专属 slots，保留通用 slots
            generic_keys = {"customer_name", "phone", "id_last4"}
            state.slots = {k: v for k, v in state.slots.items() if k in generic_keys}

    def update_slots(self, state: ConversationState, new_slots: dict):
        """合并新 slots"""
        state.slots.update({k: v for k, v in new_slots.items() if v is not None})

    def update_tool_cache(self, state: ConversationState, tool_name: str, data: dict):
        """写入 tool 缓存"""
        state.tool_cache[tool_name] = ToolCacheEntry(data=data, ts=datetime.now())

    def get_cached_tool(self, state: ConversationState, tool_name: str) -> dict | None:
        """读取 tool 缓存（检查 TTL）"""
        entry = state.tool_cache.get(tool_name)
        if entry is None:
            return None
        if datetime.now() - entry.ts > timedelta(seconds=self.tool_cache_ttl):
            del state.tool_cache[tool_name]
            return None
        return entry.data

    def update_risk_flags(self, state: ConversationState, query: str):
        """基于规则检测风险标签"""
        emotional_keywords = ["投诉", "骚扰", "生气", "不满", "愤怒", "太过分", "要投诉", "曝光"]
        for kw in emotional_keywords:
            if kw in query and "emotional" not in state.risk_flags:
                state.risk_flags.append("emotional")
                break
        if "投诉" in query and "complaint" not in state.risk_flags:
            state.risk_flags.append("complaint")

    def extract_slots_from_query(self, state: ConversationState, query: str):
        """基于规则从用户发言中提取 slots（覆盖 90% 场景）"""
        # 逾期原因
        reason_map = {"失业": "失业", "没钱": "资金困难", "生病": "疾病",
                      "资金周转": "资金周转", "还不上": "资金困难"}
        for kw, reason in reason_map.items():
            if kw in query and "overdue_reason" not in state.slots:
                state.slots["overdue_reason"] = reason
        # 客户诉求
        request_map = {"减免": "减免利息", "延期": "延期还款", "分期": "分期还款"}
        for kw, req in request_map.items():
            if kw in query:
                state.slots["customer_request"] = req
```

**3.4 context/context_manager.py — 统一管理器**

```python
class ContextManager:
    """统一管理三层上下文的入口"""

    def __init__(self, settings):
        self.window = SlidingWindow(max_turns=settings.SLIDING_WINDOW_SIZE)
        self.summary = RollingSummary(max_length=settings.SUMMARY_MAX_LENGTH)
        self.state_mgr = StructuredStateManager(tool_cache_ttl=settings.TOOL_CACHE_TTL)
        self._sessions: dict[str, ConversationState] = {}

    def get_or_create(self, session_id: str) -> ConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState(session_id=session_id)
        return self._sessions[session_id]

    def process_turn_start(self, state: ConversationState, user_query: str):
        """轮次开始时：更新风险标签、提取 slots"""
        self.state_mgr.update_risk_flags(state, user_query)
        self.state_mgr.extract_slots_from_query(state, user_query)

    def process_turn_end(self, state: ConversationState,
                         user_query: str, agent_reply: str,
                         skill_match, tools_called: list[str]):
        """轮次结束时：更新窗口、摘要、意图"""
        prev_skill = state.intent.current_skill_id
        new_skill = skill_match.skill_id if skill_match else None
        # 更新意图
        domain = skill_match.domain if hasattr(skill_match, 'domain') else state.intent.domain
        self.state_mgr.update_intent(state, new_skill, domain)
        # 合并 LLM 提取的 slots
        if skill_match and skill_match.extracted_slots:
            self.state_mgr.update_slots(state, skill_match.extracted_slots)
        # 添加到窗口
        exited = self.window.add_turn(state, user_query, agent_reply)
        # 更新摘要
        if exited:
            new_slots = skill_match.extracted_slots if skill_match else None
            self.summary.update(state, exited, prev_skill, new_skill,
                                new_slots, tools_called, None)
```

### 验收标准
- 滑动窗口在超过 N 轮时正确滑出旧消息
- 摘要在有关键事件时正确追加，无事件时不追加
- 意图切换时 turn_in_skill 正确重置，场景 slots 正确清除
- tool cache TTL 过期后正确返回 None

---

## Phase 1 · 任务 4：Tool 执行器 + 合规检查器

### 目标
实现带缓存的并行 Tool 执行器和后置规则合规检查器。

### 前置依赖
任务 1（models 已定义），任务 3（Layer 3 tool_cache 管理）

### 实现要点

**4.1 tools/executor.py — 带缓存的并行执行器**

```python
import asyncio
from fin_copilot.context.structured_state import StructuredStateManager

class ToolExecutor:
    def __init__(self, registry: dict, state_mgr: StructuredStateManager):
        self.registry = registry   # tool_name -> async handler
        self.state_mgr = state_mgr

    async def execute(self, tool_names: list[str], state: ConversationState) -> dict:
        """
        并行执行指定 tools，自动跳过缓存命中的 tool。
        返回: {tool_name: {data} | None}
        """
        results = {}
        to_execute = []

        for name in tool_names:
            cached = self.state_mgr.get_cached_tool(state, name)
            if cached is not None:
                results[name] = cached
            elif name in self.registry:
                to_execute.append(name)
            else:
                results[name] = None  # 未注册的 tool

        if to_execute:
            coros = [self._safe_call(name, state) for name in to_execute]
            outcomes = await asyncio.gather(*coros)
            for name, outcome in zip(to_execute, outcomes):
                if outcome is not None:
                    self.state_mgr.update_tool_cache(state, name, outcome)
                results[name] = outcome

        return results

    async def _safe_call(self, name: str, state: ConversationState) -> dict | None:
        """单个 tool 调用，带 3s 超时和异常捕获"""
        try:
            handler = self.registry[name]
            return await asyncio.wait_for(handler(state), timeout=3.0)
        except Exception:
            return None
```

**4.2 compliance/rule_checker.py — 后置规则合规**

从 v1 的 `compliance_gate.py` 迁移规则层，移除 LLM 审查部分：

```python
import re
import json

class RuleComplianceChecker:
    def __init__(self, forbidden_words_path: str, key_rules_path: str):
        self.forbidden_patterns = self._load_forbidden(forbidden_words_path)
        self.key_rules = self._load_rules(key_rules_path)

    def check(self, answer: str, state: ConversationState,
              skill: SkillDefinition | None = None,
              is_longtail: bool = False) -> ComplianceResult:
        issues = []

        # 1. 全局违禁词检查
        for word, pattern in self.forbidden_patterns:
            if pattern.search(answer):
                issues.append({"type": "forbidden_word", "word": word, "severity": "key"})

        # 2. Skill 级违禁表达检查
        if skill and skill.compliance.forbidden_expressions:
            for expr in skill.compliance.forbidden_expressions:
                if expr in answer:
                    issues.append({"type": "skill_forbidden", "word": expr, "severity": "key"})

        # 3. 超权检查（"减免" 必须伴随 "具体以...为准"）
        if re.search(r"减免|免息|免除", answer):
            if "具体以" not in answer or "为准" not in answer:
                issues.append({"type": "ultra_vires", "severity": "key"})

        # 4. 必含免责声明检查
        if skill and skill.compliance.required_disclaimer:
            if skill.compliance.required_disclaimer not in answer:
                # 轻微违规：自动补充
                answer += f"\n{skill.compliance.required_disclaimer}"

        # 5. 长尾加严检查
        if is_longtail:
            if "我可以帮你操作" in answer or "帮您操作" in answer:
                issues.append({"type": "longtail_overpromise", "severity": "key"})
            if "以上信息仅供参考" not in answer:
                answer += "\n以上信息仅供参考，具体以业务确认为准。"

        # 6. PII 泄露检测
        if re.search(r'\d{18}|\d{17}[Xx]', answer):  # 身份证号
            issues.append({"type": "pii_leak", "severity": "key"})
        if re.search(r'1[3-9]\d{9}', answer):  # 完整手机号
            issues.append({"type": "pii_leak", "severity": "key"})

        key_issues = [i for i in issues if i["severity"] == "key"]
        passed = len(key_issues) == 0

        return ComplianceResult(
            passed=passed,
            corrected_answer=answer,
            issues=issues,
            need_handoff=len(key_issues) >= 2
        )
```

### 验收标准
- Tool 执行器正确并行调用多个 tool，缓存命中时跳过调用
- Tool 超时 3s 后返回 None，不阻塞其他 tool
- 合规检查器检出 12+ 违禁词，通过正则排除合法用法
- 长尾加严规则生效（自动补充免责声明、拦截过度承诺）

---

## Phase 1 · 任务 5：链路 A 规则短路 + L1 域分类

### 目标
实现链路 A 的规则引擎和 L1 域分类器（Phase 1 用规则实现，不训练模型）。

### 前置依赖
任务 2（Skill 加载器），任务 4（Tool 执行器 + 合规检查器）

### 实现要点

**5.1 routing/rule_engine.py — 链路 A**

```python
class RuleEngine:
    """链路 A：基于规则的直接匹配，零 LLM 调用"""

    def __init__(self, rule_path: str, skill_loader: SkillLoader):
        self.rules = self._load_rules(rule_path)
        self.skill_loader = skill_loader

    def match(self, query: str, state: ConversationState) -> RuleMatchResult | None:
        """
        尝试规则匹配。命中返回 RuleMatchResult，未命中返回 None。
        Phase 1: 硬编码 Top-10 高频场景的匹配规则。
        后续: 从反馈数据自动沉淀规则。
        """
        query_normalized = query.strip().lower()

        for rule in self.rules:
            if self._check_rule(query_normalized, rule, state):
                skill = self.skill_loader.get_skill(rule["skill_id"])
                if skill is None:
                    continue
                return RuleMatchResult(
                    skill_id=rule["skill_id"],
                    skill=skill,
                    template_variant=self._determine_variant(skill, state),
                    tools_needed=list(skill.tools.get("required", [])),
                    confidence=1.0,  # 规则匹配置信度为 1
                    rule_id=rule["rule_id"]
                )
        return None

    def _check_rule(self, query: str, rule: dict, state: ConversationState) -> bool:
        """检查单条规则是否命中"""
        # 关键词全匹配
        if "keywords_all" in rule:
            if not all(kw in query for kw in rule["keywords_all"]):
                return False
        # 关键词任一匹配
        if "keywords_any" in rule:
            if not any(kw in query for kw in rule["keywords_any"]):
                return False
        # 排除词
        if "exclude" in rule:
            if any(kw in query for kw in rule["exclude"]):
                return False
        # 正则匹配
        if "pattern" in rule:
            if not re.search(rule["pattern"], query):
                return False
        return True

    def _determine_variant(self, skill: SkillDefinition, state: ConversationState) -> str:
        """根据 turn_in_skill 确定模板变体"""
        turn = state.intent.turn_in_skill
        variants = list(skill.templates.keys())
        if not variants:
            return "default"
        if turn <= 1:
            return variants[0]
        elif turn == 2 and len(variants) > 1:
            return variants[1]
        elif len(variants) > 2:
            return variants[-1]
        return variants[-1]
```

**5.2 rules/rule_engine.json — Phase 1 初始规则**

```json
[
  {
    "rule_id": "bill_query_v1",
    "skill_id": "outstanding_bill_query",
    "keywords_any": ["账单", "欠款", "欠多少", "还多少"],
    "exclude": ["还款成功", "已还清"]
  },
  {
    "rule_id": "repayment_date_v1",
    "skill_id": "repayment_due_date_query",
    "keywords_any": ["还款日", "什么时候还", "几号还"]
  },
  {
    "rule_id": "member_status_v1",
    "skill_id": "member_status_query",
    "keywords_any": ["会员", "会员状态", "我的会员"]
  }
]
```

（Phase 1 先写 10 条高频规则，后续从反馈数据自动沉淀。）

**5.3 routing/domain_classifier.py — L1 域分类**

Phase 1 用关键词规则实现，不训练模型：

```python
class DomainClassifier:
    """L1 域分类器 — Phase 1 基于关键词规则"""

    DOMAIN_KEYWORDS = {
        "会员问题": ["会员", "开通", "退会", "会员权益"],
        "额度问题": ["额度", "提额", "没有额度", "审批"],
        "还款问题": ["还款", "还钱", "账单", "欠款", "扣款", "逾期还款"],
        "贷款问题": ["贷款", "借款", "放款", "审批进度", "借钱"],
        "费用问题": ["费用", "手续费", "利息", "退款", "扣费"],
        "活动问题": ["活动", "优惠", "推荐", "营销", "广告"],
        "业务场景办理问题": ["结清证明", "征信", "合同", "发票", "销户"],
        "账户问题": ["账户", "注销", "冻结", "登录"],
        "逾期问题": ["逾期", "催收", "协商", "减免", "延期"],
        "优享卡问题": ["优享卡", "优享", "白金卡"],
    }

    def classify(self, query: str, state: ConversationState) -> str:
        """返回最匹配的域名。无匹配时返回上一轮的域（连续性偏好）。"""
        scores = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query)
            if score > 0:
                scores[domain] = score

        if scores:
            return max(scores, key=scores.get)
        # 无匹配时延续上一轮的域
        if state.intent.domain:
            return state.intent.domain
        return "还款问题"  # 默认域（占比最高）
```

### 验收标准
- "查询我的账单" → 链路 A 命中 `outstanding_bill_query`
- "我想协商还款" → 链路 A 未命中，进入 L1 分类器 → 返回"逾期问题"域
- L1 分类器对 10 个域的关键词覆盖完整

---

## Phase 1 · 任务 6：链路 B — Skill 路由 + Agent A/B

### 目标
实现系统主链路：LLM Skill Routing → Agent B 置信度审查 → Tool 执行 → Agent A 合规生成。

### 前置依赖
任务 1-5 全部完成

### 实现要点

**6.1 routing/skill_router.py — LLM Skill Routing**

```python
class SkillRouter:
    """链路 B 核心：用 LLM 从域内候选 skill 中匹配最合适的"""

    def __init__(self, llm_client, skill_loader: SkillLoader, prompt_path: str):
        self.llm = llm_client
        self.skill_loader = skill_loader
        self.prompt_template = self._load_prompt(prompt_path)

    async def route(self, query: str, domain: str,
                    state: ConversationState,
                    sliding_window_text: str,
                    summary: str) -> SkillMatch:
        """
        调用 LLM 从域内 skill 候选中选择最匹配的。
        返回 SkillMatch（含 skill_id, confidence, template_variant 等）
        """
        # 1. 加载域内 skill 候选
        candidates = self.skill_loader.get_skills_by_domain(domain)
        if not candidates:
            return SkillMatch(skill_id="none", confidence=0.0)

        # 2. 格式化 skill 候选为 prompt 文本
        candidate_text = self._format_candidates(candidates)

        # 3. 构建完整 prompt
        prompt = self.prompt_template.format(
            candidate_skills=candidate_text,
            sliding_window=sliding_window_text,
            summary=summary or "无历史摘要",
            current_skill_id=state.intent.current_skill_id or "无",
            turn_in_skill=state.intent.turn_in_skill,
            collected_slots=json.dumps(state.slots, ensure_ascii=False) if state.slots else "无",
            risk_flags=", ".join(state.risk_flags) if state.risk_flags else "无"
        )

        # 4. 调用 LLM
        response = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # 低温度提高确定性
            response_format={"type": "json_object"}
        )

        # 5. 解析 LLM 输出
        return self._parse_response(response, candidates)

    def _format_candidates(self, candidates: list[SkillDefinition]) -> str:
        """将 skill 候选格式化为 LLM 可读的文本"""
        lines = []
        for sk in candidates:
            examples = "；".join(sk.triggers.examples[:3]) if sk.triggers.examples else "无"
            templates = ", ".join(sk.templates.keys()) if sk.templates else "无"
            tools = ", ".join(sk.tools.get("required", [])) if sk.tools else "无"
            lines.append(
                f"- **{sk.skill_id}**({sk.name}): {sk.description}\n"
                f"  示例: {examples}\n"
                f"  模板变体: {templates}\n"
                f"  工具: {tools}"
            )
        return "\n".join(lines)

    def _parse_response(self, raw: str, candidates: list) -> SkillMatch:
        """解析 LLM JSON 输出，带容错"""
        try:
            data = json.loads(raw)
            skill_id = data.get("skill_id", "none")
            # 校验 skill_id 在候选集中
            valid_ids = {c.skill_id for c in candidates} | {"none"}
            if skill_id not in valid_ids:
                skill_id = "none"
            return SkillMatch(
                skill_id=skill_id,
                template_variant=data.get("template_variant", "first_contact"),
                confidence=float(data.get("confidence", 0.0)),
                tools_needed=data.get("tools_needed", []),
                extracted_slots=data.get("extracted_slots", {}),
                reasoning=data.get("reasoning", "")
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return SkillMatch(skill_id="none", confidence=0.0)
```

**6.2 agents/confidence_auditor.py — Agent B**

```python
class ConfidenceAuditor:
    """Agent B: 纯规则置信度审查，<10ms"""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def audit(self, skill_match: SkillMatch, skill: SkillDefinition | None,
              state: ConversationState, l1_domain: str,
              tool_results: dict) -> ConfidenceAuditResult:
        score = 1.0
        reasons = []

        # 1. Skill 匹配置信度
        if skill_match.confidence < 0.7:
            score -= 0.3
            reasons.append(f"low_confidence({skill_match.confidence:.2f})")

        # 2. 域一致性
        if skill and skill.domain != l1_domain:
            score -= 0.4
            reasons.append(f"domain_mismatch({skill.domain} vs {l1_domain})")

        # 3. 模板槽位完整性
        if skill and skill_match.template_variant in skill.templates:
            tpl = skill.templates[skill_match.template_variant]
            if tpl.required_slots:
                available = set(state.slots.keys()) | set(tool_results.keys())
                missing = set(tpl.required_slots) - available
                if missing:
                    score -= 0.2 * len(missing)
                    reasons.append(f"missing_slots({missing})")

        # 4. 递进状态匹配
        variants = list(skill.templates.keys()) if skill else []
        if variants and skill_match.template_variant not in variants:
            score -= 0.2
            reasons.append("variant_not_in_skill")

        # 5. Tool 执行失败
        if skill:
            required_tools = skill.tools.get("required", [])
            for t in required_tools:
                if tool_results.get(t) is None:
                    score -= 0.5
                    reasons.append(f"tool_failed({t})")

        # 6. 关键词交叉（待实现：需要 query 参数）
        # 7. RAG 交叉验证（Phase 2）

        score = max(0.0, min(1.0, score))
        passed = score >= self.threshold

        fallback_type = ""
        if not passed:
            fallback_type = "handoff" if score < 0.2 else "safe_reply"

        return ConfidenceAuditResult(
            score=score, passed=passed,
            reasons=reasons, fallback_type=fallback_type
        )
```

**6.3 agents/compliant_generator.py — Agent A**

```python
class CompliantGenerator:
    """Agent A: 合规生成 — prompt 内嵌合规约束"""

    def __init__(self, llm_client, prompt_path: str):
        self.llm = llm_client
        self.prompt_template = self._load_prompt(prompt_path)

    async def generate(self, skill: SkillDefinition, template_variant: str,
                       tool_results: dict, state: ConversationState,
                       recent_turns_text: str, summary: str) -> dict:
        """
        基于 skill 模板 + tool 数据 + 合规约束生成话术。
        返回 {"answer": str, "next_step_hint": str}
        """
        # 获取模板
        tpl = skill.templates.get(template_variant)
        script = tpl.script if tpl else skill.fallback.get("answer", "")
        next_step = tpl.next_step if tpl else ""

        # 尝试 Jinja2 直接填充（如果 slots 完整，可跳过 LLM）
        filled = self._try_template_fill(script, state.slots, tool_results)
        if filled and not self._has_unfilled_slots(filled):
            # 模板完全填充，不需要 LLM
            return {"answer": filled, "next_step_hint": next_step}

        # 需要 LLM 辅助生成
        forbidden = ", ".join(skill.compliance.forbidden_expressions) \
                    if skill.compliance.forbidden_expressions else "无"
        disclaimer = skill.compliance.required_disclaimer or "无"

        prompt = self.prompt_template.format(
            skill_name=f"{skill.name}（{skill.skill_id}）",
            template_script=script,
            tool_results=json.dumps(tool_results, ensure_ascii=False, default=str),
            conversation_summary=f"{summary}\n\n最近对话:\n{recent_turns_text}",
            forbidden=forbidden,
            required_disclaimer=disclaimer
        )

        response = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        return self._parse_response(response, next_step)

    def _try_template_fill(self, script: str, slots: dict, tool_results: dict) -> str | None:
        """尝试用 Jinja2 填充模板"""
        try:
            from jinja2 import Template
            # 合并所有数据源
            data = {}
            data.update(slots)
            for tool_name, result in tool_results.items():
                if isinstance(result, dict):
                    data.update(result)
            # 将 {slot} 转为 Jinja2 {{ slot }}
            jinja_script = re.sub(r'\{(\w+)\}', r'{{ \1 }}', script)
            template = Template(jinja_script)
            return template.render(**data)
        except Exception:
            return None

    def _has_unfilled_slots(self, text: str) -> bool:
        """检查是否还有未填充的槽位"""
        return bool(re.search(r'\{\{.*?\}\}|\{[a-z_]+\}', text))
```

### 验收标准
- Skill Routing 对"我想协商逾期还款" → 返回 `overdue_negotiation`, confidence > 0.7
- Skill Routing 对"今天天气怎么样" → 返回 `none`, confidence < 0.3
- Agent B 对域不一致的匹配结果正确扣分 -0.4
- Agent B 对 required tool 失败的结果扣分 -0.5 并返回 fallback
- Agent A 对 slots 完整的 tool_only 场景直接填充模板，不调用 LLM
- Agent A 对需要 LLM 的场景输出包含免责声明

---

## Phase 1 · 任务 7：主编排器 + API 入口

### 目标
实现 Orchestrator，将三条链路（A/B/C fallback）编排为统一的请求处理流程，并提供 FastAPI + CLI 入口。

### 前置依赖
任务 1-6 全部完成

### 实现要点

**7.1 orchestrator.py — 主编排器**

这是整个系统的核心调度文件。相比 v1 的 1281 行 orchestrator，v2 目标控制在 200 行以内，逻辑清晰分层。

```python
class Orchestrator:
    """三条链路的统一编排器"""

    def __init__(self, context_mgr, rule_engine, domain_classifier,
                 skill_router, skill_loader, tool_executor,
                 confidence_auditor, compliant_generator,
                 compliance_checker, sliding_window):
        self.ctx = context_mgr
        self.rules = rule_engine
        self.classifier = domain_classifier
        self.router = skill_router
        self.skills = skill_loader
        self.tools = tool_executor
        self.auditor = confidence_auditor
        self.generator = compliant_generator
        self.compliance = compliance_checker
        self.window = sliding_window

    async def handle_turn(self, session_id: str, user_query: str,
                          channel: str = "online") -> CopilotResponse:
        trace_id = generate_trace_id()
        state = self.ctx.get_or_create(session_id)

        # ===== L0: 输入预处理 =====
        query = self._preprocess(user_query)
        self.ctx.process_turn_start(state, query)

        # ===== 链路 A: 规则短路尝试 =====
        rule_match = self.rules.match(query, state)
        if rule_match:
            return await self._execute_route_a(state, query, rule_match, trace_id)

        # ===== L1: 域分类 =====
        domain = self.classifier.classify(query, state)

        # ===== 链路 B: LLM Skill Routing =====
        window_text = self.window.format_for_prompt(state)
        skill_match = await self.router.route(
            query, domain, state, window_text, state.summary
        )

        # 无匹配 → Phase 1 直接返回 fallback（Phase 2 走链路 C）
        if skill_match.skill_id == "none" or skill_match.confidence < 0.3:
            return self._build_fallback(state, query, trace_id,
                                        route="route_c_fallback")

        # 加载 Skill 定义
        skill = self.skills.get_skill(skill_match.skill_id)
        if skill is None:
            return self._build_fallback(state, query, trace_id,
                                        route="route_b_skill_not_found")

        # ===== 并行: Tool 执行 + Agent B 审查 =====
        tools_needed = skill_match.tools_needed or list(skill.tools.get("required", []))
        tool_results, audit_result = await asyncio.gather(
            self.tools.execute(tools_needed, state),
            asyncio.coroutine(lambda: self.auditor.audit(
                skill_match, skill, state, domain, {}
            ))()  # Agent B 是同步的，wrap 为协程
        )

        # Agent B 先拿到 tool 结果后再做槽位完整性检查
        # (上面并行时 tool_results 还没到，这里补充检查)
        audit_result = self.auditor.audit(
            skill_match, skill, state, domain, tool_results
        )

        if not audit_result.passed:
            fallback = skill.fallback.get("answer", "")
            resp = CopilotResponse(
                output_type="fallback",
                answer=fallback or "您的问题我需要进一步了解，请稍候。",
                route="route_b_audit_failed",
                confidence=audit_result.score,
                trace_id=trace_id
            )
            self._finalize_turn(state, query, resp.answer, skill_match, [])
            return resp

        # ===== Agent A: 合规生成 =====
        recent_text = self.window.format_for_prompt(state, n_turns=3)
        gen_result = await self.generator.generate(
            skill, skill_match.template_variant,
            tool_results, state, recent_text, state.summary
        )

        # ===== 后置规则合规 =====
        comp_result = self.compliance.check(
            gen_result["answer"], state, skill, is_longtail=False
        )

        if not comp_result.passed and comp_result.need_handoff:
            resp = CopilotResponse(
                output_type="handoff",
                answer="该问题需要转接专员处理。",
                route="route_b_compliance_handoff",
                trace_id=trace_id
            )
        else:
            resp = CopilotResponse(
                output_type="bot_reply",
                answer=comp_result.corrected_answer,
                next_step_hint=gen_result.get("next_step_hint", ""),
                matched_skill_id=skill_match.skill_id,
                matched_skill_name=skill.name,
                confidence=skill_match.confidence,
                route="route_b",
                tools_called=list(tool_results.keys()),
                compliance_passed=comp_result.passed,
                trace_id=trace_id
            )

        self._finalize_turn(state, query, resp.answer, skill_match,
                           list(tool_results.keys()))
        return resp

    async def _execute_route_a(self, state, query, rule_match, trace_id):
        """链路 A: 规则短路执行"""
        skill = rule_match.skill
        tools_needed = rule_match.tools_needed

        # Tool 执行
        tool_results = await self.tools.execute(tools_needed, state)

        # 模板填充（Jinja2，零 LLM）
        gen_result = await self.generator.generate(
            skill, rule_match.template_variant,
            tool_results, state, "", ""
        )

        # 后置合规
        comp_result = self.compliance.check(
            gen_result["answer"], state, skill, is_longtail=False
        )

        resp = CopilotResponse(
            output_type="bot_reply",
            answer=comp_result.corrected_answer,
            next_step_hint=gen_result.get("next_step_hint", ""),
            matched_skill_id=rule_match.skill_id,
            matched_skill_name=skill.name,
            confidence=1.0,
            route="route_a",
            tools_called=list(tool_results.keys()),
            compliance_passed=comp_result.passed,
            trace_id=trace_id
        )

        self._finalize_turn(state, query, resp.answer, rule_match,
                           list(tool_results.keys()))
        return resp

    def _build_fallback(self, state, query, trace_id, route):
        """构建 fallback 响应"""
        return CopilotResponse(
            output_type="fallback",
            answer="您的问题我需要进一步了解，请稍候为您转接专员处理。",
            warning="⚠️ 该回答无SOP覆盖，请坐席核实后使用",
            route=route,
            trace_id=trace_id
        )

    def _preprocess(self, query: str) -> str:
        """L0 输入预处理"""
        # Phase 1: 基础归一化
        query = query.strip()
        query = re.sub(r'\s+', ' ', query)
        return query

    def _finalize_turn(self, state, query, answer, skill_match, tools_called):
        """轮次结束：更新上下文"""
        self.ctx.process_turn_end(state, query, answer, skill_match, tools_called)
```

**7.2 routers/gateway.py — FastAPI 入口**

```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str
    user_text: str
    channel: str = "online"
    customer_id: str = ""

@router.post("/api/chat")
async def chat(req: ChatRequest):
    orchestrator = get_orchestrator()
    response = await orchestrator.handle_turn(
        session_id=req.session_id,
        user_query=req.user_text,
        channel=req.channel
    )
    return response.model_dump()
```

**7.3 cli_demo.py — CLI 入口**

从 v1 的 `cli_demo.py` 简化迁移，核心改动：
- 调用 `orchestrator.handle_turn()` 替代 v1 的 `Gateway.chat()`
- 打印 `route` 字段显示走了哪条链路
- 打印 `matched_skill_id` 和 `confidence`

### 验收标准
- "查询我的账单" → 链路 A 命中 → 返回话术，route="route_a"
- "我想协商逾期还款" → 链路 B → Skill Routing → Agent B 通过 → Agent A 生成，route="route_b"
- "今天天气怎么样" → 无匹配 → fallback，route="route_c_fallback"
- 全链路 trace_id 贯穿
- CLI demo 可交互式多轮对话

---

## Phase 1 · 任务 8：Prompt 模板文件 + 离线评测

### 目标
编写三条链路的 prompt 模板文件，并基于 test.jsonl 进行离线评测。

### 前置依赖
任务 7（主编排器可运行）

### 实现要点

**8.1 skills/prompts/skill_routing.md**

```markdown
你是金融客服坐席辅助系统的场景匹配引擎。

## 任务
根据客户对话内容，从候选场景列表中选择最匹配的场景。如果没有合适的场景，选择 "none"。

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
严格输出 JSON，不要解释：
{"skill_id": "场景ID或none", "template_variant": "模板变体名", "confidence": 0.0-1.0, "tools_needed": [], "extracted_slots": {}, "reasoning": "一句话理由"}

同时从对话中提取以下信息（如有）：
- customer_request: 客户核心诉求
- overdue_reason: 逾期原因（如适用）
- repayment_ability: 客户自述还款能力（如适用）
将提取结果放入 extracted_slots 字段。
```

**8.2 skills/prompts/compliant_gen.md**

```markdown
你是金融客服坐席助手。请根据以下信息生成合规话术，直接输出可发送给客户的文字。

## 匹配场景
{skill_name}

## 标准话术模板
{template_script}

## 工具查询结果
{tool_results}

## 客户上下文
{conversation_summary}

## 合规红线（绝对禁止使用以下表达）
{forbidden}

## 必须包含的内容
{required_disclaimer}

## 要求
1. 基于标准话术模板，用工具查询结果中的真实数据替换模板中的槽位
2. 语气专业友善，不要编造任何业务数据
3. 不要使用合规红线中的任何表达
4. 必须包含"必须包含的内容"中要求的文字
5. 直接输出话术文字，不要解释

输出 JSON：{"answer": "话术内容", "next_step_hint": "建议下一步操作"}
```

**8.3 skills/prompts/longtail_reasoning.md（Phase 2 使用，Phase 1 先创建占位）**

```markdown
你是金融客服坐席助手。当前问题未匹配到标准SOP场景，请基于自身理解生成回答。

## 客户对话上下文
{sliding_window}

## 历史摘要
{summary}

## 客户信息
{customer_info}

## 已收集信息
{collected_slots}

## 工具查询结果
{tool_results}

## SOP 参考片段（仅供参考，不必照搬）
{rag_references}

## 安全约束
- 仅允许查询类建议，不做任何承诺
- 禁止输出具体金额/利率/减免方案
- 禁止说"我可以帮你操作"，只能说"建议您..."
- 如信息不足以回答，请直接说明并建议转人工
- 必须附加：以上信息仅供参考，具体以业务确认为准

输出 JSON：{"answer": "回答内容", "next_step_hint": "建议下一步", "confidence": 0.0-1.0}
```

**8.4 skills/references/compliance/forbidden_words.json**

从 v1 的 `compliance_gate.py` 迁移：

```json
{
  "words": [
    {"word": "保证", "exclude_patterns": ["保证金", "无法保证"]},
    {"word": "承诺", "exclude_patterns": []},
    {"word": "绝对", "exclude_patterns": ["绝对值"]},
    {"word": "肯定能", "exclude_patterns": []},
    {"word": "一定可以", "exclude_patterns": []},
    {"word": "没有问题", "exclude_patterns": []},
    {"word": "百分之百", "exclude_patterns": []},
    {"word": "包你满意", "exclude_patterns": []},
    {"word": "马上就好", "exclude_patterns": []},
    {"word": "立刻解决", "exclude_patterns": []},
    {"word": "我做主", "exclude_patterns": []},
    {"word": "私下处理", "exclude_patterns": []}
  ]
}
```

**8.5 离线评测脚本**

```python
# tests/eval_offline.py
"""
基于 test.jsonl 的离线评测：
1. 逐条读取 test.jsonl
2. 从 完整对话_清洗后 中提取每轮客户发言
3. 调用 orchestrator.handle_turn()
4. 记录：skill_id 匹配结果、route 类型、时延、合规检查结果
5. 输出评测报告：
   - Skill 匹配 TOP1 准确率（需人工标注 ground truth）
   - 链路分布（A/B/C 比例）
   - 平均时延 / P95 时延
   - 合规通过率
"""
```

### 验收标准
- 3 个 prompt 文件存在且格式正确
- forbidden_words.json 包含 12 个违禁词及排除模式
- 离线评测脚本可运行，输出评测报告
- Skill 匹配 TOP1 准确率 >= 80%（基于人工评估抽样）

---

## Phase 2 概要：上线试点（1-2 个月）

Phase 2 在 Phase 1 验证通过后启动，核心增量：

| 任务 | 说明 |
|------|------|
| **编写剩余 31 个 Skill YAML** | 补全至 51 个 Skill 全覆盖 |
| **训练 L1 分类器** | 基于 raw_data.csv 训练 distilbert/TextCNN，替代关键词规则 |
| **实现链路 C 完整链路** | `agents/longtail_reasoner.py` + 轻量 RAG 辅助（Milvus Top-3） |
| **实现反馈采集模块** | `scripts/feedback_collector.py`，隐式 accept/modify/reject |
| **迁移推理引擎** | Ollama → vLLM + INT4 量化，目标单次推理 200-500ms |
| **Session 持久化** | 内存 dict → Redis，支持多实例 + 重启恢复 |
| **Jinja2 模板引擎化** | 替代 v1 的 25+ 个硬编码 _build_*_response 方法 |
| **灰度验证** | 50 名坐席 × 2 周 A/B test |

## Phase 3 概要：中期演进（3-6 个月）

| 方向 | 说明 |
|------|------|
| **自演进闭环** | 长尾自动沉淀新 Skill；高频 Skill 自动晋升规则；规则自动过期降级 |
| **运营后台** | Skill/规则/合规规范的可视化编辑工具 |
| **Skill 分支条件** | 高合规场景实现节点级精确控制 |
| **推理加速** | TensorRT-LLM + speculative decoding + prefix caching |
| **质检一体化** | 合规能力扩展到全对话实时质检 |
| **全场景覆盖** | 链路 A+B 覆盖 >= 95% 流量 |

---

## 实施建议

### 执行顺序

```
任务 1（脚手架+模型）→ 任务 2（Skill编写）→ 任务 3（上下文管理）
                                              ↓
                     任务 4（Tool+合规）  ← 可与任务3并行
                                              ↓
                     任务 5（规则引擎+L1）← 依赖任务2+4
                                              ↓
                     任务 6（链路B核心）← 依赖全部
                                              ↓
                     任务 7（编排器+API）← 依赖全部
                                              ↓
                     任务 8（Prompt+评测）← 依赖全部
```

### 可并行的任务对

- **任务 2（Skill 编写）** 和 **任务 3（上下文管理）** 完全独立，可并行
- **任务 4（Tool+合规）** 和 **任务 2** 可并行（Tool 复用 v1，不依赖 Skill）
- **任务 5 和 6** 有依赖，需串行

### 关键风险缓解

| 风险 | 缓解 |
|------|------|
| Skill YAML 编写耗时超预期 | 先写 10 个核心场景跑通链路，剩余 10 个后续补 |
| LLM Skill Routing 精度不够 | 调整 prompt、增加 few-shot examples、缩小候选集 |
| 7B 模型无法可靠输出 JSON | 添加 response_format=json_object 约束 + 重试逻辑 |
| v1 tool handler 迁移不兼容 | 保持 handler 签名不变，仅改执行器 |
