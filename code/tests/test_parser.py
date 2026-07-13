"""Tests for the parser — no LLM needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.parser import build_tool_result_block, parse_response


def test_parse_text_only_response():
    resp = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "Hello there."}],
    }
    p = parse_response(resp)
    assert p.text == "Hello there."
    assert not p.has_tool_calls
    assert p.stop_reason == "end_turn"


def test_parse_tool_use_response():
    resp = {
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "Let me check."},
            {"type": "tool_use", "id": "call_1", "name": "calculator",
             "input": {"expression": "2+2"}},
        ],
    }
    p = parse_response(resp)
    assert p.text == "Let me check."
    assert p.has_tool_calls
    assert len(p.tool_calls) == 1
    assert p.tool_calls[0]["name"] == "calculator"
    assert p.tool_calls[0]["input"]["expression"] == "2+2"


def test_parse_thinking_block():
    resp = {
        "stop_reason": "end_turn",
        "content": [
            {"type": "thinking", "thinking": "Reasoning internally..."},
            {"type": "text", "text": "Final answer."},
        ],
    }
    p = parse_response(resp)
    assert p.thinking == "Reasoning internally..."
    assert p.text == "Final answer."


def test_build_tool_result_block():
    block = build_tool_result_block("call_x", "42")
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "call_x"
    assert block["content"] == "42"


def test_parse_empty_content():
    p = parse_response({"stop_reason": "end_turn", "content": []})
    assert p.text == ""
    assert not p.has_tool_calls


def test_parse_xml_tool_use_fallback():
    """Some endpoints return <tool_use>{...}</tool_use> embedded in text."""
    resp = {
        "stop_reason": "end_turn",  # model lied about stop_reason
        "content": [{
            "type": "text",
            "text": '我来帮你加。\n<tool_use>\n{"name": "todo", "input": {"action": "add", "content": "买菜"}}\n</tool_use>\n好的。'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert len(p.tool_calls) == 1
    assert p.tool_calls[0]["name"] == "todo"
    assert p.tool_calls[0]["input"]["action"] == "add"
    assert p.tool_calls[0]["input"]["content"] == "买菜"
    # The <tool_use> tag is stripped from the user-visible text
    assert "<tool_use>" not in p.text
    assert "我来帮你加" in p.text
    # stop_reason is corrected
    assert p.stop_reason == "tool_use"


def test_parse_multiple_xml_tool_uses():
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": 'multi:\n<tool_use>{"name": "a", "input": {"x": 1}}</tool_use> and <tool_use>{"name": "b", "input": {"y": 2}}</tool_use>'
        }],
    }
    p = parse_response(resp)
    assert len(p.tool_calls) == 2
    names = {tc["name"] for tc in p.tool_calls}
    assert names == {"a", "b"}


def test_parse_xml_tool_use_string_input():
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '<tool_use>{"name": "search", "input": "{\\"query\\": \\"weather\\"}"}</tool_use>'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "search"
    assert p.tool_calls[0]["input"] == {"query": "weather"}


def test_parse_xml_tool_name_variant_json_params():
    """Variant 2: <tool_name>NAME</tool_name><parameters>{json}</parameters>"""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '<tool_name>todo</tool_name><parameters>{"action": "add", "content": "买菜"}</parameters>'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "todo"
    assert p.tool_calls[0]["input"]["action"] == "add"
    assert p.tool_calls[0]["input"]["content"] == "买菜"
    assert "<tool_name>" not in p.text
    assert "<parameters>" not in p.text


def test_parse_xml_tool_name_variant_kv_params():
    """Variant 2 KV: <tool_name>NAME</tool_name><parameters><k>v</k></parameters>"""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '<tool_name>calculator</tool_name><parameters><expression>2+3</expression></parameters>'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "calculator"
    assert p.tool_calls[0]["input"]["expression"] == "2+3"


def test_parse_bare_json_with_tool_key():
    """Variant 3: bare JSON in text with 'tool' field."""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '{"tool": "calculator", "action": "compute", "expression": "25*4+10"}'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "calculator"
    # Both "action" and "expression" should be folded into input
    inp = p.tool_calls[0]["input"]
    assert inp.get("expression") == "25*4+10"
    assert "tool" not in inp
    assert p.stop_reason == "tool_use"


def test_parse_bare_json_todo_format():
    """Variant 3 with todo tool."""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '{"tool": "todo", "action": "add", "content": "买菜"}'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "todo"
    inp = p.tool_calls[0]["input"]
    assert inp.get("action") == "add"
    assert inp.get("content") == "买菜"


def test_parse_bare_json_strips_from_text():
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": 'I will help. {"tool": "search", "query": "weather"} Thanks.'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "search"
    assert p.tool_calls[0]["input"]["query"] == "weather"
    # JSON blob stripped from user-visible text
    assert "{" not in p.text
    assert "I will help" in p.text
    assert "Thanks" in p.text


def test_parse_scattered_xml_tags():
    """Variant 4: scattered XML tags without a <parameters> wrapper."""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '<tool_name>todo</tool_name>\n<action>add</action>\n<content>买菜</content>'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "todo"
    inp = p.tool_calls[0]["input"]
    assert inp["action"] == "add"
    assert inp["content"] == "买菜"
    # All tags stripped from visible text
    assert "<tool_name>" not in p.text
    assert "<action>" not in p.text
    assert "<content>" not in p.text


def test_parse_openai_style_function_call():
    """Variant 5: OpenAI-style function call JSON in text."""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '{"type":"function","name":"calculator","arguments":{"expression": "25*4+10"}}'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "calculator"
    assert p.tool_calls[0]["input"]["expression"] == "25*4+10"
    # JSON stripped from visible text
    assert "{" not in p.text


def test_parse_openai_style_with_input_key():
    """Variant 5b: same format but with 'input' instead of 'arguments'."""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '{"type":"function","name":"search","input":{"query":"weather"}}'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "search"
    assert p.tool_calls[0]["input"]["query"] == "weather"


def test_parse_anthropic_native_json_in_text():
    """Variant 3b: Anthropic-native JSON shape in text (not tool_use block)."""
    resp = {
        "stop_reason": "end_turn",
        "content": [{
            "type": "text",
            "text": '{"name": "calculator", "input": {"expression": "25*4+10"}}'
        }],
    }
    p = parse_response(resp)
    assert p.has_tool_calls
    assert p.tool_calls[0]["name"] == "calculator"
    assert p.tool_calls[0]["input"]["expression"] == "25*4+10"
    # stop_reason corrected
    assert p.stop_reason == "tool_use"