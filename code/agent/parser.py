"""Parser for Anthropic / MiniMax API responses.

Anthropic responses have:
- stop_reason: "end_turn" | "tool_use" | "max_tokens" | "stop_sequence"
- content: list of blocks:
    - {"type": "text", "text": "..."}
    - {"type": "thinking", "thinking": "..."}
    - {"type": "tool_use", "id": "...", "name": "...", "input": {...}}

Some compatible endpoints occasionally return XML-style tool_use embedded
in text blocks instead of as structured content blocks. We handle several
variants so the Agent Runtime stays robust.

This module extracts:
- final_text: the plain text response to show the user
- tool_calls: list of (id, name, input) to dispatch
- thinking: optional thinking text (for trace)
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ===== regex patterns for XML fallback variants =====

# Variant 1: <tool_use>{"name":"...","input":{...}}</tool_use>
_XML_TOOL_USE_RE = re.compile(
    r"<tool_use>\s*(\{.*?\})\s*</tool_use>", re.DOTALL
)

# Variant 2: <tool_name>NAME</tool_name><parameters>...</parameters>
_XML_TOOL_NAME_RE = re.compile(
    r"<tool_name>\s*([A-Za-z_][\w]*)\s*</tool_name>", re.IGNORECASE
)
_XML_PARAMETERS_JSON_RE = re.compile(
    r"<parameters>\s*(\{.*?\})\s*</parameters>", re.DOTALL | re.IGNORECASE
)
_XML_PARAMETERS_KV_RE = re.compile(
    r"<parameters>\s*(.*?)\s*</parameters>", re.DOTALL | re.IGNORECASE
)
_XML_PARAM_TAG_RE = re.compile(
    r"<([A-Za-z_][\w]*)>\s*(.*?)\s*</\1>", re.DOTALL
)


@dataclass
class ParsedResponse:
    text: str = ""
    thinking: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    # True for any tool_call that was synthesized locally (XML fallback).
    # These IDs are NOT known by the API and must NOT be sent back as
    # tool_result blocks — feed the result back as plain text instead.
    synthesized_calls: bool = False

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def parse_response(response: Dict[str, Any]) -> ParsedResponse:
    """Parse an Anthropic-style API response into a structured form.

    Handles:
    - Native tool_use content blocks (preferred)
    - XML <tool_use>{json}</tool_use> embedded in text (fallback)
    - XML <tool_name>NAME</tool_name><parameters>...</parameters>
    - Mixed: text + native tool_use + thinking blocks
    """
    result = ParsedResponse()
    result.raw = response
    result.stop_reason = response.get("stop_reason", "")

    content = response.get("content", [])
    if not isinstance(content, list):
        if isinstance(content, str):
            result.text = content
        return result

    text_parts: List[str] = []
    thinking_parts: List[str] = []

    for block in content:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "thinking":
            thinking_parts.append(block.get("thinking", ""))
        elif btype == "tool_use":
            result.tool_calls.append({
                "id": block.get("id", "") or _gen_call_id(),
                "name": block.get("name", ""),
                "input": block.get("input", {}),
            })

    full_text = "\n".join(p for p in text_parts if p).strip()
    result.text = full_text
    result.thinking = "\n".join(p for p in thinking_parts if p).strip()

    # ===== Fallback: scan text for XML-style tool use =====
    if not result.tool_calls:
        full_text, tcs = _scrape_xml_tool_use(full_text)
        for tc in tcs:
            result.tool_calls.append({
                "id": _gen_call_id(),
                "name": tc["name"],
                "input": tc["input"],
            })
        result.text = full_text
        if result.tool_calls and result.stop_reason == "end_turn":
            result.stop_reason = "tool_use"
            result.synthesized_calls = True

    return result


def _scrape_xml_tool_use(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Look for XML-style tool invocations in text. Return (clean_text, tool_calls).

    Tries variants in order. Strips matched XML from the returned clean text.
    """
    tool_calls: List[Dict[str, Any]] = []

    # Variant 1: <tool_use>{json}</tool_use>
    pieces: List[str] = []
    cursor = 0
    matched_any = False
    for m in _XML_TOOL_USE_RE.finditer(text):
        matched_any = True
        pieces.append(text[cursor:m.start()])
        cursor = m.end()
        payload = m.group(1)
        parsed = _safe_json_loads(payload)
        if not isinstance(parsed, dict):
            continue
        name = parsed.get("name", "")
        inp = parsed.get("input", {})
        if isinstance(inp, str):
            inp = _safe_json_loads(inp) or {}
        if name and isinstance(inp, dict):
            tool_calls.append({"name": name, "input": inp})
    pieces.append(text[cursor:])
    clean = "\n".join(p for p in pieces if p.strip()).strip()

    if tool_calls:
        return clean, tool_calls

    # Variant 2: <tool_name>NAME</tool_name><parameters>...</parameters>
    name_match = _XML_TOOL_NAME_RE.search(clean)
    if not name_match:
        return clean, tool_calls

    name = name_match.group(1).strip()
    inp: Dict[str, Any] = {}
    block_start = name_match.start()
    block_end = name_match.end()

    params_json = _XML_PARAMETERS_JSON_RE.search(clean, pos=block_end)
    params_kv = _XML_PARAMETERS_KV_RE.search(clean, pos=block_end)

    if params_json:
        parsed = _safe_json_loads(params_json.group(1))
        if isinstance(parsed, dict):
            inp = parsed
        block_end = params_json.end()
    elif params_kv:
        for tag_match in _XML_PARAM_TAG_RE.finditer(params_kv.group(1)):
            key = tag_match.group(1).strip()
            val = tag_match.group(2).strip()
            inp[key] = _coerce(val)
        block_end = params_kv.end()

    if name and inp:
        tool_calls.append({"name": name, "input": inp})

    clean = (clean[:block_start] + clean[block_end:]).strip()
    return clean, tool_calls


def _coerce(val: str) -> Any:
    """Try to interpret a string as JSON/number/bool, fallback to string."""
    parsed = _safe_json_loads(val)
    if parsed is not None:
        return parsed
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def build_tool_result_block(tool_use_id: str, content: str) -> Dict[str, Any]:
    """Build a tool_result message block to send back to the LLM."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }


def _safe_json_loads(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _gen_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:16]}"