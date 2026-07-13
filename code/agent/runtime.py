"""The ReAct Loop state machine — the Agent Runtime core.

States:
    IDLE              waiting for user input
    RECEIVED          user input just arrived
    REASONING         calling LLM to decide
    TOOL_CALLING      executing one or more tools
    TOOL_COMPLETED    tool result back in context
    RESPONDING        about to deliver the final answer
    DONE              turn finished; back to IDLE

The loop runs in `run_turn()`: from user input to a final assistant message.

To work around the M3 model's inconsistent tool-use behavior, this runtime
includes two robustness layers:
  1. Intent-aware prompt augmentation: if the user request clearly needs a
     specific tool (math / search / todo), append a one-line constraint
     telling the model NOT to compute by hand / fabricate / claim to forget.
  2. "Talk-only" detection: if the model responds with phrases like
     "let me help..." or "我来帮你..." but emits no tool_use block, retry
     once with a stronger hint. This handles the most common M3 failure mode.
"""
from __future__ import annotations

import enum
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from agent.context import Context
from agent.llm import safe_chat
from agent.parser import ParsedResponse, build_tool_result_block, parse_response
from agent.tools import registry as global_tool_registry
from agent.trace import Trace


SYSTEM_PROMPT = """你是具备工具调用能力的 AI agent，必须严格按以下规则工作：

═══════════════════════════════════════════════════════
绝对规则（违反任何一条都是错误）：
═══════════════════════════════════════════════════════

【规则 1: 数学计算】
凡是涉及数字运算（哪怕是 1+1），必须调用 calculator 工具。
绝对禁止：在文本里写代码、手算、给"假设"答案。

【规则 2: 外部信息】
涉及天气、事实、查询的，必须调用 search 工具。
绝对禁止：凭训练数据回答（你可能过时）、说"我无法访问"。

【规则 3: 待办记录】
用户说"记住/提醒/待办/todo"时，必须调用 todo 工具。
绝对禁止：说"我没有记忆"（对话内是有状态的）。

═══════════════════════════════════════════════════════
正确行为示例（请严格模仿）：
═══════════════════════════════════════════════════════

用户: "帮我算一下 25*4+10"
→ 你必须直接输出 tool_use 块调用 calculator(expression="25*4+10")，
   不要写代码、不要先说"我来算"。

用户: "东京今天天气如何？"
→ 你必须直接输出 tool_use 块调用 search(query="东京 天气")，
   不要凭记忆编造天气数据。

用户: "帮我记住买菜"
→ 你必须直接输出 tool_use 块调用 todo(action="add", content="买菜")，
   不要用文字说"我会记住"。

═══════════════════════════════════════════════════════
记住：你的回复里要么是 tool_use 块，要么是基于工具结果的简短总结。
绝对不要光说不做。
═══════════════════════════════════════════════════════"""


# ===== Intent detection patterns (for prompt augmentation) =====
INTENT_PATTERNS: Dict[str, List[str]] = {
    "math": [
        r"\d+\s*[\+\-\*/\%]\s*\d+",          # "2+3", "25*4"
        r"(?:算|计算|求|等于|几|多少)",         # Chinese math words
        r"calculate|compute|how much|equals?",  # English math words
    ],
    "search": [
        r"(?:天气|查询|搜索|什么是|谁|哪里|哪一年|哪个)",
        r"weather|temperature|forecast|search|what is|who is|where",
    ],
    "todo": [
        r"(?:记住|待办|提醒|记下|别忘|清单|任务)",
        r"todo|remind|remember|task|list",
    ],
}


# Phrases that indicate the model SAID it would do something but didn't
# actually emit a tool_use block. Bilingual to cover both Chinese and English
# model outputs.
TALK_ONLY_PATTERNS: List[str] = [
    r"我来帮", r"让我来", r"我将", r"我先", r"我来用", r"我帮你",
    r"let me", r"i'll", r"i will", r"i can help", r"please wait",
    r"i'm going to", r"let me check", r"let me calculate",
    r"i would", r"let me look", r"i'll use", r"let me use",
]


# One-line constraint appended to user input when intent is detected
INTENT_HINTS: Dict[str, str] = {
    "math": "（请用 calculator 工具计算，不要手算、不要写代码）",
    "search": "（请用 search 工具查询，不要瞎编、不要凭记忆回答）",
    "todo": "（请用 todo 工具记录）",
}


def detect_intents(text: str) -> List[str]:
    """Return the list of tool categories the user request likely needs."""
    found: List[str] = []
    for intent, patterns in INTENT_PATTERNS.items():
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                found.append(intent)
                break
    return found


def augment_user_prompt(user_input: str) -> Tuple[str, List[str]]:
    """Append intent-specific constraint hints to the user input.

    Returns (augmented_text, detected_intents).
    """
    intents = detect_intents(user_input)
    if not intents:
        return user_input, []
    hints = " ".join(INTENT_HINTS[i] for i in intents if i in INTENT_HINTS)
    if hints:
        return f"{user_input}\n{hints}", intents
    return user_input, intents


