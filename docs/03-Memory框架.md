# 03 - Memory 框架 ⭐⭐

> **对应题目**：模块二 Memory 全部
> **核心问题**：长期 memory 的范式转移是什么？召回时机怎么设计？

---

## 1. 核心概念清单

| 概念 | 一句话解释 |
|------|-----------|
| **Working Memory** | 当前 context 里的信息，模型能直接看到 |
| **Episodic Memory** | 个体经历（"我昨天和主人聊过 X"）|
| **Semantic Memory** | 通用知识（"Python 是一种语言"）|
| **Procedural Memory** | 技能 / 流程（"怎么重启服务"）|
| **Memory Consolidation** | 把短期记忆转化为长期记忆 |
| **Retrieval-Augmented Memory** | 按相关性检索召回 |
| **Memory Decay** | 时间衰减权重（越久越不重要）|
| **Memory Distillation** | 从对话中提取结构化记忆 |
| **Memory Conflict Resolution** | 解决新记忆 vs 旧记忆的冲突 |
| **Forgetting Mechanism** | 主动遗忘不重要或错误的信息 |

---

## 2. Memory 在 Agent 中的角色

### 2.1 为什么需要 Memory？

**核心矛盾**：LLM 的 context window 是有限的（128k / 200k），但用户的交互历史是无限的。

```
Context Window     ~     Memory (外部存储)
[最近 5-10 轮]           [所有历史对话]
[当前任务]                [用户偏好]
[关键摘要]                [实体信息]
[工具结果]                [任务状态]
```

**关键转变**：
```
2023: "全塞 context"
2024: "Context Caching + 摘要压缩"
2025: "Memory as a Service" ← 主流
2026: "Agentic Memory Engineering"
```

### 2.2 Memory vs Context

| 维度 | Context | Memory |
|------|---------|--------|
| 存储位置 | LLM 提示词 | 外部数据库 / 文件 |
| 大小限制 | 几十 k tokens | 几乎无限 |
| 访问方式 | 全量加载 | 按需检索 |
| 成本 | 高（每次调用都付） | 低（按检索次数）|
| 一致性 | 每次一致 | 动态变化 |

**实战原则**：能外置的，就不要塞 context。

### 2.3 短期/中期/长期 分层

```
短期（小时级）: 当前 session 的 messages（内存）
中期（天级）:   摘要 + 任务状态（SQLite / JSON）
长期（年级）:   用户偏好 + 实体 + 关键事件（向量库 + SQL）
```

---

## 3. 经典框架

### 3.1 MemGPT / Letta (2023) ⭐

**作者**：Charles Packer 等（UC Berkeley）
**论文**：*MemGPT: Towards LLMs as Operating Systems* (2023)
**公司**：Letta（前身是 MemGPT 团队）
**链接**：https://research.memgpt.ai

**核心思想**：把 LLM 看作**操作系统**，把 context 看作**物理内存**。
- 物理内存 = context window（有限、快）
- 虚拟内存 = 外部存储（无限、慢）
- LLM 自己管理 page in / page out

**架构**：
```
┌────────────────────────┐
│  Main Context (LLM)    │ ← 物理内存
│  - System Instructions │
│  - Working Context     │
│  - FIFO Buffer         │
│  - 最近 N 个 events    │
└────────┬───────────────┘
         │ function calls
         ↓
┌────────────────────────┐
│  External Context      │ ← 虚拟内存
│  - Recall Storage      │
│  - Archival Storage    │
│  - (向量 / SQL)         │
└────────────────────────┘
```

**优点**：
- ✅ 突破 context window 限制
- ✅ LLM 自主管理"记忆"
- ✅ 学术开创性，影响后续所有 memory 框架

**缺点**：
- ❌ 实现复杂
- ❌ 调试困难（"AI 为什么不读那条 memory？"）
- ❌ function call 消耗额外 token

**当前状态**：Letta 开源（https://github.com/letta-ai/letta），仍是学术最经典实现。

---

### 3.2 Mem0 (2024) ⭐⭐

**作者**：Prateek Choudhary 等
**论文**：*Mem0: Long-Term Memory for LLM Agents* (2024)
**链接**：https://mem0.ai

**核心思想**：把 memory 抽象成 **Add / Search / Update / Delete** 四个操作，作为 LLM 应用的 middleware。

**架构**：
```
[LLM App]
    ↓ add/search/update/delete
[Mem0 Layer]
    ├── LLM Distillation  (从对话中提取记忆)
    ├── Vector Store      (Qdrant / Chroma / pgvector)
    ├── SQL Store         (关系数据)
    └── Conflict Resolution
```

**关键能力**：
1. **Extraction**：用 LLM 从对话中提取结构化记忆
2. **Conflict Resolution**：新信息 vs 旧信息 → 决定 update / replace / keep both
3. **Multi-level Search**：按 user / agent / session 分层
4. **Production-ready**：支持多种向量库、有 SDK

