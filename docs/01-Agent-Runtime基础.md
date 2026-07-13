# 01 - Agent Runtime 基础 ⭐⭐⭐

> **对应题目**：Vibe Coding 全部 / 模块四 Tool Runtime
> **核心问题**：ReAct 循环怎么写？工具怎么注册？Session 怎么隔离？Trace 怎么做？

---

## 1. 核心概念清单

| 概念 | 一句话解释 |
|------|-----------|
| **Agent** | 一个能"感知 → 思考 → 行动 → 观察"循环的 LLM 驱动系统 |
| **ReAct** | Reason + Act，LLM 边想边做，每步显式输出思考和动作 |
| **Tool** | Agent 可调用的函数，有 name / description / schema 三个要素 |
| **Schema** | 工具的参数定义，LLM 靠它知道怎么调（JSON Schema / Pydantic） |
| **Session** | 一个用户的一个对话窗口，独立 context、history、state |
| **Trace** | 工具调用 + LLM 思考的全链路日志，用于调试和审计 |
| **Parser** | 从 LLM 文本输出中提取 思考 / 工具调用 / 最终答案 |

---

## 2. ReAct 循环原理

**核心思想**：LLM 不直接给答案，而是**一步步推理 + 调用工具**。

```
用户输入 → LLM 思考 → 是否要调工具？
                          ↓
                       是 → 调工具 → 工具结果塞回 → 再 LLM 思考
                          ↓
                       否 → 返回最终答案
```

**单步结构**：
```python
# Pseudo
while not done:
    response = llm.chat(messages, tools_schema)
    if response.has_tool_call():
        result = execute_tool(response.tool_call)
        messages.append(tool_result_message(result))
    else:
        return response.content
```

**为什么需要"显式思考"**？
- 让 LLM 的决策过程**可追溯**（debug 友好）
- 让 LLM 能"自我纠错"（看到上一步结果再决定）
- 让用户能看到"AI 在想什么"（透明性）

---

## 3. 工具注册机制 ⭐（题目重点）

### 3.1 工具的三个核心要素

```python
class Tool(Protocol):
    name: str            # 工具名，LLM 用来调
    description: str     # 工具描述，LLM 用来决定"要不要调"
    schema: dict         # 参数 schema，LLM 用来填参数
    def run(self, **kwargs) -> str: ...
```

**name 和 description 的设计**（这是关键）：
- **name**：动词/动名词，`search_web` / `read_file` / `send_email`
- **description**：1-3 句话，说清"什么时候用、用完返回什么"
- **description 是 LLM 决策的唯一依据**——必须写好

### 3.2 Schema 驱动 LLM 决策

LLM 不需要"知道"工具的 Python 实现，只需要 schema：

```python
search_schema = {
    "name": "search_web",
    "description": "Search the web for current information. Use when you need recent facts.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
}
```

LLM 输出：
```json
{
  "tool": "search_web",
  "args": {"query": "weather in Tokyo", "max_results": 3}
}
```

### 3.3 工具注册器

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        self._tools[tool.name] = tool
    
    def get_schema(self) -> list[dict]:
        """返回所有工具的 schema，给 LLM 看"""
        return [t.to_schema() for t in self._tools.values()]
    
    def execute(self, name: str, args: dict) -> str:
        if name not in self._tools:
            raise ToolNotFound(name)
        return self._tools[name].run(**args)
```

---

## 4. LLM 输出解析

LLM 输出可能包含：
1. **思考过程**（"我需要先查天气..."）
2. **工具调用**（`{tool: "weather", args: {...}}`）
3. **最终答案**（"明天北京晴，25°C"）
4. **混合**：上面三种的组合

### 4.1 解析策略

**策略 A：原生 function calling**（OpenAI 兼容）
- LLM API 直接支持 `tools` 字段
- 返回结构化 `tool_calls`
- 优点：解析稳定、schema 强约束
- 缺点：和文本流割裂

**策略 B：文本流 + 解析器**（Anthropic 风格）
- LLM 在文本中输出 `<tool_use>...</tool_use>` XML
- 解析器正则提取
- 优点：自然、可读
- 缺点：解析复杂、依赖 prompt

**Vibe coding 建议**：用 minimax M3 的原生 function calling，**先跑通再考虑美化**。

### 4.2 解析器伪代码

```python
def parse_response(response) -> ParsedResponse:
    if response.tool_calls:
        # 原生 function calling
        return ParsedResponse(
            thinking=response.content,
            tool_calls=response.tool_calls,
            final_answer=None
        )
    else:
        return ParsedResponse(
            thinking=response.content,
            tool_calls=[],
            final_answer=response.content
        )
