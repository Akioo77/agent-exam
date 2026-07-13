"""Tests for the todo tool — covers add, list, complete, remove."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.todo import TodoTool, _get_store, _set_store


SESSION = "test_session_abc"


def setup_function(fn):
    _set_store(SESSION, [])


def test_add_then_list():
    t = TodoTool()
    out = t.execute(action="add", content="buy milk", session_id=SESSION)
    assert "Added todo" in out
    out = t.execute(action="list", session_id=SESSION)
    assert "buy milk" in out


def test_complete_marks_done():
    t = TodoTool()
    add_out = t.execute(action="add", content="read book", session_id=SESSION)
    todo_id = add_out.split("[")[1].split("]")[0]
    t.execute(action="complete", item_id=todo_id, session_id=SESSION)
    listed = t.execute(action="list", session_id=SESSION)
    assert "done" in listed


def test_remove_deletes_item():
    t = TodoTool()
    add_out = t.execute(action="add", content="pay bill", session_id=SESSION)
    todo_id = add_out.split("[")[1].split("]")[0]
    t.execute(action="remove", item_id=todo_id, session_id=SESSION)
    listed = t.execute(action="list", session_id=SESSION)
    assert "pay bill" not in listed


def test_add_without_content_returns_error():
    out = TodoTool().execute(action="add", content="", session_id=SESSION)
    assert "Error" in out


def test_complete_unknown_id_returns_error():
    out = TodoTool().execute(action="complete", item_id="nope", session_id=SESSION)
    assert "Error" in out


def test_unknown_action_returns_error():
    out = TodoTool().execute(action="nuke", session_id=SESSION)
    assert "Error" in out