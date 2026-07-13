# 04 - Task Management ⭐

> **对应题目**：模块三 Task 全部
> **核心问题**：长程任务怎么不丢目标？每天 9 点定时复盘怎么设计？

---

## 1. 核心概念清单

| 概念 | 一句话解释 |
|------|-----------|
| **Task** | 有明确目标 + 步骤的执行单元 |
| **Task State** | 任务当前状态（目标、进度、已完成/待办）|
| **Plan** | 任务的执行步骤序列 |
| **Subgoal** | 子目标（大任务拆分）|
| **Self-Reflection** | LLM 自我检查"我还在做正确的事吗"|
| **Milestone** | 可验证的中间节点 |
| **Scheduled Agent** | 定时触发的 agent |
| **Proactive Agent** | 主动发起动作的 agent（不是被动等指令）|
| **Long-running Task** | 跨小时 / 天的任务 |
| **Goal Drift** | 目标漂移（任务做着做着就忘了目标）|

---

## 2. 长程任务的目标丢失（题目考点 1）

> "对于长程任务，大模型执行一段时间可能会忘掉目标，你知道哪些解决方案，有什么优缺？"

### 2.1 为什么会丢目标？

**根本原因**：
- LLM 一次只看得到 context 里的内容
- 随着 history 增长，最初的指令被"挤出去"
- 注意力机制对长 context 末端的偏好
- 工具调用、错误重试、用户消息插入 → 目标被冲淡

**症状**：
- 做着做着偏离主题
- 重复已经完成的事
- 产出和最初目标不一致
- 用户提醒"你忘了 X"

### 2.2 解决方案（按实现难度排序）

#### 方案 1：System Prompt 固定任务卡 ⭐（必做）

**原理**：把任务状态写进 system prompt 永远不丢。

```python
SYSTEM_PROMPT = """
你是 Agent 助手。当前任务：

【任务目标】为 HKUST 调研项目实现 Agent Runtime
【进度】
  ✅ LLM 客户端
  ✅ 工具注册
  ⏳ ReAct 循环（进行中）
  ⬜ Session 管理
  ⬜ Context 管理
【约束】
  - 必须用 Python
  - 必须用 minimax M3
  - 必须支持 3 个工具
【用户偏好】喜欢深蓝主题、不喜欢花哨动画
"""
```

**优点**：零成本、确定性强
**缺点**：占用 context 空间、任务变化时要改 prompt

#### 方案 2：每 N 步 Self-Check ⭐（推荐）

**原理**：每 5-10 轮强制 LLM 自检"我还在做 X 吗"。

```python
def maybe_reflect(messages, step_count):
    if step_count % 5 == 0:
        reflection_prompt = {
            "role": "user",
            "content": f"""
请检查：
1. 当前任务是什么？
2. 我们已经做了什么？
3. 接下来要做什么？
4. 我是否还在正确路径上？

如果偏离，请重新规划。
"""
        }
        return messages + [reflection_prompt]
    return messages
```

**优点**：动态纠偏、不占额外空间
**缺点**：额外 LLM 调用成本

#### 方案 3：外化 Plan（todo 工具）⭐⭐（强烈推荐）

**原理**：用 todo 工具把 plan 存到外部，prompt 中持续 reference。

```python
# todo 工具的 schema
todo_schema = {
    "name": "todo",
    "description": "Manage a persistent todo list. Use this to track your plan.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"enum": ["add", "update", "list", "complete"]},
            "items": {"type": "array", "items": {"type": "string"}}
        }
    }
}

# LLM 使用
# Step 1: todo add "实现 ReAct 循环"
# Step 2: todo add "实现 Session 管理"
# Step 3: todo update "ReAct 循环" → "done"
# ...
```

**优点**：
- Plan 持久化（不占 context）
- LLM 显式跟踪进度
- 可视化给用户看

**缺点**：依赖 LLM 自觉使用

#### 方案 4：进度可视化

**原理**：把当前进度显式塞回 prompt。

```python
# 每轮 prompt 中都包含
context_block = f"""
【当前进度】
{completed}/{total} 步完成
下一步：{next_step}
"""
```

#### 方案 5：Plan-Execute-Replan 循环

**原理**：定期重新规划，而不是死板按初始 plan。

```
[Initial Plan] → [Execute] → [Result] → [Replan] → [Execute] → ...
                  ↑                                 ↓
                  └────── if not on track ──────────┘
```

#### 方案 6：Subgoal + 独立 Context

**原理**：把大任务拆成多个子任务，每个子任务用**独立的** context。

```
[任务] 实现 Agent
  ├── [子任务 1] 实现 ReAct Loop（独立 context）
  ├── [子任务 2] 实现 Session（独立 context）
  └── [子任务 3] 实现 Context Management（独立 context）
```