```

---

## 5. Session 隔离 ⭐（题目重点）

### 5.1 为什么要隔离？

题目场景：
- 用户 A 窗口 1：让 Agent 查天气记待办
- 用户 A 窗口 2：让 Agent 写周报记待办
- 两个窗口**不能互相干扰**

### 5.2 Session 的最小数据

```python
class Session:
    id: str                     # session id
    user_id: str                # 所属用户
    messages: list[Message]     # 对话历史
    state: dict                 # 业务状态（如待办列表）
    created_at: datetime
    updated_at: datetime
    metadata: dict              # 题目中可能是"窗口 1/2"
```

### 5.3 隔离设计

**进程内**：
```python
class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
    
    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(id=session_id, ...)
        return self._sessions[session_id]
```

**持久化（推荐）**：
- Session 存到本地文件 `sessions/{id}.json`
- 重启可恢复
- 多个"窗口"用不同 `session_id` 即可

**隔离边界**：
- LLM call 必须**只带**当前 session 的 messages
- 工具调用**不共享** state（除非显式设计）
- 同一个 session 的**所有调用串行化**（避免并发冲突）

---

## 6. Trace / 日志 ⭐（题目要求）

### 6.1 Trace 要记录什么

| 字段 | 说明 |
|------|------|
| `timestamp` | 事件时间 |
| `session_id` | 哪个 session |
| `event_type` | `user_input` / `llm_call` / `tool_call` / `tool_result` / `final_answer` |
| `payload` | 详细内容（LLM prompt、response、tool args、result） |
| `duration_ms` | 耗时 |
| `error` | 异常信息（如果有） |

### 6.2 实现方式

```python
class Tracer:
    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.events: list[dict] = []
    
    def log(self, event_type: str, payload: dict, duration_ms: int = 0):
        event = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.current_session,
            "event_type": event_type,
            "payload": payload,
            "duration_ms": duration_ms
        }
        self.events.append(event)
        # 实时写盘
        with self.log_file.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
```

**进阶**：
- 加 session_id filter、time range filter
- 输出到 stdout 同步（方便 asciinema 录屏）
- 支持结构化搜索

---

## 7. 异常处理

| 异常 | 处理 |
|------|------|
| LLM 调用超时 | 重试 3 次 + 降级（用更小模型）|
| LLM 返回格式错 | 重新解析或 prompt 修正 |
| 工具不存在 | 返回错误给 LLM，让它"重试" |
| 工具执行抛异常 | 捕获 + 返回错误消息给 LLM |
| 工具超时 | 设置 timeout，超时后 kill + 返回错误 |
| Session 损坏 | 备份 + 重新创建 + 通知用户 |

**关键**：错误要**返回给 LLM**，让它能自我纠错（"我刚才调错了，再试一次"）。

---

## 8. 题目考点

Vibe coding 部分会考察：
1. ✅ ReAct 循环的清晰实现（**伪代码 → 真代码**）
2. ✅ 工具注册机制（**Schema 设计能力**）
3. ✅ LLM 输出解析（**function calling vs 文本流**的选择）
4. ✅ Session 隔离（**多窗口 + 持久化**）
5. ✅ Trace（**结构化日志**）
6. ✅ 异常处理（**错误传播给 LLM** 的设计）

---

## 9. 推荐阅读

- **ReAct 论文** (Yao et al., 2022)：原始 ReAct 范式
- **OpenAI Function Calling 文档**：原生 function calling API
- **Anthropic Tool Use 文档**：tool_use XML 风格
- **LangChain Tools 源码**：参考工具注册设计

---

_下节课：02 - Context Engineering_
