# Agent 技术笔试题 — 项目文档

> 状态：**准备阶段**（2026-07-10）
> 目标：从零实现最小可用 Agent + 5 道架构设计题

---

## 🎯 项目目标

### Vibe Coding 部分
- **从零实现 Agent Runtime**（不依赖 langgraph / openhands / openclaw）
- 核心要素：ReAct 循环、工具注册、Session 隔离、Context 管理、Trace
- 3 个工具：calculator / search (mock) / todo（自选）
- 真实 LLM API（minimax M3）
- 录屏 + 测试用例 + README

### 架构设计部分
- 5 道题各 300-500 字
- **主人主答，我打磨**（题目说"用 AI 帮助思考，不是让 AI 完成任务"）

---

## 🛠️ 技术栈

| 维度 | 选型 | 理由 |
|------|------|------|
| **LLM** | minimax M3（OpenAI 兼容） | 已订阅、零成本、minimax |
| **语言** | Python 3.11+ | 库齐、协程简洁、主人最熟 |
| **LLM SDK** | `openai` Python | 兼容 minimax API |
| **测试** | `pytest` + `pytest-asyncio` | 业界标准 |
| **结构化** | `pydantic` | Schema、验证、序列化 |
| **Token 计数** | `tiktoken` | 上下文压缩 |
| **持久化** | JSON 文件 | 简化（不用数据库） |
| **录屏** | `asciinema` | 体积小、可读性高 |
| **依赖管理** | `uv` 或 `pip + venv` | 待定 |

---

## 📁 项目结构

```
agent-exam/
├── README.md                 # 本文档
├── docs/                     # 课程材料
│   ├── 00-课程总览.md
│   ├── 01-Agent-Runtime基础.md
│   ├── 02-Context-Engineering.md
│   ├── 03-Memory框架.md
│   ├── 04-Task-Management.md
│   ├── 05-Tool-Runtime.md
│   └── 06-架构对比.md
├── code/                     # Vibe coding 产物
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── runtime.py        # ReAct 循环核心
│   │   ├── session.py        # Session 管理
│   │   ├── context.py        # Context 管理 + 压缩
│   │   ├── tools/            # 工具实现
│   │   │   ├── base.py       # 工具基类
│   │   │   ├── calculator.py
│   │   │   ├── search.py
│   │   │   └── todo.py
│   │   ├── llm.py            # LLM 客户端
│   │   ├── parser.py         # 输出解析
│   │   └── trace.py          # Trace / 日志
│   ├── main.py               # 入口（CLI）
│   ├── prompts/              # Prompt 模板
│   └── tests/                # 测试
│       ├── test_tools.py
│       ├── test_session.py
│       ├── test_context.py
│       └── test_loop.py
├── notes/                    # 主人思考记录
│   └── 架构题草稿.md
└── RECORDING/                # 录屏产物
```

---

## 📅 规划时间表（待定 deadline）

| 阶段 | 内容 | 估时 |
|------|------|------|
| 1. 课程学习 | docs/ 全部看完 | 2-3 小时 |
| 2. 架构题 | 5 道主答 + 打磨 | 2-3 小时 |
| 3. 工具基类 + Schema | `tools/base.py` | 30 min |
| 4. LLM 客户端 | `llm.py` | 30 min |
| 5. 三个工具 | calculator/search/todo | 1 hour |
| 6. ReAct Loop | `runtime.py` | 2 hour |
| 7. Session 管理 | `session.py` | 1 hour |
| 8. Context 管理 | `context.py` | 1.5 hour |
| 9. Trace / 日志 | `trace.py` | 30 min |
| 10. CLI 入口 | `main.py` | 30 min |
| 11. 测试用例 | tests/ | 1.5 hour |
| 12. 录屏 | asciinema | 30 min |
| 13. README + 提交 | 文档 | 1 hour |

---

## 💎 主人相关资源

主人已有经验可借鉴：
- **Project 3**（外化工具）→ 模块三 Task 设计
- **FCP**（Future Child Posting）→ Session、Memory、Pipeline
- **HKUST education_report** → 写作风格、报告结构
- **OpenClaw / Claude Code 体感** → 模块五架构对比

---

## 📝 提交清单

- [ ] 代码链接（GitHub 仓库）
- [ ] 终端录屏（asciinema）
- [ ] README（运行方式 + 系统设计 + memory 召回）
- [ ] AI Prompt 记录
- [ ] 问题解决记录

---

_更新于 2026-07-10 19:47_
