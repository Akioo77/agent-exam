# Agent 技术笔试题 — 项目文档

> **应聘人：庄英琪**
> 状态：**✅ 已完成**（2026-07-14）
> 题目：从零实现最小可用 Agent（Vibe Coding）+ 5 道架构设计题
>
> 📺 **录屏**：[`vibecoding_demo.mov`](vibecoding_demo.mov)（99 MB，⚠️ 超 GitHub 50MB 上限）
> 📝 **面试题答案**：[`面试题答案.md`](面试题答案.md)
> 🧪 **测试结果**：92 个测试全部通过

---

## 🎯 项目目标

从零实现一个 Agent Runtime，**不依赖 LangGraph / OpenHands / OpenClaw** 等现有框架。

| 要素 | 实现 |
|------|------|
| ReAct Loop | `code/agent/runtime.py` 中的显式状态机（7 个状态）|
| 工具注册机制 | `code/agent/tools.py` 中的 `Tool` 基类 + `ToolRegistry` + `@register_tool` 装饰器 |
| 3 个工具 | calculator（安全 AST）/ search（mock）/ todo（session 隔离）|
| LLM 输出解析 | `code/agent/parser.py`（支持 7 种输出格式 + XML fallback）|
| Session 隔离 | `code/agent/session.py`（每个 session 一个 JSON 文件）|
| Context 压缩 | `code/agent/context.py`（三层记忆：短期滚动 → 中期压缩 → 长期持久化）|
| Trace 日志 | `code/agent/trace.py`（结构化事件流）|
| CLI 入口 | `code/main.py`（支持 `--list` / `--resume`）|
| **M3 工具调用加固** | 自答检测 + retry + intent-aware prompt augmentation |

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
                       │       AgentRuntime            │
                       │  (code/agent/runtime.py)     │
                       │  State: IDLE → RECEIVED       │
                       │       → REASONING            │
                       │       → TOOL_CALLING         │
                       │       → TOOL_COMPLETED       │
                       │       → RESPONDING → DONE    │
                       └────┬─────────┬───────────────┘
                            │         │
              调用 LLM       │         │ 派发工具
                            ▼         ▼
                  ┌──────────────┐  ┌────────────────────┐
                  │   LLM Client │  │   Tool Registry    │
                  │ (agent/llm)  │  │ (agent/tools.py)   │
                  │              │  │  + 3 个具体工具     │
                  │ MiniMax-M3   │  │  - calculator      │
                  └──────┬───────┘  └────────┬───────────┘
                         └─────────┬─────────┘
                                   ▼
                       ┌──────────────────────────┐
                       │       Context            │
                       │ (code/agent/context.py)  │
                       │  - messages 列表          │
                       │  - 自动压缩（>100K 字符） │
                       └────────────┬─────────────┘
                                    ▼
                       ┌──────────────────────────┐
                       │       Session            │
                       │ (code/agent/session.py) │
                       │  ~/.agent_sessions/     │
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
  │   Parser 解析 → tool_calls = [{name: "calculator", input: {expression: "25*4+10"}}]
  │     ↓
  │   执行 calculator → output: "110"
  │     ↓
  │   Context.append(user_msg_with_tool_result)
  │     ↓
  │   再次调 LLM → 返回最终文本 "结果是 110"
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
│  Layer 1: Working Memory (短期)                             │
│  - 存储: 当前 session 的 messages 列表                       │
│  - 召回时机: 每次 ReAct turn 开始时，整块塞给 LLM            │
│  - 生命周期: 跟随 session 文件                               │
└─────────────────────────────────────────────────────────────┘
                              ↓ 压缩触发（>100K 字符）
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Compressed Memory (中期)                          │
│  - 永远保留 messages[0] (system)                             │
│  - 永远保留最后 keep_recent=10 条                           │
│  - 中间 assistant 文本 > 100 字符 → 截断                    │
│  - 中间 tool_result > 300 字符 → 截断                       │
└─────────────────────────────────────────────────────────────┘
                              ↓ session 保存到磁盘
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Persistent Memory (长期)                          │
│  - 存储: session JSON 文件（~/.agent_sessions/）           │
│  - 召回时机: CLI 启动 --resume <session_id>                 │
└─────────────────────────────────────────────────────────────┘
```

### Memory 召回时机表

| 时机 | 召回内容 | 代码位置 |
|------|---------|---------|
| 每个 turn 开始 | 当前 session 的全部 messages | `runtime.py:run_turn()` |
| Context 超过 100K 字符 | 压缩后的 messages | `runtime.py:run_turn()` → `context.maybe_compress()` |
| 工具调用前 | 当前 session_id（用于 todo 等需要 session 维度的工具） | `runtime.py:_inject_session_id()` |
| CLI 启动 `--resume` | 之前保存的 session JSON | `session.py:SessionManager.load()` |
| 每个 turn 结束 | 保存当前 session | `main.py` → `sm.save(current)` |

### Memory 放置原则

**放进 context 的内容（必须）：**
- ✅ 用户输入（user role）
- ✅ 工具执行结果（user role + tool_result blocks 或纯文本）
- ✅ Assistant 的 tool_use 调用

**可以截断的内容（压缩时）：**
- 🔻 Assistant 的纯文本回复（→ `"[truncated]"`）
- 🔻 长 tool_result 内容（保留前 300 字符）
- 🔻 Assistant 的 thinking blocks

**不放进 context 的内容：**
- ❌ 系统提示词（用单独的 `system` 参数）
- ❌ 工具注册信息（用 `tools` 参数单独传）
- ❌ Trace 日志（独立存储，不参与推理）

---

## 🔧 三个工具详解

### 1. calculator — 安全数学计算

用 AST 白名单实现（不用 `eval()`），支持加减乘除幂运算，拒绝危险表达式。

```
calculator(expression="2+3*4")        → "14"
calculator(expression="(1+2)**3")     → "27"
calculator(expression="__import__...") → "Error: ..."
```

### 2. search — Mock 搜索引擎

模拟搜索，支持关键词：weather / python / agent，其它返回通用 placeholder。

### 3. todo — 会话级待办列表

按 `session_id` 隔离，每个 session 有独立的待办列表。

| 操作 | 示例 |
|------|------|
| 添加 | `todo(action="add", content="写作业")` |
| 列出 | `todo(action="list")` |
| 完成 | `todo(action="complete", todo_id="xxx")` |
| 删除 | `todo(action="remove", todo_id="xxx")` |

---

## 🚀 运行方式

### 1. 安装依赖

```bash
cd code/
pip install -r requirements.txt
```

只依赖两个包：`anthropic`（LLM SDK）+ `pytest`（测试）。

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API key
python3 main.py
```

