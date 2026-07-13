"""Session management — one session per CLI window.

Sessions are persisted as JSON files under SESSION_DIR. Each session
stores its message context and trace log. Different session_ids are
fully independent — there is no shared mutable state.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.context import Context
from agent.trace import Trace


@dataclass
class Session:
    """One independent conversation session."""
    session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    title: str = ""
    context: Context = field(default_factory=Context)
    trace: Trace = field(default_factory=Trace)
    meta: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "context": self.context.to_dict(),
            "trace": self.trace.to_json(),
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Session":
        s = cls(
            session_id=d["session_id"],
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            title=d.get("title", ""),
            meta=d.get("meta", {}),
        )
        s.context = Context.from_dict(d.get("context", {}))
        s.trace = Trace.from_json(d.get("trace", "[]"))
        return s


class SessionManager:
    """File-backed session store."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def new_session(self, title: str = "") -> Session:
        sid = f"session_{uuid.uuid4().hex[:12]}"
        s = Session(session_id=sid, title=title or f"Session {time.strftime('%Y-%m-%d %H:%M')}")
        self.save(s)
        return s

    def save(self, session: Session) -> None:
        session.touch()
        path = self._path(session.session_id)
        path.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, session_id: str) -> Optional[Session]:
        path = self._path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Session.from_dict(data)

    def list_sessions(self) -> List[Dict[str, Any]]:
        items = []
        for p in self.base_dir.glob("session_*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                items.append({
                    "session_id": d["session_id"],
                    "title": d.get("title", ""),
                    "updated_at": d.get("updated_at", 0),
                    "n_messages": len(d.get("context", {}).get("messages", [])),
                })
            except Exception:
                continue
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return items

    def _path(self, session_id: str) -> Path:
        if not session_id.startswith("session_"):
            session_id = f"session_{session_id}"
        return self.base_dir / f"{session_id}.json"