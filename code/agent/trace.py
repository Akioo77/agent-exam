"""Trace / structured logging for the Agent Runtime.

Each ReAct step gets a record with timestamp, state, and action.
Used both for debugging (stdout) and for the saved session file.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class TraceEvent:
    """A single traceable event."""
    timestamp: float
    state: str  # state machine state at the time
    event_type: str  # user_input, llm_call, tool_call, tool_result, llm_response, error, ...
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Trace:
    """In-memory + printable trace log."""

    def __init__(self, verbose: bool = False, enabled: bool = True):
        self.events: List[TraceEvent] = []
        self.verbose = verbose
        self.enabled = enabled

    def record(self, state: str, event_type: str, **data) -> TraceEvent:
        ev = TraceEvent(
            timestamp=time.time(),
            state=state,
            event_type=event_type,
            data=data,
        )
        self.events.append(ev)
        if self.enabled:
            self._print(ev)
        return ev

    def _print(self, ev: TraceEvent) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime(ev.timestamp))
        prefix = f"[trace {ts} | {ev.state:<14}] {ev.event_type}"
        if self.verbose:
            payload = json.dumps(ev.data, ensure_ascii=False, default=str)
            # Truncate very long payloads
            if len(payload) > 200:
                payload = payload[:200] + "..."
            print(f"{prefix}: {payload}")
        else:
            # Compact: show only key info
            key = self._summarize(ev.data)
            print(f"{prefix}: {key}")

    @staticmethod
    def _summarize(data: Dict[str, Any]) -> str:
        """Pick the most informative field for a compact log line."""
        if not data:
            return ""
        for k in ("content", "tool", "name", "result", "error", "status"):
            if k in data:
                v = str(data[k])
                return v[:80] + ("..." if len(v) > 80 else "")
        # Fallback
        first = next(iter(data.values()))
        v = str(first)
        return v[:80] + ("..." if len(v) > 80 else "")

    def to_json(self) -> str:
        return json.dumps(
            [ev.to_dict() for ev in self.events],
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Trace":
        t = cls(enabled=False)
        for ev in json.loads(raw):
            t.events.append(TraceEvent(**ev))
        return t