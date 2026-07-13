# Minimal Viable Agent — From Scratch

> 2026 年 Agent 技术笔试题 · Vibe Coding 部分
> 一个用 Python 实现的最小可用 Agent Runtime：ReAct Loop + 工具注册 + Session 隔离 + Context 压缩 + Trace 日志

---

## 🎯 项目目标

从零实现一个 Agent Runtime，**不依赖 LangGraph / OpenHands / OpenClaw** 等现有框架。
核心要素：

| 要素 | 实现 |
|------|------|
| ReAct Loop | `agent/runtime.py` 中的显式状态机 |
| 工具注册机制 | `agent/tools.py` 中的 `Tool` 基类 + `ToolRegistry` + `@register_tool` |
| 3 个工具 | calculator / search (mock) / todo |
| LLM 输出解析 | `agent/parser.py` 解析 Anthropic 格式 + XML fallback |
| Session 隔离 | `agent/session.py` 每个 session 一个 JSON 文件 |
| Context 管理 | `agent/context.py` 滑动窗口 + 简单压缩 |
| Trace / 日志 | `agent/trace.py` 结构化事件流 |
| CLI 入口 | `main.py` |

---

## 🚀 运行方式

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

只依赖两个包：
- `anthropic` —— MiniMax 提供 Anthropic 兼容的 API（`https://api.minimaxi.com/anthropic`）
- `pytest` —— 测试

### 2. 配置 API Key

**推荐：用 `.env` 文件**

```bash
cp .env.example .env
# 编辑 .env，填入你的真实 API key
python3 main.py
```

**或者用环境变量**

```bash
export ANTHROPIC_API_KEY="sk-..."
# 可选：自定义 base URL（默认已设为 MiniMax 端点）
export ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"
# 可选：覆盖模型（默认 MiniMax-M3）
export AGENT_MODEL="MiniMax-M3"
```

或者用脚本：
```bash
chmod +x run.sh
./run.sh
```

### 🔒 安全检查

提交前跑一下密钥扫描：

```bash
python3 scripts/check_secrets.py
```

如果扫到真实 key，脚本会报错并指出文件 + 行号。
支持的检测模式：OpenAI/MiniMax/Anthropic/OpenRouter/GitHub/AWS/Google/Slack token + 硬编码密码。

### 3. 启动 CLI

```bash
python3 main.py
```

会创建一个新的 session，进入交互模式。

### 4. 列出 / 恢复 session

```bash
python3 main.py --list              # 列出所有 session
python3 main.py --resume <session_id>  # 恢复某个 session
python3 main.py --trace             # 开启详细 trace
```

### 5. CLI 内置命令

| 命令 | 作用 |
|------|------|
| `/new` | 保存当前 session，开新 session |
| `/list` | 列出所有 session |
| `/switch <id>` | 切换到另一个 session |
| `/state` | 显示当前 context 状态 |
| `/trace on/off` | 切换详细 trace |
| `/compress` | 手动触发 context 压缩 |
| `/help` | 显示帮助 |
| `/quit` | 保存并退出 |

---

## 🧪 测试

```bash
python3 -m pytest tests/ -v
```

**41 个测试全部通过**，覆盖：

- `tests/test_calculator.py` —— 5 个 calculator 测试（正确计算、除零、安全拒绝）
- `tests/test_search.py` —— 3 个 search 测试（关键词匹配、fallback、结果数量）
- `tests/test_todo.py` —— 6 个 todo 测试（增删改查、错误处理）
- `tests/test_registry.py` —— 5 个 registry 测试（注册、查重、schema 格式）
- `tests/test_session_context.py` —— 6 个 session/context 测试（持久化、隔离、压缩）
- `tests/test_parser.py` —— 8 个 parser 测试（原生格式 + 3 种 XML fallback）
- `tests/test_runtime.py` —— 6 个 runtime 测试（用 mock LLM 测整个状态机）

---

## 🏗️ 系统设计

### 架构图

