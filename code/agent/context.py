"""Context management for the Agent.

Stores conversation messages, applies basic compression when
the context gets too long.

Memory policy (per the project README):
- Keep all user messages
- Keep all tool results
- Compress / drop the model's "thinking" text when over budget
- Always keep the most recent N messages untouched
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# A message is a dict: {"role": ..., "content": ..., plus optional fields}
Message = Dict[str, Any]


@dataclass
class Context:
    """The conversation context fed to the LLM.

    Stores both the raw message history (for session restore) and
    the *effective* list of messages (after compression).
    """
    messages: List[Message] = field(default_factory=list)
    max_messages: int = 80           # hard cap on stored messages
    keep_recent: int = 10            # recent messages are never compressed
    max_chars: int = 100_000         # rough char-based compression threshold

    # ----- mutation -----
    def append(self, message: Message) -> None:
        self.messages.append(message)

    def extend(self, messages: List[Message]) -> None:
        self.messages.extend(messages)

    def clear(self) -> None:
        self.messages.clear()

    def __len__(self) -> int:
        return len(self.messages)

    # ----- compression -----
    def maybe_compress(self) -> bool:
        """If over budget, compress by truncating old assistant thinking.

        Returns True if compression happened.
        """
        total = sum(self._estimate(m) for m in self.messages)
        if total <= self.max_chars and len(self.messages) <= self.max_messages:
            return False

        # Strategy: keep system + first user message (task brief), and the
        # tail of the conversation (keep_recent messages). For old assistant
        # messages with text content, replace content with a short marker.
        if len(self.messages) <= self.keep_recent + 2:
            return False

        head = self.messages[:1]               # system
        tail = self.messages[-self.keep_recent:]

        middle = self.messages[1:-self.keep_recent]
        compressed_middle: List[Message] = []
        for m in middle:
            compressed_middle.append(self._compress_message(m))

        self.messages = head + compressed_middle + tail
        return True

    def _compress_message(self, m: Message) -> Message:
        """Compress a single message — keep structure but shrink content."""
        role = m.get("role")
        if role == "assistant":
            content = m.get("content")
            if isinstance(content, str) and len(content) > 100:
                return {
                    **m,
                    "content": "[earlier response truncated for context budget]",
                }
            # If assistant used tool_use blocks, keep them (they're usually short)
            return m
        if role == "user":
            # Keep user input as-is — it's signal
            return m
        # tool_result: keep but truncate very long outputs
        if role == "user" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if block.get("type") == "tool_result":
                    text = block.get("content", "")
                    if isinstance(text, str) and len(text) > 300:
                        new_content.append({
                            **block,
                            "content": text[:300] + " ... [truncated]",
                        })
                    else:
                        new_content.append(block)
                else:
                    new_content.append(block)
            return {**m, "content": new_content}
        return m

    # ----- estimation -----
    @staticmethod
    def _estimate(m: Message) -> int:
        """Rough char-length estimate (1 token ≈ 4 chars in English/Chinese mix)."""
        c = m.get("content")
        if isinstance(c, str):
            return len(c)
        if isinstance(c, list):
            total = 0
            for b in c:
                if isinstance(b, dict):
                    total += len(str(b.get("content", ""))) + 50
                else:
                    total += len(str(b))
            return total
        return 50

    # ----- view -----
    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": self.messages,
            "max_messages": self.max_messages,
            "keep_recent": self.keep_recent,
            "max_chars": self.max_chars,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Context":
        return cls(
            messages=d.get("messages", []),
            max_messages=d.get("max_messages", 80),
            keep_recent=d.get("keep_recent", 10),
            max_chars=d.get("max_chars", 100_000),
        )