**或者用环境变量：**
```bash
export ANTHROPIC_API_KEY="sk-..."
export ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"
export AGENT_MODEL="MiniMax-M3"   # 可选，默认 MiniMax-M3
```

**一键启动脚本：**
```bash
chmod +x run.sh && ./run.sh
```

### 3. 启动 CLI

```bash
python3 main.py              # 新建 session
python3 main.py --list       # 列出所有 session
python3 main.py --resume <id> # 恢复某个 session
python3 main.py --trace      # 开启详细 trace
```

### 4. CLI 内置命令

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

### 5. 安全检查

提交前跑密钥扫描（检测 11 种密钥格式）：

```bash
python3 scripts/check_secrets.py
```

---

## 🧪 测试

```bash
python3 -m pytest tests/ -v
```

**92 个测试，100% 通过：**

| 文件 | 数量 | 内容 |
|------|------|------|
| `test_calculator.py` | 5 | 正确计算、除零、安全拒绝 |
| `test_search.py` | 3 | 关键词匹配、fallback、结果数量 |
| `test_todo.py` | 6 | 增删改查、错误处理 |
| `test_registry.py` | 5 | 注册、查重、schema 格式 |
| `test_session_context.py` | 6 | 持久化、隔离、压缩 |
| `test_parser.py` | 13 | 原生格式 + XML fallback |
| `test_runtime.py` | 6 | mock LLM 测整个状态机 |
| `test_robustness.py` | 19 | M3 自答检测 + retry 加固 |
| `test_cli_commands.py` | 12 | CLI 内置命令 |
| `test_check_secrets.py` | 8 | 密钥扫描器 |

