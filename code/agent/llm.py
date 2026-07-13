"""LLM client wrapper for the Anthropic / MiniMax-compatible API."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import anthropic

import config


_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    """Get or create the global Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=config.LLM_API_KEY or "no-key",
            base_url=config.LLM_BASE_URL,
        )
    return _client


def chat(
    messages: List[Dict[str, Any]],
    system: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """Call the LLM and return the raw response dict.

    Args:
        messages: list of message dicts (Anthropic format).
        system: optional system prompt.
        tools: optional list of tool schemas.
        model: override model.
        max_tokens: override max tokens.
        temperature: override temperature.

    Returns:
        Raw API response as a dict.
    """
    client = get_client()

    kwargs: Dict[str, Any] = {
        "model": model or config.LLM_MODEL,
        "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
        "temperature": temperature if temperature is not None else config.LLM_TEMPERATURE,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools

    resp = client.messages.create(**kwargs)
    # Pydantic model → dict
    return resp.model_dump()


def safe_chat(
    messages: List[Dict[str, Any]],
    system: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Call chat() with retries on transient errors.

    Raises the last exception if all retries fail.
    """
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return chat(messages=messages, system=system, tools=tools)
        except anthropic.APIConnectionError as e:
            last_err = e
        except anthropic.APITimeoutError as e:
            last_err = e
        except anthropic.APIStatusError as e:
            # Retry only on 5xx
            if e.status_code and e.status_code < 500:
                raise
            last_err = e
        except Exception as e:
            # Unknown error — don't retry blindly
            raise

        import time
        time.sleep(0.5 * (2 ** attempt))

    assert last_err is not None
    raise last_err