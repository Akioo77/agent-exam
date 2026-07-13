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

# Variant 3: {"tool": "NAME", "action": "...", ...} — bare JSON object in
# text mentioning a tool name. We scan every JSON-looking object in the text
# and pick ones whose "tool" / "name" / "function" field matches a known tool.
_KNOWN_TOOL_NAMES_HINT = r"(?:calculator|search|todo|read_docs|weather)"
_JSON_BLOB_RE = re.compile(r"\{[^{}]*\"(?:tool|name|function)\"[^{}]*\}")


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
    if name_match:
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
        # If we matched <tool_name> but found no <parameters>, fall through
        # to Variant 4 which can pick up scattered <action>/<content> tags.

    # Variant 3: bare JSON in text — {"tool": "NAME", "input": {...}}
    # or {"tool": "NAME", "action": "...", ...} with action folded into input.
    # Also handles Anthropic-native JSON in text: {"name": "...", "input": {...}}
    # which has the same schema as a tool_use content block but arrives as
    # plain text instead.
    if not tool_calls:
        # Scan for any JSON blob containing a "tool", "name", or "function" key
        # Use a brace-matching scanner so nested objects work.
        for hint_re in (
            re.compile(r"\{\s*\"tool\"\s*:"),
            re.compile(r"\{\s*\"function\"\s*:"),
            re.compile(r"\{\s*\"name\"\s*:\s*\"(?P<n>[A-Za-z_][\w]*)\"\s*,\s*\"(?:input|arguments)\"\s*:"),
        ):
            for m in hint_re.finditer(clean):
                start = m.start()
                depth = 0
                end = start
                for i, ch in enumerate(clean[start:], start=start):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end <= start:
                    continue
                blob = clean[start:end]
                parsed = _safe_json_loads(blob)
                if not isinstance(parsed, dict):
                    continue
                name = parsed.get("tool") or parsed.get("name") or parsed.get("function")
                if not isinstance(name, str) or not name:
                    continue
                inp = parsed.get("input") or parsed.get("arguments")
                if not isinstance(inp, dict):
                    inp = {}
                    # fold remaining fields
                    for k, v in parsed.items():
                        if k in ("tool", "name", "function", "type"):
                            continue
                        inp[k] = v
                if inp:
                    tool_calls.append({"name": name, "input": inp})
                    clean = (clean[:start] + clean[end:]).strip()
                    break
            if tool_calls:
                break

        if tool_calls:
            return clean, tool_calls

    # Variant 4: scattered XML tags like
    #   <tool_name>todo</tool_name>
    #   <action>add</action>
    #   <content>买菜</content>
    # The <tool_name>X</tool_name> tag is the tool name; the rest are input
    # fields. <parameters> is excluded because it's Variant 2 territory.
    tag_matches = list(_XML_PARAM_TAG_RE.finditer(clean))
    if tag_matches:
        name = ""
        inp: Dict[str, Any] = {}
        span_start = len(clean)
        span_end = 0
        for m in tag_matches:
            key = m.group(1).strip().lower()
            val = m.group(2).strip()
            if key == "tool_name":
                name = val
                span_start = min(span_start, m.start())
                span_end = max(span_end, m.end())
            elif key == "parameters":
                continue  # Variant 2; don't double-count
            else:
                inp[key] = _coerce(val)
                span_start = min(span_start, m.start())
                span_end = max(span_end, m.end())
        if name and inp:
            tool_calls.append({"name": name, "input": inp})
            clean = (clean[:span_start] + clean[span_end:]).strip()
            return clean, tool_calls

    # Variant 5: OpenAI-style function-call JSON in text
    #   {"type":"function","name":"calculator","arguments":{"expression":"25*4+10"}}
    # or with "input" instead of "arguments"
    #   {"type":"function","name":"calculator","input":{"expression":"25*4+10"}}
    # Use a brace-matching scanner since the JSON may contain nested objects.
    if not tool_calls:
        for m in re.finditer(r"\{\s*\"type\"\s*:\s*\"function\"", clean):
            start = m.start()
            depth = 0
            end = start
            for i, ch in enumerate(clean[start:], start=start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end <= start:
                continue
            blob = clean[start:end]
            parsed = _safe_json_loads(blob)
            if not isinstance(parsed, dict):
                continue
            name = parsed.get("name", "")
            inp = parsed.get("arguments", parsed.get("input", {}))
            if isinstance(inp, str):
                inp = _safe_json_loads(inp) or {}
            if name and isinstance(inp, dict) and inp:
                tool_calls.append({"name": name, "input": inp})
                clean = (clean[:start] + clean[end:]).strip()
                break

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