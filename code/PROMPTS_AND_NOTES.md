# AI Prompt 与问题解决记录

> 本文档记录了实现过程中使用的关键 AI prompts 以及遇到的问题和解决方案。

---

## 📝 关键 Prompts

### 1. 工具注册 Schema 自动生成

**目的**：让每个工具自动从 `execute` 方法签名推导 JSON Schema，无需手写 schema。

**Prompt 给出的方向**：
> 用 `inspect.signature` + `get_type_hints` 自动读取参数，把 Python 类型映射到 JSON Schema 的 `"type"`，把没有默认值的参数放进 `"required"`。

**实际产物**（在 `agent/tools.py`）：
```python
def schema(self) -> ToolSchema:
    sig = inspect.signature(self.execute)
    hints = get_type_hints(self.execute)
    properties, required = {}, []
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "kwargs"):
            continue
        json_type = _python_type_to_json_type(hints.get(param_name, str))
        prop = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        properties[param_name] = prop
    return ToolSchema(name=self.name, description=self.description,
                      input_schema={"type": "object",
                                    "properties": properties,
                                    "required": required})
```

---

### 2. ReAct Loop 状态机

**核心 Prompt**：
> 状态机需要 7 个状态：`IDLE / RECEIVED / REASONING / TOOL_CALLING / TOOL_COMPLETED / RESPONDING / DONE`。每次状态转换都要在 trace 里记录。

**关键设计决策**：
- **每个 round 重新塞入 context**：assistant 的 `tool_use` 块必须保留在 context 里，user 的 `tool_result` 块必须紧跟其后（Anthropic API 强制要求）。
- **Synthesized tool calls 走纯文本路径**：当 LLM 用 XML 风格输出工具调用时，API 不认识我们生成的 tool_use_id，所以必须把结果用文本塞回 context，而不是用 `tool_result` 块。

**实现片段**：
```python
if parsed.synthesized_calls:
    text_content = "\n\n".join(b["text"] for b in tool_result_blocks)
    self.context.append({"role": "user",
                         "content": f"Tool results:\n{text_content}"})
else:
    self.context.append({"role": "user", "content": tool_result_blocks})
```

---

### 3. Context 压缩策略

**Prompt**：
> 用户输入和工具结果必须保留，assistant 的 thinking 文本可以截断。最近 N 条消息永远不动。

**实际策略**（`agent/context.py`）：
- 保留 `messages[0]`（system）和最后 `keep_recent` 条
- 中间的 assistant 文本块超过 100 字符的，替换为 `"[earlier response truncated for context budget]"`
- tool_result 内容超过 300 字符的，截断并标注

---

### 4. Session 隔离方案

**Prompt**：
> 每个 CLI 实例 = 一个 session，文件持久化到 `~/.agent_sessions/`。

**实现**：
```python
def new_session(self, title: str = "") -> Session:
    sid = f"session_{uuid.uuid4().hex[:12]}"
    s = Session(session_id=sid, title=title)
    self.save(s)
    return s
```

**为什么用 UUID 而不是顺序 ID**：避免冲突、避免暴露信息、CLI 启动时不需要查重。

---

## 🐛 遇到的问题与解决方案

### 问题 1：calculator 工具的安全

**问题描述**：用 `eval()` 执行用户表达式太危险，可以 `eval("__import__('os').system('rm -rf /')")`。

**解决方案**：用 `ast.parse` + 白名单运算符 + 节点遍历（`_safe_eval`），只允许数字和 `+ - * / // % **` 等基本运算。

**验证**（`test_calculator.py`）：
```python
def test_invalid_expression():
    out = CalculatorTool().execute(expression="__import__('os')")
    assert out.startswith("Error")
```

---

### 问题 2：M3 模型的 tool_use 不稳定

**问题描述**：M3 模型有时输出**结构化**的 `tool_use` 块，有时输出 **XML 内嵌**（`<tool_use>{...}</tool_use>`），有时输出**另一种 XML**（`<tool_name>X</tool_name><parameters>...</parameters>`），有时干脆只描述要做什么而不调工具。

**解决方案**：写一个**多 parser fallback**：
1. 优先识别原生 `tool_use` content 块（绝大多数情况）
2. fallback 1：识别 `<tool_use>{json}</tool_use>` 模式
3. fallback 2：识别 `<tool_name>NAME</tool_name><parameters>{json}</parameters>` 模式
4. fallback 3：识别 `<parameters><k>v</k></parameters>` 的 KV 形式
5. 标记 `synthesized_calls=True`，让 runtime 走文本回传路径，避免 API 400 错误

**代码位置**：`agent/parser.py` 的 `_scrape_xml_tool_use()` 函数。

**关键洞察**：当模型输出 XML 而不是结构化块时，我们生成的 tool_use_id 是**本地伪造**的，API 不认识它们。所以工具结果必须用**纯文本**塞回，而不是 `tool_result` 块。

---

### 问题 3：API 返回的 stop_reason 不可信

**问题描述**：当 M3 输出 XML 格式时，API 仍然返回 `stop_reason: "end_turn"`，但实际上是要调用工具。

**解决方案**：parser 检测到 XML tool use 时，自动把 `stop_reason` 改成 `"tool_use"`。

**代码片段**：
```python
if result.tool_calls and result.stop_reason == "end_turn":
    result.stop_reason = "tool_use"
    result.synthesized_calls = True
```

---

### 问题 4：tool_result 内容可能很大

**问题描述**：search mock 返回的内容很长，硬塞 context 会快速吃光 token。

**解决方案**：compression 时保留 `tool_result` 的类型标记，但内容截断到 300 字符并加 `[truncated]` 标记。

**代码位置**：`agent/context.py` 的 `_compress_message()`。

---

### 问题 5：测试如何不依赖真实 LLM

**问题描述**：面试题要求"使用真实的 LLM API"，但测试不应该每次都打 API（成本+速度+不稳定）。

**解决方案**：用 `unittest.mock.patch` 替换 `agent.runtime.safe_chat`，注入 canned responses。这样：
- 单元测试快速、可重复、零成本
- 真实 LLM 集成在 demo 脚本里手动验证

**代码位置**：`tests/test_runtime.py` 全部用例。

---

## 🎯 学到的关键经验

1. **Tool schema 应该从代码推导，而不是手写**。改动工具签名时 schema 自动同步，避免不一致。
2. **AI 模型的 tool calling 不可靠**。必须设计 fallback parser，否则在生产环境会随机失败。
3. **API 的 stop_reason 也可能是错的**。不能让 runtime 完全相信它。
4. **Context 压缩必须保留语义**。不能粗暴删消息，要保留 user input 和 tool result，截断的是 thinking。
5. **Session 文件化比数据库简单**。对单机 CLI 项目来说，JSON 文件足够，不用引入 DB 依赖。

---

_以上记录帮助理解整个 Agent Runtime 的设计动机和踩过的坑。_