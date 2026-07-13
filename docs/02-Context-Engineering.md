# 02 - Context Engineering ⭐⭐⭐

> **对应题目**：模块一 Context / Performance 全部 + Vibe Coding Context 管理
> **核心问题**：长 context 怎么压？TTFT 怎么压？压缩后怎么不丢失关键信息？

---

## 1. 核心概念清单

| 概念 | 一句话解释 |
|------|-----------|
| **Context** | LLM 单次调用的全部输入（system + history + tools + 当前问题）|
| **Context Window** | 模型能处理的最大 token 数（如 128k / 200k）|
| **TTFT** | Time To First Token，首 token 延迟 |
| **Context Caching** | 复用相同前缀的 KV cache，节省计算 |
| **Context Compression** | 把长 history 压缩成短 summary |
| **Memory** | 超出 context window 的外部存储（向量/实体/任务）|
| **RAG** | Retrieval-Augmented Generation，按需检索补全 context |

---

## 2. Context 管理的基础原理

### 2.1 Context 的组成

```
[System Prompt]              # 角色、规则、工具描述
[Tools Schema]               # 工具定义（如果走原生 function calling，这部分不一定占 context）
[User Question + History]    # 历史对话 + 当前问题
[Tool Results]               # 工具返回结果
```

**token 占比典型情况**：
- System prompt：500-2000 tokens
- Tools schema：500-3000 tokens（3-10 个工具）
- History：爆炸点（200 轮 = 20k-100k tokens）
- Tool results：可能很大（一次搜索返回 10k tokens）

### 2.2 关键挑战

1. **超长 history**：每轮对话 500 tokens，200 轮 = 100k tokens
2. **工具结果膨胀**：一次搜索/读文件可能 5k+ tokens
3. **首轮长输入**：多模态 + 长文档 = 5-10s 延迟
4. **压缩后失真**：丢失关键信息导致回复质量下降

---

## 3. 滑动窗口（最朴素）

### 3.1 原理

只保留最近 N 轮对话 + system prompt + 当前问题。

```python
def sliding_window(messages, max_turns=20):
    # 保留 system + 最近 max_turns 条
    if len(messages) <= max_turns + 1:
        return messages
    return [messages[0]] + messages[-max_turns:]
```

### 3.2 优缺点

| 优点 | 缺点 |
|------|------|
| 简单、实现成本 0 | 关键信息丢失 |
| 无额外延迟 | 不支持长程任务 |
| | 用户觉得"AI 忘性好快" |

**适用场景**：闲聊、短期任务。

---

## 4. 摘要压缩（中等方案）⭐

### 4.1 原理

定期用 LLM 把历史对话压缩成 summary，塞回 context。

```python
def compress_history(messages, model):
    history = [m for m in messages if m.role != "system"]
    summary_prompt = f"请将以下对话压缩为简洁摘要，保留关键信息：\n\n{history}"
    summary = model.chat([{"role": "user", "content": summary_prompt}])
    return [{"role": "system", "content": f"对话摘要：{summary}"}] + messages[-5:]
```

### 4.2 进阶：分层摘要

```
[System Prompt]
[Summary 1: 第 1-50 轮摘要]      ← 1-2k tokens
[Summary 2: 第 51-100 轮摘要]    ← 1-2k tokens
[最近 10 轮原文]                  ← 5k tokens
[当前问题]                        ← 0.5k tokens
```

**好处**：保留更多历史细节，总 tokens 反而更少。

### 4.3 关键：保留什么？

压缩时**必须保留**：
1. **任务状态**（"我们在做 X，已经完成 Y"）
2. **用户偏好**（"用户喜欢用表格"）
3. **关键决策**（"我们决定用 A 方案"）
4. **实体信息**（人名、项目名、专有名词）
5. **未完成项**（待办、待确认）

**可以丢弃**：
1. 寒暄、客套
2. 重复信息
3. 错误尝试的细节

---

## 5. RAG-based Memory（高级方案）⭐

### 5.1 原理

把历史对话**向量化**存入外部数据库（向量库），按相关性**检索**召回。

```
[系统提示]
[最近 5 轮原文]
[检索: Top-3 相关历史摘要]  ← 动态召回
[当前问题]
```

### 5.2 关键设计

**a) 何时写？**
- 每 N 轮触发一次（避免每轮都调用 embedding）
- 检测到关键事件（用户偏好表达、任务完成）

**b) 检索什么？**
- 当前问题的 embedding
- 在向量库中找 top-k（k=3-5）
- 相似度阈值过滤（< 0.7 丢弃）

**c) 怎么用？**
- 把检索结果作为"参考"塞入 context
- 让 LLM 自己判断"现在用不用得上"
- 不要硬塞，否则干扰

### 5.3 进阶：实体 + 任务 + 摘要 三库

```
[实体库]: 人名、项目、技术栈等（结构化存储）
[任务库]: 进行中任务、待办、完成项
[摘要库]: 向量化的对话摘要
```

检索时**多路召回 + 重排序**，保证不丢失关键信息。

---

## 6. Context 压缩的"流畅性"保障 ⭐⭐（题目重点）

> "200 轮 context 快爆了。如何确保压缩后对话仍然流畅？"

### 6.1 三道防线

