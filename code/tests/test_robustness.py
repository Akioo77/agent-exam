"""Tests for the robustness layers in agent.runtime:
- Intent detection
- Prompt augmentation
- Talk-only response detection
- Retry hint generation
- End-to-end: talk-only retry forces tool call
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import agent.tools  # noqa
import tools.calculator, tools.search, tools.todo  # noqa

from agent.context import Context
from agent.runtime import (
    AgentRuntime,
    augment_user_prompt,
    build_retry_hint,
    detect_intents,
    is_talk_only_response,
)
from agent.trace import Trace


# ===== Unit tests for the helpers =====

def test_detect_intents_math_chinese():
    assert "math" in detect_intents("帮我算一下 25*4+10")


def test_detect_intents_math_symbols():
    assert "math" in detect_intents("100 / 5 等于多少")


def test_detect_intents_math_english():
    assert "math" in detect_intents("calculate 2 + 2")


def test_detect_intents_search_chinese():
    assert "search" in detect_intents("东京今天天气如何")


def test_detect_intents_search_english():
    assert "search" in detect_intents("what is the weather")


def test_detect_intents_todo_chinese():
    assert "todo" in detect_intents("帮我记住买菜这件事")


def test_detect_intents_todo_english():
    assert "todo" in detect_intents("remind me to call john")


def test_detect_intents_none():
    """Pure chitchat shouldn't trigger any intent."""
    intents = detect_intents("你好，今天怎么样？")
    assert intents == []


def test_detect_intents_multiple():
    """A request can imply multiple tools."""
    intents = detect_intents("帮我算一下汇率，然后记到待办里")
    assert "math" in intents
    assert "todo" in intents


def test_augment_user_prompt_adds_hint_for_math():
    augmented, intents = augment_user_prompt("帮我算 2+2")
    assert "math" in intents
    assert "calculator" in augmented
    assert "不要手算" in augmented


def test_augment_user_prompt_unchanged_for_chitchat():
    augmented, intents = augment_user_prompt("你好")
    assert intents == []
    assert augmented == "你好"


def test_is_talk_only_chinese():
    assert is_talk_only_response("我来帮你计算一下", ["math"])
    assert is_talk_only_response("让我来查一下天气", ["search"])
    assert is_talk_only_response("我将使用 todo 工具", ["todo"])


def test_is_talk_only_english():
    assert is_talk_only_response("Let me calculate that", ["math"])
    assert is_talk_only_response("I'll look that up for you", ["search"])
    assert is_talk_only_response("I'll use the calculator tool", ["math"])


def test_is_talk_only_false_when_no_intent():
    """Without detected intent, don't trigger retry (might be genuine chitchat)."""
    assert not is_talk_only_response("我来帮你讲个笑话", [])


def test_is_talk_only_false_when_response_is_substantive():
    """For chitchat (no intent), don't retry even with substantive content."""
    assert not is_talk_only_response("The answer is 110.", [])


def test_is_talk_only_catches_math_with_equation():
    """If math intent and response has '= N' pattern, that's a self-answer."""
    assert is_talk_only_response("25 * 4 = 100", ["math"])
    assert is_talk_only_response("答案是：110", ["math"])


def test_is_talk_only_catches_latex_math():
    """LaTeX math expression counts as a self-answer."""
    assert is_talk_only_response("$25 \\times 4 = 100$", ["math"])


def test_build_retry_hint_math():
    hint = build_retry_hint(["math"])
    assert "calculator" in hint
    assert "不要手算" in hint


def test_build_retry_hint_multiple():
    hint = build_retry_hint(["math", "todo"])
    assert "calculator" in hint
    assert "todo" in hint


def test_build_retry_hint_empty():
    hint = build_retry_hint([])
    assert "工具" in hint  # generic fallback


# ===== Integration tests for talk-only retry =====

def _talk_only_response():
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "我来帮你算一下。"}],
    }


def _tool_use_response():
    return {
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "我来用工具。"},
            {"type": "tool_use", "id": "call_x", "name": "calculator",
             "input": {"expression": "2+2"}},
        ],
    }


def _text_only_response():
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "The answer is 4."}],
    }


def test_talk_only_triggers_retry_and_tool_call():
    """If the first response is talk-only, runtime retries and uses the tool."""
    call_count = {"n": 0}

    def fake_chat(messages, system=None, tools=None, **_):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _talk_only_response()      # round 1: talk-only
        if call_count["n"] == 2:
            return _tool_use_response()       # round 1 retry: actually calls tool
        return _text_only_response()           # round 2: done

    rt = AgentRuntime("t", Context(), Trace(enabled=False), max_rounds=5)
    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        result = rt.run_turn("帮我算 2+2")

    assert result.error is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "calculator"
    # Three LLM calls (initial + retry + final)
    assert call_count["n"] == 3


def test_no_retry_when_first_response_is_substantive():
    """If model gave an actual answer (not talk-only), don't retry."""
    call_count = {"n": 0}

    def fake_chat(messages, system=None, tools=None, **_):
        call_count["n"] += 1
        return _text_only_response()

    rt = AgentRuntime("t", Context(), Trace(enabled=False))
    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        result = rt.run_turn("The capital of France?")

    # Only one call — no intent, no retry
    assert call_count["n"] == 1
    assert "4" in result.final_text


def test_no_retry_for_pure_chitchat():
    """Greetings don't trigger retry even if response contains talk phrases."""
    call_count = {"n": 0}

    def fake_chat(messages, system=None, tools=None, **_):
        call_count["n"] += 1
        return _talk_only_response()

    rt = AgentRuntime("t", Context(), Trace(enabled=False))
    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        result = rt.run_turn("你好")

    # No intent detected → no retry even though response is talk-only
    assert call_count["n"] == 1
    assert result.error is None


def test_augmented_prompt_used_in_first_llm_call_not_stored():
    """The augmented hint goes to the LLM but is NOT saved in context."""
    sent_messages: list[list[dict]] = []

    def fake_chat(messages, system=None, tools=None, **_):
        sent_messages.append(list(messages))
        return _tool_use_response()

    rt = AgentRuntime("t", Context(), Trace(enabled=False))
    with patch("agent.runtime.safe_chat", side_effect=fake_chat):
        rt.run_turn("帮我算 2+2")

    # First LLM call: last message contains the augmentation hint
    first_call = sent_messages[0]
    last_msg = first_call[-1]
    assert "content" in last_msg
    assert "calculator" in last_msg["content"] or "不要手算" in last_msg["content"]

    # But context should NOT contain the augmentation — only the original
    original_user_msg = rt.context.messages[0]
    assert "不要手算" not in original_user_msg["content"]
    assert "帮我算 2+2" in original_user_msg["content"]