**论文亮点**（Mem0 vs MemGPT vs OpenAI Memory）：
- 比 MemGPT 快 91%，token 消耗少 90%
- 比 OpenAI Memory 在 LOCOMO benchmark 上准确率高 26%

**代码示例**：
```python
from mem0 import Memory

m = Memory()
m.add("主人喜欢深蓝主题，不喜欢花哨动画", user_id="user_001")

# 自动提取 entities, relations, facts
related = m.search("主人喜欢什么颜色", user_id="user_001")
# 返回: ["主人喜欢深蓝主题，不喜欢花哨动画"]
```

**优点**：
- ✅ 生产级、性能优化好
- ✅ 容易集成（middleware 设计）
- ✅ 开源 + 商业化都成熟

**缺点**：
- ❌ 仍依赖外部 LLM 做 extraction
- ❌ 准确率依赖 LLM 质量

---

### 3.3 A-MEM (2025) ⭐

**作者**：Wujiang Xu 等（UIUC + Microsoft）
**论文**：*A-MEM: Agentic Memory for LLM Agents* (2025)
**链接**：https://arxiv.org/abs/2502.12110

**核心思想**：受 **Zettelkasten**（卢曼卡片盒）启发，构建**自演化**的笔记网络。

**关键能力**：
1. **Note Generation**：每条交互生成一张"原子笔记"
2. **Link Generation**：新笔记和旧笔记自动建立链接（语义相似度）
3. **Evolution**：每次访问时，LLM 主动重写、合并、扩展旧笔记
4. **Agentic**：LLM 自己决定"要不要修改旧记忆"

**架构**：
```
[对话输入] 
    ↓
[LLM Note Generation] 
    ↓
[Semantic Link to Old Notes] 
    ↓
[Memory Network] ← 类似知识图谱
    ↓
[Retrieval] 
    ↓
[LLM Response]
```

**优点**：
- ✅ 自演化，不需要人工维护
- ✅ 链接式结构，支持"联想回忆"
- ✅ 学术新颖

**缺点**：
- ❌ 成本高（每次交互都要 LLM 多次调用）
- ❌ 不可预测（LLM 可能改坏旧记忆）

---

### 3.4 MIRIX (2025)

**作者**：Mirix 团队
**链接**：https://github.com/Mirix-AI/MIRIX

**核心思想**：**多模态 memory** —— 文字、图片、音频、视频都能存。

**架构**（6 类组件）：
- **Textual Memory**
- **Image Memory**
- **Audio Memory**
- **Video Memory**
- **PDF Memory**
- **Cross-modal Linking**

**应用场景**：
- AI 助手能"记住"主人发过的图
- 视频会议摘要
- 多模态知识管理

---

### 3.5 LangGraph Memory

**链接**：https://github.com/langchain-ai/langgraph

**特点**：框架绑定，提供：
- **Short-term Memory**：thread-scoped，session 内可见
- **Long-term Memory**：cross-thread，跨 session 持久化
- **Checkpointer**：状态保存 / 恢复

**优点**：易用、与 LangChain 生态整合
**缺点**：绑定框架，迁移成本高

---

## 4. 头部玩家产品拆解

### 4.1 Anthropic Claude Memory

**发布时间**：2024 年 10 月（Projects），2025 年（Memory）
**形态**：
- **Projects Memory**：项目级，文档 + 知识库
- **User Memory**：跨项目，记住用户偏好
- **Skills**：动态加载的工具 / 提示

**关键设计**：
- 显式的 memory 开关（用户可关闭）
- Project 内文档自动 context
- Skills 是"懒加载"的工具

**官方说法**：*"Memory allows Claude to remember context across conversations, so you don't have to repeat yourself."*

---

### 4.2 OpenAI ChatGPT Memory

**发布时间**：2024 年 2 月（首次），2024 年 9 月（重大升级）
**形态**：
- **Saved Memories**：用户显式要求记住的
- **Referenced Memories**：ChatGPT 自动提取的
- **Manage Memory**：UI 列出所有 memory，可逐条删除

**关键设计**：
- 用户**完全控制**（CRUD 全开放）
- "Memory about you" 显式卡片
- 跨 session、跨设备同步
- Team / Enterprise 隔离

**统计数据**（2024 末）：
- 平均每用户 100+ memory
- 60% 任务有 memory 参与

---

### 4.3 Google Gemini Personal Context

**发布时间**：2024-2025
**形态**：
- 跨 Google 服务（Search / YouTube / Maps / Gmail）
- 用户可选开启
- 主动建议："Based on what you searched..."

**关键设计**：
- 整合 Gmail / Calendar / Photos 数据
- Personal Context 强相关于 Google 生态
- 用户可在 myactivity.google.com 管理

---

### 4.4 Microsoft Copilot Memory

**发布时间**：2024-2025
**形态**：
- 企业级：工作内容、邮件、文档
- 个人级：用户偏好
- 与 Microsoft 365 深度整合

---

### 4.5 其他