def is_talk_only_response(text: str, intents: List[str]) -> bool:
    """Heuristic: did the model answer the question itself without calling a tool?

    Returns True when (a) the user request clearly needs a tool, AND one of:
      (b1) the model response contains talk-only phrases ("I'll do X"), OR
      (b2) the model provided an actual answer for a math / search question
           (e.g. gave a numeric result for a math problem without using the
           calculator tool) — also counts as "didn't use the tool".
    """
    if not intents:
        return False
    if not text:
        return False
    lower = text.lower()

    # (b1) Model said "I'll do X" but didn't actually do it
    if any(re.search(p, lower, re.IGNORECASE) for p in TALK_ONLY_PATTERNS):
        return True

    # (b2) Model gave an answer for a math problem (numeric or equation-like)
    if "math" in intents:
        # Numbers followed by =, or expressions, or "答案是 X" pattern
        if re.search(r"=\s*-?\d", text):
            return True
        if re.search(r"答案是[:：]?\s*-?\d", text):
            return True
        # LaTeX-style math like $25 \times 4$
        if re.search(r"\\times|\\div|\\frac|\\cdot", text):
            return True

    return False


def build_retry_hint(intents: List[str]) -> str:
    """A short follow-up user message that pressures the model to use tools."""
    if not intents:
        return "请直接调用工具，不要只用文字描述。"
    parts = []
    if "math" in intents:
        parts.append("用 calculator 工具算（不要手算）")
    if "search" in intents:
        parts.append("用 search 工具查（不要瞎编）")
    if "todo" in intents:
        parts.append("用 todo 工具记录")
    return "请直接：" + "，".join(parts) + "。不要再用文字回答。"


class State(str, enum.Enum):
    IDLE = "IDLE"
    RECEIVED = "RECEIVED"
    REASONING = "REASONING"
    TOOL_CALLING = "TOOL_CALLING"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    RESPONDING = "RESPONDING"
    DONE = "DONE"
    ERROR = "ERROR"