**防线 1：保留任务状态**
```python
# 在 system prompt 中始终保留
TASK_STATE = """
当前任务：为笔试题实现 Agent Runtime
进度：完成 LLM 客户端、工具注册；待完成 ReAct 循环、Session 管理
"""
```

**防线 2：保留最近 N 轮原文**
- 最近 5-10 轮不压缩（保细节）
- 中间 10-50 轮做摘要
- 早期 50+ 轮做实体化

**防线 3：显式 carryover**
- 压缩后的 prompt 加一句："我们之前在讨论 X 任务"
- 显式告诉 LLM "别忘了这件事"

### 6.2 防止"AI 失忆"的具体技巧

| 技巧 | 说明 |
|------|------|
| **System Pin** | System prompt 永远不被压缩，固定任务卡 |
| **Entity Bookkeeping** | 实体信息（人名/项目）单独存，按需召回 |
| **Reflection Token** | 每 20 轮让 LLM 自检"还记得任务吗" |
| **Compression Marker** | 在 history 中标记 `[已压缩: 第 1-50 轮摘要]` |
| **Quality Check** | 压缩后用一个小问题测试 LLM 是否还记得关键信息 |

### 6.3 压缩触发时机

| 触发条件 | 阈值 |
|---------|------|
| 固定间隔 | 每 20 轮 |
| Token 超限 | context > 70% window |
| 任务切换 | 检测到用户切换话题 |
| 主动降级 | 连续 3 轮 LLM 表现差（自检） |

---

## 7. TTFT 优化（5-10s → 2s）⭐⭐（题目重点）

> "大模型面对第一轮长窗口或多模态输入时，first token 会显著变慢。"

### 7.1 优化手段（按性价比排序）

| 手段 | 效果 | 成本 |
|------|------|------|
| **1. 流式响应 (SSE)** | 心理感知 5s → 0.5s | 零 |
| **2. Prompt Caching** | 2-5x 加速 | 收费（如 Anthropic 缓存） |
| **3. Speculative Decoding** | 1.5-2x 加速 | 中（要小模型） |
| **4. 客户端预热** | 100-300ms 加速 | 零 |
| **5. 渐进式占位符** | 心理感知提升 | 零 |
| **6. 模型分片 / 路由** | 4-10x 加速 | 高（架构改动） |
| **7. KV Cache 复用** | 3-10x 加速 | 中 |

### 7.2 推荐组合（性价比最高）

**Layer 1：免费手段**
```python
# 1. 流式响应
response = client.stream_chat(messages)
for chunk in response:
    yield chunk.delta

# 2. 预热（应用启动时调用一次）
_ = client.chat([{"role": "user", "content": "ping"}])

# 3. 渐进式占位符
print("正在分析您的问题...")  # 先输出
# 然后 LLM 流式输出
```

**Layer 2：付费手段**
```python
# 4. Prompt Caching（Anthropic / Gemini 支持）
response = client.chat(
    messages,
    cache_breakpoints=[0, 500]  # 标记可缓存的边界
)

# 5. Speculative Decoding
# 用小模型先出草稿，大模型并行验证
```

### 7.3 实战数据

- **纯流式**：5s → 用户感知 0.5s（5x 心理改善）
- **+ 缓存**：5s → 2s（实际 2.5x 加速）
- **+ Speculative**：5s → 1.5s（实际 3x 加速）
- **全套**：5s → 0.8-1.2s（4-6x 改善）

### 7.4 答题切入建议

主人在答这题时，挑 **2-3 个最熟的**，讲清：
1. **原理**（为什么能优化）
2. **实测数据**（5s → 2s）
3. **取舍**（成本、复杂度）
4. **配合使用**（layer 1 永远做，layer 2 看预算）

---

## 8. 题目考点

| 考点 | 答题要点 |
|------|---------|
| **TTFT 优化** | 至少 2-3 个具体手段，有数据、有原理 |
| **Context 压缩** | 分层策略（原文 + 摘要 + 检索）|
| **流畅性保障** | 保留 task state、entity、carryover |
| **Vibe coding Context** | 滑动窗口 + 摘要触发 + RAG 召回 |

---

## 9. 进阶：Context Engineering 范式

> 这是当前 AI 行业最热门的话题之一（2025-2026）

### 9.1 范式转移

```
2023: 全部塞 context → context 爆炸 → 模型表现下降
2024: Context Caching → 减少重复计算
2025: Memory as a Service → context 外置，按需召回
2026+: Agentic Context Engineering → Agent 自主管理自己的 context
```

### 9.2 头部玩家

- **Anthropic**: Prompt Caching (1h cache) + Skills (动态加载工具)
- **OpenAI**: ChatGPT Memory (跨会话) + Assistants (文件存储)
- **Google**: Gemini Personal Context (跨服务) + Workspace 集成
- **Mem0 / Letta**: 第三方 memory layer

---

## 10. 推荐阅读

- **Anthropic Prompt Caching 文档** ⭐
- **MemGPT 论文** (Packer et al., 2023)
- **Anthropic Context Engineering 博客** (2024)
- **vLLM 源码**：了解 prefill 优化
- **Speculative Decoding 论文** (Leviathan et al., 2023)

---

_下节课：03 - Memory 框架_