- **Apple Intelligence (2025)**：端侧 memory，隐私优先
- **Replika**：社交 agent 长期记忆
- **Meta AI**：社交图谱整合
- **Notion AI / Cursor**：垂直场景 memory

---

## 5. 召回时机设计 ⭐（题目重点）

> "和聊天 Agent 熟悉半个月后，用户问了一个以前问过的问题。Agent 如何做 memory 召回更合理？"

### 5.1 召回流程

```
[用户输入] 
    ↓
[Embedding] 
    ↓
[Vector Search in Memory DB] 
    ↓
[Similarity Filter (threshold=0.7)] 
    ↓
[Top-k Selection] 
    ↓
[Context Assembly] 
    ↓
[LLM Response]
```

### 5.2 关键设计点

**a) 何时触发召回？**
- **被动召回**：每条用户输入都查（成本高，但准确）
- **主动召回**：检测到特定信号才查
  - 主题相似度 > 0.7
  - 出现历史关键词
  - 时间/实体引用（"上次那个 X"）

**推荐**：被动 + 主动结合，常规靠 embedding 相似度，关键实体用精确匹配。

**b) 召回什么？**
- 用户偏好（最高优先级）
- 关键事实（项目名、人名）
- 类似问题的历史回答
- 行为模式（"主人通常在晚上写代码"）

**不要召回**：
- 寒暄、客套
- 失败尝试的细节
- 临时性状态

**c) 召回多少？**
- Top-k（k=3-5）
- 阈值过滤（cosine < 0.7 丢弃）
- 总量控制在 500-1000 tokens

**d) 怎么用？**
- **隐式融入**：直接做参考，LLM 自然调用
- **显式标注**："根据您之前说过的话..."（更可控）

**e) 时间衰减**
```python
def score(memory, current_time):
    age_days = (current_time - memory.created_at).days
    recency = math.exp(-age_days / 30)  # 30 天半衰期
    return memory.relevance * 0.7 + recency * 0.3
```

### 5.3 避免"召回过载"

**症状**：每次回答都加"根据您之前..."，主人觉得烦。

**解决**：
1. 严格阈值（只在真正相关时召回）
2. 最多 2-3 条
3. 不要每条都用
4. 给用户"关闭 memory"选项

### 5.4 隐私边界

| 应该记住 | 不应该记住 |
|---------|----------|
| 偏好（喜欢 / 不喜欢）| 密码、token、密钥 |
| 项目 / 任务信息 | 一次性敏感信息 |
| 工作模式 | 私人聊天细节 |
| 显式要求记住的内容 | 未授权的数据 |

**最佳实践**：用户可导出 / 清除所有 memory。

---

## 6. 范式转移 ⭐

### 6.1 演进时间线

```
2023 Q1:  LangChain 发布 - 全塞 context
2023 Q2:  AutoGPT - 文件系统当 memory
2023 Q4:  MemGPT 论文 - 虚拟内存类比
2024 Q1:  ChatGPT Memory - 产品化里程碑
2024 Q2:  Mem0 - middleware 范式
2024 Q4:  Anthropic Skills - 动态加载
2025 Q1:  A-MEM / MIRIX - 自演化 + 多模态
2025 Q2:  Agentic Memory - LLM 自主管理
2025-26:  Memory Marketplace 探索
```

### 6.2 关键趋势

**a) Memory as a Service**
- 独立产品（Mem0、Letta Cloud）
- 不绑特定 LLM
- 多 Agent 共享同一 memory

**b) 用户可控**
- GDPR / 隐私法规要求
- 显式 CRUD UI
- "Memory 仪表盘"

**c) 多模态**
- 图像 / 视频 / 音频记忆
- 跨模态检索（"找那张我上周画的图"）

**d) 跨 Agent 共享**
- 同一用户，多个 Agent 互见 memory
- "AI 团队"记忆共享

**e) RAG 化**
- 从"全塞 prompt"到"按需检索"
- 向量库 + 关系库 + 时序库混合

**f) Memory Engineering 成为独立学科**
- 类似 prompt engineering
- 关注：存储、检索、压缩、遗忘

---

## 7. 题目考点

| 考点 | 答题要点 |
|------|---------|
| **召回时机** | 触发条件、top-k、阈值、避免过载 |
| **经典框架** | 至少 3 个框架（MemGPT、Mem0、A-MEM），讲清各自设计哲学 |
| **头部玩家** | Anthropic、OpenAI、Gemini 怎么做的（不要列名，要讲细节）|
| **范式趋势** | 从 in-context → out-of-context 的范式转移 |

---

## 8. 推荐阅读

- **MemGPT 论文** (Packer et al., 2023) - https://arxiv.org/abs/2310.08560
- **Mem0 论文** (Choudhary et al., 2024) - https://mem0.ai/research
- **A-MEM 论文** (Xu et al., 2025) - https://arxiv.org/abs/2502.12110
- **Anthropic Claude Memory 博客** (2024)
- **OpenAI Memory 发布说明** (2024-09)

---

_下节课：04 - Task Management_
