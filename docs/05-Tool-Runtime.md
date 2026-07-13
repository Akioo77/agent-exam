# 05 - Tool Runtime ⭐⭐

> **对应题目**：模块四 Tool / Session Runtime 全部
> **核心问题**：异步工具怎么设计？busy 时新消息 + 异步事件怎么并发处理？

---

## 1. 核心概念清单

| 概念 | 一句话解释 |
|------|-----------|
| **Sync Tool** | 同步工具：阻塞调用，拿到结果再返回 |
| **Async Tool** | 异步工具：调用立即返回 task_id，结果后续通知 |
| **Task ID** | 异步任务的唯一标识 |
| **Worker** | 执行任务的后台进程 |
| **Message Queue** | 任务队列（Redis / RabbitMQ / Kafka）|
| **Polling** | 前端轮询查任务状态 |
| **Webhook** | 任务完成后反向推送 |
| **SSE / WebSocket** | 服务端推送流 |
| **Idempotency** | 任务可重复执行，结果一致 |
| **Backpressure** | 背压：队列满时的处理策略 |
| **Mailbox Pattern** | 每个 actor 一个收件箱 |
| **Checkpoint** | 任务中间状态保存点 |
| **Saga** | 长事务分解 + 补偿 |

---

## 2. 同步 vs 异步工具（题目考点 1）

> "Agent 工具有同步和异步两类。异步工具不能让用户一直等，但结果依然重要。你会如何设计异步工具执行和完成通知？"

### 2.1 同步 vs 异步的本质区别

**同步工具**（如 calculator）：
```python
# LLM 调用 → 阻塞 → 拿结果 → 继续
result = calculator(expression="2+3")  # 立即返回 "5"
```

**异步工具**（如 send_email）：
```python
# LLM 调用 → 立即返回 task_id → 后台执行
task_id = send_email(to="x@y.com", body="...")  # 立即返回
# 用户可以继续做别的
# 完成后通知 → LLM 再次被触发
```

**为什么需要异步？**
- 工具本身耗时长（视频处理、模型推理）
- 工具需要等外部事件（人工审批、回调）
- 用户不想"挂着"等

### 2.2 异步工具的协议设计

#### 协议 A：Task ID + Polling

```python
# 工具定义
async_tool_schema = {
    "name": "send_email",
    "description": "发送邮件。立即返回 task_id，结果通过通知送达。",
    "async": True,
    "parameters": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "body": {"type": "string"}
        }
    }
}

# LLM 调用后
result = send_email(to="x@y.com", body="hi")
# 返回: {"task_id": "task_abc123", "status": "pending"}

# 后续 polling
status = check_task("task_abc123")
# 返回: {"status": "completed", "result": "邮件已发送"}
```

**优点**：简单、易实现
**缺点**：polling 浪费资源、实时性差

#### 协议 B：Webhook 回调

```python
# 工具调用时注册回调
result = send_email(
    to="x@y.com", 
    body="hi",
    callback_url="https://agent.example.com/callbacks/email"
)
# 后台执行完成后，主动 POST 回调 URL
```

**优点**：实时性高、零轮询
**缺点**：需要公网可达、回调失败要重试

#### 协议 C：SSE / WebSocket 推送

```python
# LLM 调用
result = send_email(to="x@y.com", body="hi")
# 后台通过 SSE 推送进度
# {"event": "email_progress", "data": {"task_id": "...", "progress": 60}}
# {"event": "email_done", "data": {"task_id": "...", "result": "..."}}
```

**优点**：实时、支持进度更新
**缺点**：需要长连接

#### 协议 D：IM 机器人（飞书 / 钉钉）

```python
# 工具调用后，通过 IM 机器人主动通知
result = send_email(to="x@y.com", body="hi")
# 后台完成后，飞书机器人发消息：
# "📧 邮件已发送给 x@y.com"
```

**优点**：用户主动接收、不需要技术栈
**缺点**：延迟、依赖外部服务

### 2.3 推荐组合