```
                       ┌──────────────────────────────┐
                       │           CLI (main.py)       │
                       └──────────────┬───────────────┘
                                      │ 用户输入
                                      ▼
                       ┌──────────────────────────────┐
                       │       AgentRuntime           │
                       │  (agent/runtime.py)          │
                       │                              │
                       │  State: IDLE                 │
                       │      ↓                       │
                       │  RECEIVED (用户输入已收)       │
                       │      ↓                       │
                       │  REASONING (调用 LLM)         │
                       │      ↓                       │
                       │  ┌─→ TOOL_CALLING            │
                       │  │     ↓                     │
                       │  │   TOOL_COMPLETED           │
                       │  │     ↓                     │
                       │  └──┘ (循环)                  │
                       │      ↓                       │
                       │  RESPONDING → DONE → IDLE    │
                       └────┬─────────┬───────────────┘
                            │         │
              调用 LLM       │         │ 派发工具
                            ▼         ▼
                  ┌──────────────┐  ┌────────────────────┐
                  │   LLM Client │  │   Tool Registry    │
                  │ (agent/llm)  │  │ (agent/tools.py)   │
                  │              │  │  + 3 个具体工具     │
                  │ MiniMax-M3   │  │  - calculator      │
                  │ (Anthropic   │  │  - search (mock)   │
                  │  兼容端点)    │  │  - todo            │
                  └──────┬───────┘  └────────┬───────────┘
                         │                   │
                         └─────────┬─────────┘
                                   ▼
                       ┌──────────────────────────┐
                       │       Context            │
                       │ (agent/context.py)       │
                       │  - messages 列表          │
                       │  - 自动压缩（>100K 字符） │
                       │  - 保留 user/tool_result  │
                       └────────────┬─────────────┘
                                    ▼
                       ┌──────────────────────────┐
                       │       Session            │
                       │ (agent/session.py)       │
                       │  ~/.agent_sessions/      │
                       │  session_xxxx.json       │
                       └──────────────────────────┘
```

### 核心数据流（一次 ReAct turn）

```
用户输入 "帮我算一下 25*4+10"
   ↓
Session 加载（或新建）→ Context.append(user_msg)
   ↓
Loop:
  ┌─→ AgentRuntime.run_turn()
  │     ↓
  │   llm.chat(messages=context.messages, tools=registry.schemas())
  │     ↓
  │   返回 {"stop_reason": "tool_use", "content": [{...}, {tool_use: calculator, expression: "25*4+10"}]}
  │     ↓
  │   Parser 解析 → tool_calls = [{name: "calculator", input: {expression: "25*4+10"}}]
  │     ↓
  │   执行 calculator → output: "110"
  │     ↓
  │   Context.append(user_msg_with_tool_result)
  │     ↓
  │   再次调 LLM
  │     ↓
  │   返回 {"stop_reason": "end_turn", "content": [{text: "结果是 110"}]}
  │     ↓
  │   解析 → final_text = "结果是 110"
  │     ↓
  │   返回给 CLI → 打印给用户
  ↓
Session.save()
```

---

## 🧠 Memory 召回时机与放置方式