**优点**：每个子任务的 context 短、清晰
**缺点**：子任务间的状态传递复杂

### 2.3 方案对比

| 方案 | 成本 | 效果 | 实现难度 | 推荐度 |
|------|------|------|---------|--------|
| System Prompt 任务卡 | 零 | ⭐⭐ | 低 | ⭐⭐⭐ 必做 |
| Self-Check | 中 | ⭐⭐⭐ | 低 | ⭐⭐⭐ 推荐 |
| 外化 Plan | 零 | ⭐⭐⭐ | 中 | ⭐⭐⭐ 强烈推荐 |
| 进度可视化 | 零 | ⭐⭐ | 低 | ⭐⭐ |
| Plan-Execute-Replan | 中 | ⭐⭐⭐ | 高 | ⭐⭐ |
| Subgoal 拆分 | 中 | ⭐⭐⭐⭐ | 高 | ⭐⭐ 复杂任务才用 |

### 2.4 推荐组合

**最小可行**：
- System Prompt 任务卡 + 外化 Plan（todo 工具）

**生产级**：
- 上述 + 每 5 步 Self-Check + 进度可视化

**复杂任务**：
- 上述 + Subgoal 拆分 + Plan-Execute-Replan

---

## 3. Plan-and-Execute 范式

### 3.1 ReAct vs Plan-and-Execute

| 维度 | ReAct | Plan-and-Execute |
|------|-------|------------------|
| 思考方式 | 边想边做 | 先全想好，再做 |
| 灵活性 | 高 | 中 |
| 适合任务 | 短、动态 | 长、结构化 |
| Token 消耗 | 多（每步都思考）| 少（前期一次性思考）|
| 失败恢复 | 自然 | 需要 Replan |

### 3.2 BabyAGI / AutoGPT 案例

**BabyAGI**（2023-03）：
```python
while True:
    task = prioritize_tasks(task_list)
    result = execute(task)
    new_tasks = generate_new_tasks(result)
    task_list = update(task_list, new_tasks)
```

**AutoGPT**（2023-04）：
- 类似循环，加了 self-criticism
- 缺点：成本爆炸、容易陷入死循环

### 3.3 现代方案：Plan-Execute-Replan

```python
plan = planner(initial_goal)
while not done:
    step = next(plan)
    result = executor(step)
    plan = re_planner(plan, result, goal)
```

**Planner 用 LLM，Executor 用 LLM + Tools，Re-Planner 用 LLM。**

---

## 4. 定时任务设计（题目考点 2）⭐⭐

> "用户给 Agent 下达任务：每天早上 9 点根据昨天聊天情况做复盘总结。你会怎么设计？"

### 4.1 完整架构设计（10 个组件）

#### 组件 1：触发层 (Trigger)

**实现**：
```python
# Cron job
0 9 * * * /usr/bin/python3 /app/agent/daily_review.py

# 或 Python APScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

sched = BlockingScheduler()
sched.add_job(daily_review_job, 'cron', hour=9, minute=0)
sched.start()
```

**设计要点**：
- 时区处理（用户本地时区 vs UTC）
- 错峰（避免整点扎堆）
- 重试触发（如果 9 点没跑成，10 点补跑？）

#### 组件 2：数据收集 (Data Collection)

**收集什么**：
- 昨天 0:00 - 24:00 的所有对话
- 任务完成情况
- 工具调用历史
- 用户活跃度

```python
def collect_yesterday_data():
    end = datetime.now().replace(hour=0, minute=0, second=0)
    start = end - timedelta(days=1)
    
    conversations = db.query("""
        SELECT * FROM messages 
        WHERE created_at >= ? AND created_at < ?
    """, start, end)
    
    tasks = db.query("""
        SELECT * FROM tasks 
        WHERE updated_at >= ? AND updated_at < ?
    """, start, end)
    
    return {
        "conversations": conversations,
        "tasks": tasks,
        "user_active_hours": compute_active_hours(conversations)
    }
```

#### 组件 3：Prompt 工程 (Prompt Template)

```python
DAILY_REVIEW_PROMPT = """
你是主人的个人复盘助手。基于以下昨日数据，生成结构化日报。

【昨日对话数据】
{conversations_summary}

【任务完成情况】
{task_status}

【用户活跃模式】
{user_active_hours}

请生成以下内容：
1. 【今日完成】3-5 条具体成就
2. 【今日遗留】未完成项 + 原因分析
3. 【亮点】做得好的地方（具体到对话引用）
4. 【改进点】明天可以优化的事
5. 【建议】基于数据主动建议

要求：
- 简洁（每条 1-2 句话）
- 具体（引用实际对话/任务）
- 主动（不要"今天没数据"，要给行动建议）
- 主人风格偏好：{user_style_preference}
"""
```