**生产环境**：
1. **主路径**：SSE / WebSocket 推送（实时）
2. **兜底**：Webhook 回调
3. **最后兜底**：Polling（每 5 秒）
4. **用户感知**：IM 机器人消息

### 2.4 状态机

```
[Pending] --(start)--> [Running] --(success)--> [Completed]
                          |
                          +--(fail)--> [Failed]
                          |
                          +--(cancel)--> [Cancelled]
```

### 2.5 完整代码示例

```python
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class AsyncTask:
    task_id: str
    tool_name: str
    args: dict
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str = None
    progress: int = 0
    created_at: float = field(default_factory=time.time)
    
class AsyncToolRegistry:
    def __init__(self):
        self.tasks: dict[str, AsyncTask] = {}
        self.workers: dict[str, Callable] = {}
        self.listeners: list[Callable] = []  # SSE 监听
    
    def register(self, name: str, func: Callable):
        """注册异步工具"""
        self.workers[name] = func
    
    async def execute(self, tool_name: str, args: dict) -> AsyncTask:
        """非阻塞执行，立即返回 task"""
        task = AsyncTask(
            task_id=str(uuid.uuid4()),
            tool_name=tool_name,
            args=args
        )
        self.tasks[task.task_id] = task
        
        # 后台启动 worker
        asyncio.create_task(self._run_task(task))
        
        return task  # 立即返回
    
    async def _run_task(self, task: AsyncTask):
        """后台 worker"""
        try:
            task.status = TaskStatus.RUNNING
            worker = self.workers[task.tool_name]
            task.result = await worker(**task.args)
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
        finally:
            # 通知所有监听者
            for listener in self.listeners:
                await listener(task)
    
    def subscribe(self, listener: Callable):
        """SSE / WebSocket 客户端订阅"""
        self.listeners.append(listener)
```

### 2.6 取消、重试、幂等

**取消**：
```python
async def cancel(self, task_id: str):
    task = self.tasks[task_id]
    if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        task.status = TaskStatus.CANCELLED
        # 通知 worker 取消（worker 自己处理）
```

**重试**（指数退避）：
```python
async def execute_with_retry(self, task, max_retries=3):
    for i in range(max_retries):
        try:
            return await self._run_task(task)
        except RetryableError:
            await asyncio.sleep(2 ** i)
```

**幂等性**：
- 任务 ID 由调用方生成（而不是 server 生成）
- 服务端做"idempotency check"：相同 ID 不重复执行

---

## 3. Session busy 时的并发处理（题目考点 2）⭐

> "如果 session state 为 busy，此时用户又发来新消息，或者异步工具完成事件也到达，runtime 应该如何处理？"

### 3.1 状态机设计

```
        ┌──────────┐
        │   IDLE   │
        └────┬─────┘
             │ user_input
             ↓
        ┌──────────┐
        │  RUNNING │
        └────┬─────┘
             │ tool_call
             ↓
   ┌─────────────────┐
   │ WAITING_TOOL    │
   └────┬────────────┘
        │ tool_result
        ↓
   ┌──────────┐
   │ RUNNING  │  (继续执行)
   └────┬─────┘
        │ final_answer
        ↓
   ┌──────────┐
   │   IDLE   │
   └──────────┘

   异常路径：
   - 任何状态 + interrupt → INTERRUPTED
   - 任何状态 + error → ERROR → IDLE
```

### 3.2 新用户消息：Enqueue vs Interrupt

**判定逻辑**：
```python
def handle_new_message(session, message):
    if session.state == State.IDLE:
        # 立即处理
        session.process(message)
    
    elif session.state == State.RUNNING:
        if is_interrupt(message):  # "停"、"取消"、"不做了"
            session.interrupt()  # 保存 checkpoint
            session.process(message)  # 处理新消息
        elif is_priority(message):  # "等等"、"先回答这个"
            session.pause()  # 暂停当前
            session.process(message)  # 处理新消息
            session.resume()  # 之后恢复
        else:
            # 普通消息：入队
            session.queue.append(message)
    
    elif session.state == State.WAITING_TOOL:
        # 工具等待中：新消息入队
        session.queue.append(message)
```