---

## 📊 核心指标

| 指标 | 数值 |
|------|------|
| 测试总数 | **92**（100% 通过） |
| 核心代码行数 | ~2,064 行 |
| 工具调用格式支持 | **7 种** |
| M3 工具调用率 | **100%**（5/5 真实 LLM 测试） |
| 安全扫描 | ✓ clean（识别 11 种密钥格式） |

---

## 🚧 已知限制 & 设计取舍

1. **M3 模型有时不主动调用工具**：会描述要做什么而非调用工具。可通过更严格的 system prompt 或换更强模型缓解。

2. **XML Fallback Parser 是补丁**：当 LLM 用 XML 风格输出工具调用时，runtime 能识别并执行，但 tool_result 须用纯文本回传。

3. **Session 存储是 JSON 文件**：单机 CLI 够用，分布式/高并发场景需换 Redis/PostgreSQL。

4. **Context 压缩是字符级估算**：用 `len(string)` 粗略估计 token，中英文混合场景 1 token ≈ 4 字符是合理近似。

5. **没有并发处理**：CLI 是单线程，不支持 session 内多任务并行。

---

## 📂 项目结构

```
agent-exam/
├── README.md                            # 本文档
├── 面试题答案.md                        # 5 道架构设计题答案
├── vibecoding_demo.mov                  # 录屏演示（99 MB）
├── code/                                # Vibe Coding 产物
│   ├── main.py                          # CLI 入口
│   ├── config.py                        # API 配置
│   ├── run.sh                           # 一键启动脚本
│   ├── requirements.txt
│   ├── PROMPTS_AND_NOTES.md             # AI Prompt 与问题解决记录
│   ├── scripts/check_secrets.py         # 密钥扫描器
│   ├── agent/
│   │   ├── runtime.py                   # ReAct Loop 状态机 ⭐
│   │   ├── llm.py                       # LLM 客户端（Anthropic 兼容）
│   │   ├── parser.py                    # 输出解析（含 XML fallback）⭐
│   │   ├── tools.py                     # 工具基类 + Registry
│   │   ├── session.py                   # Session 管理 + 持久化
│   │   ├── context.py                   # Context 管理 + 三层压缩
│   │   └── trace.py                     # Trace/日志
│   ├── tools/
│   │   ├── calculator.py                # 安全数学计算
│   │   ├── search.py                   # Mock 搜索
│   │   └── todo.py                     # 会话级待办列表
│   └── tests/                          # 92 个测试
│       ├── test_calculator.py
│       ├── test_search.py
│       ├── test_todo.py
│       ├── test_registry.py
│       ├── test_session_context.py
│       ├── test_parser.py
│       ├── test_runtime.py
│       ├── test_robustness.py
│       ├── test_cli_commands.py
│       └── test_check_secrets.py
```

---

## 🔐 安全说明

- 仓库已用 `scripts/check_secrets.py` 扫描，**0 密钥泄漏**
- API key 仅在本地环境变量中设置，**未硬编码、未提交**
- `.env` 文件已在 `.gitignore` 中排除
- `.env.example` 只包含占位符

---

## 📚 参考资料

- [Anthropic Tool Use 文档](https://docs.anthropic.com/claude/docs/tool-use)
- [ReAct 论文](https://arxiv.org/abs/2210.03629)

---

_应聘人：**庄英琪** · 完成时间：2026-07-14_
