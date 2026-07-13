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
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config
from agent.context import Context
from agent.llm import safe_chat
from agent.parser import ParsedResponse, build_tool_result_block, parse_response
from agent.tools import registry as global_tool_registry
from agent.trace import Trace


SYSTEM_PROMPT = """You are a helpful AI agent with access to tools.

You follow the ReAct pattern: reason about what to do, optionally call tools, \
observe results, and produce a final answer when ready.

CRITICAL RULES (must follow):
1. For ANY math, even simple arithmetic, you MUST call the calculator tool. \
Never write Python code or compute by hand.
2. For ANY external information (weather, news, facts), you MUST call the search tool.
3. For remembering tasks, you MUST call the todo tool — never claim you can't remember.
4. When you need a tool, respond with a tool_use block directly. Do not write code in text.
5. After receiving tool results, summarize them concisely for the user.

If a tool fails, try again or use a different tool. Never say you cannot do something \
if a relevant tool is available."""


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
          1. Appends user input to context
          2. Loops: call LLM → if tool_calls, execute them and feed results back
                    → else, return the final text
          3. Stops on: text answer, max_rounds exceeded, or error
        """
        result = TurnResult()

        # Initial state
        self._set_state(State.RECEIVED, content=user_input)
        self.context.append({"role": "user", "content": user_input})
        # Stamp session_id for tools that need it (e.g. todo)
        self._inject_session_id()

        # ReAct loop
        for round_idx in range(self.max_rounds):
            result.rounds = round_idx + 1
            self._set_state(State.REASONING, round=round_idx + 1)

            # ----- LLM call -----
            try:
                self.trace.record(State.REASONING.value, "llm_call",
                                  n_messages=len(self.context))
                response = safe_chat(
                    messages=self.context.messages,
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