**判定函数**：
```python
def is_interrupt(message):
    interrupt_keywords = ["停", "取消", "不做了", "stop", "cancel", "abort"]
    return any(kw in message.lower() for kw in interrupt_keywords)
```

### 3.3 异步工具完成事件

**场景**：session 正在 RUNNING，突然一个之前发起的异步任务完成。

```python
async def on_async_task_complete(self, task: AsyncTask):
    session = self.sessions[task.session_id]
    
    if session.state == State.IDLE:
        # session 空闲：触发新 turn，把结果告诉 LLM
        await session.process_tool_result(task)
    
    elif session.state == State.RUNNING:
        # session 正在处理其他事：合并到当前 turn
        session.inject_message({
            "role": "tool",
            "tool_call_id": task.task_id,
            "content": task.result
        })
    
    elif session.state == State.WAITING_TOOL:
        # session 正在等其他工具：新结果入队
        session.pending_tool_results.append(task)
```

### 3.4 Mailbox / Outbox Pattern

**每个 session 一个 mailbox**：

```python
class Session:
    def __init__(self, session_id):
        self.session_id = session_id
        self.state = State.IDLE
        self.mailbox: deque = deque()  # 入站消息
        self.outbox: deque = deque()  # 出站消息
    
    async def receive(self, message):
        """入站：外部消息进入 mailbox"""
        self.mailbox.append(message)
    
    async def process_mailbox(self):
        """主循环：从 mailbox 取消息处理"""
        while self.mailbox:
            msg = self.mailbox.popleft()
            await self._handle(msg)
```

**Actor 风格**：
```python
class SessionActor:
    """每个 session 一个 actor，单线程处理"""
    def __init__(self, session_id):
        self.session = Session(session_id)
        self.queue = asyncio.Queue()
    
    async def send(self, message):
        """外部 send 内部消息"""
        await self.queue.put(message)
    
    async def run(self):
        """主循环"""
        while True:
            message = await self.queue.get()
            if isinstance(message, UserMessage):
                await self._handle_user_msg(message)
            elif isinstance(message, ToolCompleteEvent):
                await self._handle_tool_complete(message)
            elif isinstance(message, InterruptEvent):
                await self._handle_interrupt(message)
```

### 3.5 事件合并

**场景**：用户连发 5 条消息"在吗？"

**优化**：
```python
def merge_rapid_messages(messages, time_window=2.0):
    """合并 2 秒内的连续消息"""
    if not messages:
        return messages
    
    merged = [messages[0]]
    for msg in messages[1:]:
        if msg.timestamp - merged[-1].timestamp < time_window:
            merged[-1].content += "\n" + msg.content
        else:
            merged.append(msg)
    return merged
```

### 3.6 背压策略

**队列满了怎么办？**

| 策略 | 适用 |
|------|------|
| **丢老消息** | 用户不在乎早期消息 |
| **合并消息** | 主题类似 |
| **升级** | 提示用户"消息太多，处理不过来" |
| **暂停接收** | 强制用户等待 |

```python
async def enqueue_with_backpressure(self, message, max_size=100):
    if len(self.queue) >= max_size:
        # 丢老消息
        await self.queue.get()
        logger.warning("Mailbox full, dropping oldest message")
    await self.queue.put(message)
```

### 3.7 快照 / Checkpoint

**为什么需要**：长任务被 interrupt 后能恢复。

```python
@dataclass
class Checkpoint:
    session_id: str
    step_count: int
    current_plan: list
    intermediate_results: dict
    pending_tool_calls: list
    saved_at: float

def save_checkpoint(self):
    self.checkpoints.append(Checkpoint(
        session_id=self.id,
        step_count=self.step_count,
        current_plan=self.current_plan,
        intermediate_results=self.intermediate_state,
        pending_tool_calls=self.pending_calls,
        saved_at=time.time()
    ))
```

---

## 4. 工具执行模型

### 4.1 任务队列

**轻量**：Python `asyncio.Queue`（单机）
**中量**：Redis + RQ / Celery（多进程）
**重量**：RabbitMQ / Kafka（分布式）

