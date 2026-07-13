"""End-to-end-ish tests for the ReAct Loop with a fake LLM.

We don't call a real LLM here — instead we monkeypatch agent.llm.chat
to return canned responses. This lets us verify the state machine
without burning API tokens.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.context import Context
from agent.runtime import AgentRuntime
from agent.tools import registry  # ensure tools are registered
from agent.trace import Trace


def _mock_response_tool_call(name: str, tool_input: dict, call_id: str = "call_x"):
    return {
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": f"I'll use {name}."},
            {"type": "tool_use", "id": call_id, "name": name, "input": tool_input},
        ],
    }


def _mock_response_text(text: str):
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
    }


def test_single_tool_call_then_final_answer():
    call_log = []

    def fake_chat(messages, system=None, tools=None, **_):
        call_log.append([m.get("role") for m in messages])
        if len(call_log) == 1:
            return _mock_response_tool_call("calculator", {"expression": "2+2"})
        return _mock_response_text("The answer is 4.")

    rt = AgentRuntime(
        session_id="test_session",
        context=Context(),
        trace=Trace(enabled=False),
    )

    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        result = rt.run_turn("What's 2+2?")

    assert result.error is None
    assert "4" in result.final_text
    assert result.rounds == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "calculator"


def test_multiple_tool_calls_in_one_round():
    def fake_chat(messages, system=None, tools=None, **_):
        # Round 1: ask for both calculator AND todo
        return {
            "stop_reason": "tool_use",
            "content": [
                {"type": "tool_use", "id": "c1", "name": "calculator",
                 "input": {"expression": "5*6"}},
                {"type": "tool_use", "id": "c2", "name": "todo",
                 "input": {"action": "add", "content": "report"}},
            ],
        }

    rt = AgentRuntime(
        session_id="iso_test",
        context=Context(),
        trace=Trace(enabled=False),
    )
    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        result = rt.run_turn("Compute 5*6 and add a todo.")

    # Both tools should have been dispatched
    names = {tc["name"] for tc in result.tool_calls}
    assert names == {"calculator", "todo"}
    # An assistant message containing tool_use blocks must be in context
    assistant_msgs = [m for m in rt.context.messages if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    has_tool_use = any(
        isinstance(m["content"], list) and
        any(b.get("type") == "tool_use" for b in m["content"])
        for m in assistant_msgs
    )
    assert has_tool_use, "expected an assistant message with tool_use blocks"


def test_no_tool_call_returns_text_immediately():
    rt = AgentRuntime(
        session_id="t",
        context=Context(),
        trace=Trace(enabled=False),
    )
    with patch("agent.runtime.safe_chat", return_value=_mock_response_text("Just chatting.")):
        result = rt.run_turn("Hi")
    assert result.error is None
    assert result.final_text == "Just chatting."
    assert result.rounds == 1


def test_max_rounds_is_respected():
    """If the mock keeps requesting tools, we should bail at max_rounds."""
    rt = AgentRuntime(
        session_id="t",
        context=Context(),
        trace=Trace(enabled=False),
        max_rounds=3,
    )
    with patch("agent.runtime.safe_chat",
               return_value=_mock_response_tool_call("calculator", {"expression": "1+1"})):
        result = rt.run_turn("loop")
    assert result.error is not None and "max_rounds" in result.error
    assert result.rounds == 3


def test_unknown_tool_returns_error_to_llm():
    def fake_chat(messages, system=None, tools=None, **_):
        # Round 1: ask for a non-existent tool. Round 2: graceful answer.
        if any(m["role"] == "user" and isinstance(m.get("content"), list)
               for m in messages):
            return _mock_response_text("Sorry, couldn't do it.")
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "x", "name": "no_such_tool",
                         "input": {}}],
        }

    rt = AgentRuntime(
        session_id="t",
        context=Context(),
        trace=Trace(enabled=False),
    )
    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        result = rt.run_turn("do something")
    assert "Sorry" in result.final_text
    # Tool result for unknown tool went back to LLM
    user_msgs = [m for m in rt.context.messages if m["role"] == "user"]
    last_user = user_msgs[-1]
    assert isinstance(last_user["content"], list)
    assert last_user["content"][0]["type"] == "tool_result"
    assert "unknown tool" in last_user["content"][0]["content"]


def test_llm_failure_returns_error_result():
    rt = AgentRuntime(
        session_id="t",
        context=Context(),
        trace=Trace(enabled=False),
    )
    def boom(**_):
        raise RuntimeError("network down")
    with patch("agent.runtime.safe_chat", side_effect=boom):
        result = rt.run_turn("hi")
    assert result.error is not None
    assert "network down" in result.error