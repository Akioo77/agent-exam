# Agent 技术笔试题 — 项目文档

> **应聘人：庄英琪**
> 状态：**✅ 已完成**（2026-07-14）
> 题目：从零实现最小可用 Agent（Vibe Coding）+ 5 道架构设计题
>
> 📺 **录屏**：[`RECORDING/vibecoding_demo.mov`](RECORDING/vibecoding_demo.mov)（103 MB）
> 📝 **面试题答案**：[`面试题答案.md`](面试题答案.md)
> 💻 **代码主目录**：[`code/`](code/)
> 🧪 **测试结果**：92 个测试全部通过

---

## 🎯 完成内容总览

### Part 1 · Vibe Coding（从零实现 Agent）

| 要素 | 实现 |
|------|------|
| ReAct Loop 状态机 | `code/agent/runtime.py`（7 个状态）|
| 工具注册机制 | `code/agent/tools.py`（@register_tool 装饰器 + 自动 Schema 推导）|
| 3 个工具 | calculator（安全 AST）/ search（mock）/ todo（session 隔离）|
| LLM 输出解析 | `code/agent/parser.py`（支持 7 种输出格式）|
| Session 隔离 | `code/agent/session.py`（文件持久化）|
| Context 压缩 | `code/agent/context.py`（三层记忆）|
| Trace 日志 | `code/agent/trace.py`（结构化事件）|
| CLI 入口 | `code/main.py`（支持 `--list` / `--resume`）|
| **M3 工具调用加固** | 自答检测 + retry + intent-aware prompt augmentation |

### Part 2 · 架构设计题（5 选 5，全部作答）

| 模块 | 题目 | 答案 |
|------|------|------|
| 一 | Context 压缩 | [`面试题答案.md`](面试题答案.md#模块一) |
| 二 | Memory 经典框架 | [`面试题答案.md`](面试题答案.md#模块二) |
| 三 | 长程任务目标保持 | [`面试题答案.md`](面试题答案.md#模块三) |
| 四 | 异步工具与通知 | [`面试题答案.md`](面试题答案.md#模块四) |
| 五 | Claude Code vs GLM 工具输出 | [`面试题答案.md`](面试题答案.md#模块五) |

---

## 📂 项目结构

```
agent-exam/
├── README.md                            # 本文档
├── 面试题答案.md                        # 面试题答案
├── RECORDING/
│   └── vibecoding_demo.mov              # 录屏文件（⚠️ 99 MB，超 GitHub 上限）
├── docs/
│   ├── 00-课程总览.md ~ 06-架构对比.md  # 学习笔记
└── code/                                # Vibe coding 产物
    ├── main.py                          # CLI 入口
    ├── config.py                        # 配置
    ├── requirements.txt
    ├── README.md                        # 代码详细说明
    ├── PROMPTS_AND_NOTES.md             # AI Prompt 与问题解决记录
    ├── record_demo.sh                   # 录屏演示脚本
    ├── run.sh
    ├── .env.example
    ├── .gitignore
    ├── scripts/check_secrets.py         # 密钥扫描器
    ├── agent/
    │   ├── runtime.py                   # ReAct Loop 状态机 ⭐
    │   ├── llm.py                       # LLM 客户端
    │   ├── parser.py                    # 输出解析（含 7 种 fallback）
    │   ├── tools.py                     # 工具基类 + Registry
    │   ├── session.py                   # Session 管理
    │   ├── context.py                   # Context 压缩
    │   └── trace.py                     # Trace 日志
    ├── tools/
    │   ├── calculator.py                # 安全数学计算
    │   ├── search.py                    # Mock 搜索
    │   └── todo.py                      # 待办列表
    └── tests/
        ├── test_calculator.py           # 5
        ├── test_search.py               # 3
        ├── test_todo.py                 # 6
        ├── test_registry.py             # 5
        ├── test_session_context.py      # 6
        ├── test_parser.py               # 13
        ├── test_runtime.py              # 6
        ├── test_robustness.py           # 19
        ├── test_cli_commands.py         # 12
        ├── test_check_secrets.py        # 8
        └── __init__.py
```

---

## 🛠️ 技术栈

| 维度 | 选型 | 理由 |
|------|------|------|
| **LLM** | MiniMax-M3（Anthropic 兼容 API）| 已订阅、零成本、1M 上下文 |
| **语言** | Python 3.9+ | 兼容性好、库齐 |
| **LLM SDK** | `anthropic` Python | MiniMax 提供 Anthropic 兼容端点 |
| **前端** | CLI（`main.py`）| 简单，聚焦核心逻辑 |
| **测试** | `pytest` | 92 个测试 |
| **持久化** | JSON 文件（`~/.agent_sessions/`）| 简化 |
| **录屏** | QuickTime Player（macOS） | 系统自带 |

---

## 📊 核心指标

| 指标 | 数值 |
|------|------|
| 测试总数 | **92**（100% 通过） |
| 核心代码行数 | ~2,064 行 |
| 文件数 | 40 |
| 工具调用格式支持 | **7 种** |
| M3 工具调用率 | **100%**（5/5 真实 LLM 测试） |
| 安全扫描 | ✓ clean（识别 11 种密钥格式） |

---

## 🚀 运行方式

```bash
# 1. 安装依赖
cd code/
pip install -r requirements.txt

# 2. 配置 API Key
export ANTHROPIC_API_KEY="sk-..."
export ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"

# 3. 跑测试
python3 -m pytest tests/

# 4. 启动 CLI
python3 main.py

# 5. 列出所有 session
python3 main.py --list

# 6. 恢复 session
python3 main.py --resume <session_id>
```

详细使用见 [`code/README.md`](code/README.md)。

---

## 📚 文档索引

| 文档 | 内容 |
|------|------|
| [`code/README.md`](code/README.md) | 代码详细说明、系统设计、Memory 召回时机 |
| [`code/PROMPTS_AND_NOTES.md`](code/PROMPTS_AND_NOTES.md) | AI Prompt 与问题解决记录 |
| [`面试题答案.md`](面试题答案.md) | 架构设计题答案（5 道全答）|
| [`docs/00-课程总览.md ~ 06-架构对比.md`](docs/) | 学习笔记（6 课）|

---

## 🔐 安全说明

- 仓库已用 `scripts/check_secrets.py` 扫描，**0 密钥泄漏**
- API key 仅在本地环境变量中设置，**未硬编码、未提交**
- `.env` 文件已在 `.gitignore` 中排除
- `.env.example` 只包含占位符

---

## 📦 提交清单

- [x] 代码链接（GitHub 仓库，待 push）
- [x] 终端录屏（`RECORDING/vibecoding_demo.mov`）
- [x] README（运行方式 + 系统设计 + memory 召回）
- [x] AI Prompt 与问题解决记录（`code/PROMPTS_AND_NOTES.md`）
- [x] 架构设计题答案（5 道全答）

---

_应聘人：**庄英琪** · 完成时间：2026-07-14_