### 三层 Memory 设计

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Working Memory (短期)                              │
│  - 存储: 当前 session 的 messages 列表                        │
│  - 召回时机: 每次 ReAct turn 开始时，整块塞给 LLM               │
│  - 放置位置: agent/runtime.py 的 self.context.messages      │
│  - 生命周期: 跟随 session 文件                                │
└─────────────────────────────────────────────────────────────┘
                              ↓ 压缩
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Compressed Memory (中期)                           │
│  - 存储: 压缩后的 messages（assistant thinking 被截断）         │
│  - 召回时机: context 超过 max_chars=100K 时自动触发            │
│  - 触发点: Context.maybe_compress()                          │
│  - 压缩策略:                                                  │
│    * 永远保留 messages[0] (system)                            │
│    * 永远保留最后 keep_recent=10 条                          │
│    * 中间的 assistant 文本 > 100 字符 → 截断                  │
│    * 中间的 tool_result 内容 > 300 字符 → 截断               │
└─────────────────────────────────────────────────────────────┘
                              ↓ session 文件
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Persistent Memory (长期)                           │
│  - 存储: session JSON 文件（~/.agent_sessions/）             │
│  - 召回时机: 用户启动 CLI 并 --resume <session_id> 时          │
│  - 加载路径: SessionManager.load(session_id)                 │
│  - 持久化时机: 每个 turn 结束后调用 sm.save(session)          │
└─────────────────────────────────────────────────────────────┘
```

### Memory 召回时机表

| 时机 | 召回内容 | 代码位置 |
|------|---------|---------|
| 每个 turn 开始 | 当前 session 的全部 messages | `runtime.py:run_turn()` → `safe_chat(messages=self.context.messages)` |
| Context 超过 100K 字符 | 压缩后的 messages | `runtime.py:run_turn()` → `self.context.maybe_compress()` |
| 工具调用前 | 当前 session_id（用于 todo 等需要 session 维度的工具） | `runtime.py:_inject_session_id()` |
| CLI 启动 `--resume` | 之前保存的 session JSON 文件 | `session.py:SessionManager.load()` |
| 每个 turn 结束 | 保存当前 session | `main.py` → `sm.save(current)` |

### Memory 放置原则

**放进 context 的内容（必须）：**
- ✅ 用户输入（user role）
- ✅ 工具执行结果（user role + tool_result blocks 或纯文本）
- ✅ Assistant 的 tool_use 调用（必须紧跟 tool_result，否则 API 报错）

**可以截断的内容（压缩时）：**
- 🔻 Assistant 的纯文本回复（压缩成 `"[truncated]"`）
- 🔻 长 tool_result 内容（保留前 300 字符）
- 🔻 Assistant 的 thinking blocks

**不放进 context 的内容：**
- ❌ 系统提示词（用单独的 `system` 参数传给 API，不放在 messages 里）
- ❌ 工具注册信息（用 `tools` 参数单独传，不放在 messages 里）
- ❌ Trace 日志（独立存储，不参与 LLM 推理）

---

## 🛠️ 三个工具详解

### 1. `calculator`

执行简单数学表达式，**安全**版本（用 AST 白名单，不用 `eval()`）。

**Schema**:
```json
{
  "name": "calculator",
  "description": "Evaluate a math expression and return the numeric result. ...",
  "input_schema": {
    "type": "object",
    "properties": {
      "expression": {"type": "string", "description": "如 2+3*4"}
    },
    "required": ["expression"]
  }
}
```

**示例调用**:
- `calculator(expression="2+3*4")` → `"14"`
- `calculator(expression="(1+2)**3")` → `"27"`
- `calculator(expression="__import__('os')")` → `"Error: ..."`

### 2. `search`（Mock）

模拟搜索引擎，返回固定 mock 数据。

**支持的关键词**：weather / python / agent，其它关键词返回通用 placeholder。

### 3. `todo`

会话级的待办列表工具，支持 add / list / complete / remove 四个动作。

**关键设计**：todos 存在 `agent.tools.todo._store` 这个全局 dict 里，按 `session_id` 隔离。每个 session 有自己的待办列表。

---

## 🚧 已知限制 & 设计取舍

1. **工具调用依赖 LLM 主动调用**：M3 模型有时不会主动调用工具（会描述要做什么）。这是模型行为问题，runtime 层面无法完全避免。可以通过更严格的 system prompt 或换更强的模型缓解。

2. **XML Fallback Parser 是补丁**：当 LLM 用 XML 风格输出工具调用时，runtime 能识别并执行，但 tool_result 必须用纯文本回传。这是为了兼容 API 的限制。

3. **Session 存储是 JSON 文件**：单机 CLI 够用，但如果要分布式或高并发，需要换成 Redis/PostgreSQL。

4. **Context 压缩是字符级估算**：用 `len(string)` 粗略估计 token，没有集成 tiktoken。对于中文+英文混合的内容，1 token ≈ 4 字符是合理近似。

5. **没有并发处理**：CLI 是单线程的，不支持一个 session 内多任务并行。

---

## 📂 项目结构

```
code/
├── main.py                # CLI 入口
├── config.py              # API 配置
├── run.sh                 # 一键启动脚本
├── requirements.txt
├── README.md              # 本文档
├── PROMPTS_AND_NOTES.md   # AI Prompt 与问题解决记录
├── agent/
│   ├── __init__.py
│   ├── runtime.py         # ReAct Loop 状态机 ⭐
│   ├── llm.py             # LLM 客户端（Anthropic 兼容）
│   ├── parser.py          # 输出解析（含 XML fallback）⭐
│   ├── tools.py           # 工具基类 + Registry
│   ├── session.py         # Session 管理 + 持久化
│   ├── context.py         # Context 管理 + 压缩
│   └── trace.py           # Trace/日志
├── tools/
│   ├── __init__.py
│   ├── calculator.py      # 安全数学计算
│   ├── search.py          # Mock 搜索
│   └── todo.py            # 待办列表
└── tests/
    ├── __init__.py
    ├── test_calculator.py
    ├── test_search.py
    ├── test_todo.py
    ├── test_registry.py
    ├── test_session_context.py
    ├── test_parser.py
    └── test_runtime.py
```

---

## 📚 参考资料

- Anthropic Tool Use 文档：https://docs.anthropic.com/claude/docs/tool-use
- MiniMax API 文档（Anthropic 兼容）
- ReAct 论文：https://arxiv.org/abs/2210.03629

---

_本项目是 Agent 技术笔试题的完整答案。所有 41 个测试通过。_