### 4.2 重试策略

| 错误类型 | 策略 |
|---------|------|
| 网络错误 | 指数退避重试 |
| 4xx（客户端错）| 不重试 |
| 5xx（服务端错）| 重试 3 次 |
| 超时 | 重试 + 增加 timeout |
| 业务错 | 不重试，返回给 LLM |

### 4.3 死信队列

```python
DEAD_LETTER_QUEUE = []

def handle_failed_task(task, error):
    if task.retry_count >= MAX_RETRIES:
        DEAD_LETTER_QUEUE.append({
            "task": task,
            "error": error,
            "failed_at": time.time()
        })
        alert_admin(task, error)
```

---

## 5. Session Runtime 完整设计

### 5.1 生命周期

```
创建 → 加载 → 运行（循环）→ 空闲 / 销毁
                ↓
            暂停 → 恢复
                ↓
            错误 → 重连
```

### 5.2 状态持久化

```python
def save_session(session):
    db.save({
        "session_id": session.id,
        "user_id": session.user_id,
        "state": session.state.value,
        "messages": session.messages,
        "metadata": session.metadata,
        "updated_at": datetime.now().isoformat()
    })

def load_session(session_id):
    data = db.get(session_id)
    return Session.from_dict(data)
```

### 5.3 跨进程恢复

**挑战**：当前 session 在 process A，下一次请求到 process B。
**解决**：session state 存到共享存储（Redis / DB），新进程加载。

### 5.4 锁机制

```python
SESSION_LOCKS: dict[str, asyncio.Lock] = {}

async def get_session_lock(session_id):
    if session_id not in SESSION_LOCKS:
        SESSION_LOCKS[session_id] = asyncio.Lock()
    return SESSION_LOCKS[session_id]

# 用法
async def process_message(session_id, message):
    lock = await get_session_lock(session_id)
    async with lock:
        session = await load_session(session_id)
        await session.process(message)
        await save_session(session)
```

---

## 6. 错误处理与恢复

| 异常 | 处理 |
|------|------|
| **工具超时** | 设置 timeout，超时 kill + 返回错误 |
| **工具 panic** | 捕获 + 返回错误消息给 LLM |
| **任务取消** | 主动取消 + 清理资源 |
| **部分失败** | 重试部分 + 跳过部分 |
| **错误传播** | 错误返回 LLM，让它自己决定 |

**关键**：错误要**结构化**返回，包含错误类型 + 建议：
```json
{
  "error": "ToolTimeout",
  "message": "search_web took longer than 30s",
  "suggestion": "Try a more specific query"
}
```

---

## 7. 实战案例

### 7.1 OpenHands Runtime

- 状态机：`IDLE / RUNNING / WAITING_USER / WAITING_TOOL`
- 单 session 单 agent 实例
- 工具执行在 Docker container 中

### 7.2 LangGraph Checkpointer

- 状态持久化（Postgres / SQLite）
- 支持时间旅行（回到任意 checkpoint）
- 跨 thread 恢复

### 7.3 CrewAI Task Delegation

- 多 agent 协作
- Task assignment / 任务依赖
- Sequential / Hierarchical 流程

### 7.4 AutoGen 多 Agent 通信

- 群聊模式（GroupChat）
- 1-to-1 直接通信
- Human-in-the-loop

---

## 8. 题目考点

| 考点 | 答题要点 |
|------|---------|
| **异步工具** | 协议设计（task_id / webhook / SSE）、状态机、错误处理 |
| **busy 状态** | enqueue vs interrupt 判定、event merge、背压、checkpoint |
| **完整并发语义** | 不要说"加个锁"，要说清楚 mailbox / actor / queue 模式 |

---

## 9. 推荐阅读

- **Temporal.io 文档** - 工作流引擎
- **Celery 文档** - 任务队列
- **Akka Actor 模型** - 并发范式
- **OpenHands 源码** - https://github.com/All-Hands-AI/OpenHands
- **LangGraph Checkpointer 源码**

---

_下节课：06 - 架构对比_
