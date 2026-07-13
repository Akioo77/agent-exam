"""Todo tool — manage a personal todo list within a session.

Stores todos in the session state so they persist across user turns.
The tool reads/writes from a thread-local store keyed by session_id.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Dict, List

from agent.tools import Tool, register_tool


# ===== In-memory todo store, keyed by session_id =====
_store_lock = threading.Lock()
_store: Dict[str, List[Dict[str, str]]] = {}


def _set_store(session_id: str, todos: List[Dict[str, str]]) -> None:
    with _store_lock:
        _store[session_id] = todos


def _get_store(session_id: str) -> List[Dict[str, str]]:
    with _store_lock:
        return list(_store.get(session_id, []))


@register_tool
class TodoTool(Tool):
    name = "todo"
    description = (
        "Manage a personal todo list scoped to the current session. "
        "Actions: add, list, complete, remove. "
        "Use this when the user asks to remember a task, list pending tasks, "
        "mark something done, or remove an item."
    )

    # We pass session_id through a context object set by the runtime
    _session_id: str = "default"

    def execute(
        self,
        action: str,
        content: str = "",
        item_id: str = "",
        session_id: str = "default",
    ) -> str:
        """Manage todos.

        Args:
            action: One of 'add', 'list', 'complete', 'remove'.
            content: For 'add': the task description.
            item_id: For 'complete'/'remove': the todo id.
            session_id: Internal use — set by the runtime.

        Returns:
            A human-readable summary of the operation result.
        """
        todos = _get_store(session_id)

        if action == "add":
            if not content.strip():
                return "Error: 'content' is required when adding a todo."
            new_item = {
                "id": f"todo_{uuid.uuid4().hex[:8]}",
                "content": content.strip(),
                "status": "pending",
                "created_at": str(int(time.time())),
            }
            todos.append(new_item)
            _set_store(session_id, todos)
            return f"Added todo [{new_item['id']}]: {new_item['content']}"

        if action == "list":
            if not todos:
                return "No todos in this session."
            lines = ["Current todos:"]
            for t in todos:
                marker = "✓" if t["status"] == "done" else "•"
                lines.append(f"  {marker} [{t['id']}] {t['content']} ({t['status']})")
            return "\n".join(lines)

        if action == "complete":
            for t in todos:
                if t["id"] == item_id:
                    t["status"] = "done"
                    _set_store(session_id, todos)
                    return f"Marked [{item_id}] as done."
            return f"Error: no todo with id '{item_id}'."

        if action == "remove":
            new_todos = [t for t in todos if t["id"] != item_id]
            if len(new_todos) == len(todos):
                return f"Error: no todo with id '{item_id}'."
            _set_store(session_id, new_todos)
            return f"Removed [{item_id}]."

        return f"Error: unknown action '{action}'. Use add/list/complete/remove."