#### 组件 4：输出结构 (Output Format)

**三种模式**：
- 晨会版（150 字，关键信息）
- 详细版（500 字 + 数据）
- 摘要版（50 字，标题 + 1 句总结）

```python
@dataclass
class DailyReport:
    date: date
    summary_version: str          # 50字摘要
    morning_meeting_version: str  # 150字晨会版
    detailed_version: str         # 500字详细版
    metrics: dict                 # 数据
    recommendations: list[str]    # 主动建议
```

#### 组件 5：推送渠道 (Delivery)

**多渠道并行**：
- 邮件（IMAP）
- 飞书 / 钉钉机器人
- 微信公众号模板消息
- App 推送
- Web Dashboard

```python
def deliver(report, channels=["feishu", "email"]):
    for ch in channels:
        if ch == "feishu":
            feishu_bot.send(report.summary_version)
        elif ch == "email":
            smtp.send(report.morning_meeting_version)
```

#### 组件 6：失败兜底 (Failure Handling)

**场景**：
- 昨天完全没数据（首次 / 沉默日）
- LLM 调用失败
- 推送渠道不可用

**兜底**：
```python
def safe_daily_review():
    data = collect_yesterday_data()
    if not data or len(data["conversations"]) == 0:
        # 沉默日：主动问候
        return Report(
            summary="昨天咱们没怎么聊，今天想做点啥？",
            recommendations=["有什么我可以帮你的吗？"]
        )
    
    try:
        report = generate_report(data)
    except LLMError:
        # 降级到模板
        return generate_template_report(data)
    
    return report
```

#### 组件 7：个性化 (Personalization)

**用户偏好维度**：
- 详细程度（5 级）
- 关注维度（效率/学习/健康/财务）
- 输出风格（学术/轻松/数据驱动）
- 推送时间（9:00 / 9:30 / 自定义）

**存储**：
```python
user_prefs = {
    "user_001": {
        "detail_level": 3,
        "focus_areas": ["efficiency", "learning"],
        "style": "casual",
        "push_time": "09:00",
        "language": "zh-CN"
    }
}
```

#### 组件 8：反馈循环 (Feedback Loop)

**主人可标注**：
- 👍 这条有用
- 👎 不准 / 没用
- 编辑 / 修正

**学习**：
```python
def on_feedback(report_id, rating, edit=None):
    if rating == "bad":
        # 把负反馈加入训练数据
        training_data.append({
            "prompt": report.prompt,
            "output": report.output,
            "expected": edit or "正确版本",
            "rating": "bad"
        })
```

#### 组件 9：成本控制 (Cost Optimization)

**策略**：
- 工作日深度版 + 周末摘要版
- 没数据日不调用 LLM
- 用小模型做初稿，大模型做润色
- 缓存重复内容

```python
def select_model(date, data_size):
    if date.weekday() >= 5:  # 周末
        return "small_model"
    if data_size < 100:
        return "small_model"
    return "large_model"
```

#### 组件 10：可解释性 (Explainability)

**每条结论都能追溯**：
- "今天完成 5 个任务" → 来源：db.tasks
- "主人最近关注 X" → 来源：embedding.topics
- "建议做 Y" → 来源：template + recent_pattern

---

## 5. Scheduled Agent / Proactive Agent 实战案例

### 5.1 ChatGPT Daily Brief

- 触发：用户主动开启
- 内容：今日新闻 + 用户关注的话题
- 渠道：邮件 + App 推送

### 5.2 Apple Intelligence Reminders

- 触发：上下文感知（时间/位置/活动）
- 主动判断：是否需要提醒
- 隐私：端侧处理

### 5.3 企业 OKR 系统

- 触发：周一周五自动
- 数据收集：上周任务、目标完成度
- 输出：进度报告 + 风险预警

### 5.4 GitHub Actions + Agent

- 触发：代码 push
- 自动化：review / 部署
- 通知：Slack / Email

---

## 6. 题目考点

| 考点 | 答题要点 |
|------|---------|
| **目标丢失** | 三道防线：任务卡 + self-check + 外化 plan |
| **每天 9 点复盘** | 至少 8 个组件（触发/数据/prompt/输出/渠道/兜底/个性化/反馈）|
| **关键 trade-off** | 成本 vs 质量、自动化 vs 控制、个性化 vs 通用 |

---

## 7. 推荐阅读

- **Plan-and-Execute 论文** (Wei et al., 2022)
- **Reflexion 论文** (Shinn et al., 2023) - 自我反思
- **BabyAGI 开源** - https://github.com/yoheinakajima/babyagi
- **LangGraph Long-running Tasks 文档**
- **APScheduler 文档** - 调度实现

---

_下节课：05 - Tool Runtime_