@dataclass
class TurnResult:
    """The outcome of a single ReAct turn (user input → final answer)."""
    final_text: str = ""
    rounds: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class AgentRuntime:
    """The ReAct Loop controller."""

    def __init__(
        self,
        session_id: str,
        context: Context,
        trace: Trace,
        max_rounds: int = None,
    ):
        self.session_id = session_id
        self.context = context
        self.trace = trace
        self.max_rounds = max_rounds if max_rounds is not None else config.MAX_ROUNDS
        self.state = State.IDLE

    # ============ state transitions ============
    def _set_state(self, new_state: State, **event_data) -> None:
        self.state = new_state
        self.trace.record(new_state.value, "state_transition", **event_data)

    # ============ main entry point ============
    def run_turn(self, user_input: str) -> TurnResult:
        """Run one full ReAct turn: user input → final assistant message.

        The runtime:
          1. Augments the user input with intent-specific tool-use hints
          2. Appends user input to context
          3. Loops: call LLM → if tool_calls, execute them and feed results back
                    → else, return the final text
          4. If the first response is "talk-only" (says "I'll do X" without
             actually calling a tool), retries once with a stronger hint.
          5. Stops on: text answer, max_rounds exceeded, or error
        """
        result = TurnResult()

        # ===== Intent-aware prompt augmentation =====
        augmented_input, intents = augment_user_prompt(user_input)
        if intents:
            self.trace.record(State.RECEIVED.value, "intent_detected",
                              intents=intents,
                              original=user_input,
                              augmented=augmented_input)

        # Initial state
        self._set_state(State.RECEIVED, content=user_input)
        # Store the ORIGINAL input in context (user typed what they typed).
        # The augmented version is sent to the LLM but not persisted, so
        # future turns don't see the constraint noise.
        self.context.append({"role": "user", "content": user_input})
        # Stamp session_id for tools that need it (e.g. todo)
        self._inject_session_id()

        # ReAct loop
        for round_idx in range(self.max_rounds):
            result.rounds = round_idx + 1
            self._set_state(State.REASONING, round=round_idx + 1)

            # ----- LLM call -----
            # On round 1, use the augmented input so the model sees the
            # constraint hint. On later rounds, use context as-is.
            messages_for_llm = list(self.context.messages)
            if round_idx == 0 and augmented_input != user_input:
                # Replace the last user message with the augmented version
                messages_for_llm[-1] = {"role": "user", "content": augmented_input}

            try:
                self.trace.record(State.REASONING.value, "llm_call",
                                  n_messages=len(messages_for_llm),
                                  augmented=(round_idx == 0 and augmented_input != user_input))
                response = safe_chat(
                    messages=messages_for_llm,
                    system=SYSTEM_PROMPT,
                    tools=global_tool_registry.schemas(),
                )
            except Exception as e:
                self._set_state(State.ERROR, error=str(e))
                result.error = f"LLM call failed: {e}"
                self.trace.record(State.ERROR.value, "error", where="llm", error=str(e))
                return result

            parsed = parse_response(response)
            self.trace.record(
                State.REASONING.value,
                "llm_response",
                stop_reason=parsed.stop_reason,
                text_preview=parsed.text[:120] + ("..." if len(parsed.text) > 120 else ""),
                n_tool_calls=len(parsed.tool_calls),
                thinking_preview=parsed.thinking[:80] + ("..." if len(parsed.thinking) > 80 else ""),
            )

            # ===== Talk-only retry layer =====
            # If round 1 produced no tool calls but the user clearly needed a
            # tool and the model talked about doing it, retry once with a
            # stronger prompt before giving up.
            if (
                round_idx == 0
                and not parsed.has_tool_calls
                and is_talk_only_response(parsed.text, intents)
            ):
                retry_hint = build_retry_hint(intents)
                self.trace.record(State.REASONING.value, "talk_only_retry",
                                  detected_intents=intents, hint=retry_hint)
                # Build retry messages: drop the assistant's talk-only reply
                # (don't pollute context), and inject a stronger user message.
                retry_messages = list(self.context.messages) + [
                    {"role": "user", "content": retry_hint},
                ]
                try:
                    response = safe_chat(
                        messages=retry_messages,
                        system=SYSTEM_PROMPT,
                        tools=global_tool_registry.schemas(),
                    )
                    parsed = parse_response(response)
                    self.trace.record(
                        State.REASONING.value,
                        "llm_response_after_retry",
                        stop_reason=parsed.stop_reason,
                        n_tool_calls=len(parsed.tool_calls),
                        text_preview=parsed.text[:120],
                    )
                except Exception as e:
                    # Retry failed — fall through to normal handling
                    self.trace.record(State.ERROR.value, "retry_failed",
                                      error=str(e))

            # Persist assistant turn in context
            self.context.append({"role": "assistant", "content": response["content"]})

            # ----- branch: tool calls vs final answer -----
            if not parsed.has_tool_calls:
                self._set_state(State.RESPONDING, final_text=parsed.text)
                result.final_text = parsed.text
                self._set_state(State.DONE, rounds=result.rounds)
                # Maybe compress
                self.context.maybe_compress()
                return result

            # ----- execute tool calls -----
            self._set_state(State.TOOL_CALLING,
                            tools=[tc["name"] for tc in parsed.tool_calls])
            tool_result_blocks: List[Dict[str, Any]] = []

            for tc in parsed.tool_calls:
                tc_record = {
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                }
                result.tool_calls.append(tc_record)
                self.trace.record(State.TOOL_CALLING.value, "tool_call",
                                  name=tc["name"], input=tc["input"])

                tool = global_tool_registry.get(tc["name"])
                if tool is None:
                    output = f"Error: unknown tool '{tc['name']}'."
                else:
                    try:
                        # Auto-inject session_id if tool wants it
                        kwargs = dict(tc["input"])
                        if tc["name"] == "todo":
                            kwargs.setdefault("session_id", self.session_id)
                        output = tool.execute(**kwargs)
                    except Exception as e:
                        output = f"Error: tool '{tc['name']}' failed: {e}"
                        self.trace.record(State.ERROR.value, "tool_error",
                                          name=tc["name"], error=str(e))

                # If the tool call was synthesized locally from XML, the API
                # does NOT know the tool_use_id, so we can't send a real
                # tool_result block back. Encode the result as plain text in
                # the next user message instead.
                if parsed.synthesized_calls:
                    tool_result_blocks.append({
                        "type": "text",
                        "text": f"[Tool result for {tc['name']}({tc['input']})]:\n{output}",
                    })
                else:
                    tool_result_blocks.append(
                        build_tool_result_block(tc["id"], output)
                    )
                self.trace.record(State.TOOL_COMPLETED.value, "tool_result",
                                  name=tc["name"], result_preview=output[:120])

            # Feed tool results back into context as a user message
            self._set_state(State.TOOL_COMPLETED, n_results=len(tool_result_blocks))
            if parsed.synthesized_calls:
                # synthesized path: plain text only — no tool_result blocks
                text_content = "\n\n".join(
                    b["text"] for b in tool_result_blocks if b.get("type") == "text"
                )
                self.context.append({
                    "role": "user",
                    "content": f"Tool results:\n{text_content}",
                })
            else:
                self.context.append({"role": "user", "content": tool_result_blocks})

            # Compression check between rounds
            self.context.maybe_compress()

        # ----- loop exhausted -----
        self._set_state(State.ERROR, error=f"max_rounds ({self.max_rounds}) reached")
        result.error = f"Reached max_rounds ({self.max_rounds}) without a final answer."
        return result

    def _inject_session_id(self) -> None:
        """Ensure todo-style tools can read the current session id.

        Currently todo reads session_id from the input kwargs; we add it as a
        meta message in the trace for visibility."""
        self.trace.record(State.RECEIVED.value, "session_meta",
                          session_id=self.session_id, n_messages=len(self.context))