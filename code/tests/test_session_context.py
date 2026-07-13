"""Tests for session and context management — no LLM needed."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.context import Context
from agent.session import Session, SessionManager


def test_context_append_and_len():
    ctx = Context()
    ctx.append({"role": "user", "content": "hi"})
    ctx.append({"role": "assistant", "content": "hello"})
    assert len(ctx) == 2


def test_context_compression_keeps_recent():
    ctx = Context(max_chars=2000, keep_recent=3, max_messages=100)
    # Add a long system message that triggers compression later
    ctx.append({"role": "user", "content": "x" * 1500})
    ctx.append({"role": "assistant", "content": "y" * 1500})
    for i in range(8):
        ctx.append({"role": "user", "content": f"msg {i}"})
    assert ctx.maybe_compress() is True
    # Most recent messages preserved
    last = ctx.messages[-1]
    assert last["content"] == "msg 7"


def test_session_persistence(tmp_path):
    sm = SessionManager(tmp_path)
    s = sm.new_session(title="unit test")
    s.context.append({"role": "user", "content": "hello"})
    sm.save(s)

    loaded = sm.load(s.session_id)
    assert loaded is not None
    assert loaded.session_id == s.session_id
    assert loaded.title == "unit test"
    assert len(loaded.context) == 1
    assert loaded.context.messages[0]["content"] == "hello"


def test_session_isolation(tmp_path):
    """Two sessions must not share state."""
    sm = SessionManager(tmp_path)
    s1 = sm.new_session()
    s2 = sm.new_session()
    s1.context.append({"role": "user", "content": "from s1"})
    s2.context.append({"role": "user", "content": "from s2"})
    sm.save(s1)
    sm.save(s2)

    l1 = sm.load(s1.session_id)
    l2 = sm.load(s2.session_id)
    assert l1.context.messages[0]["content"] == "from s1"
    assert l2.context.messages[0]["content"] == "from s2"


def test_list_sorders_sessions_by_updated(tmp_path):
    sm = SessionManager(tmp_path)
    a = sm.new_session()
    time.sleep(0.01)
    b = sm.new_session()
    items = sm.list_sessions()
    ids = [it["session_id"] for it in items]
    assert ids[0] == b.session_id  # b is newer
    assert ids[1] == a.session_id


def test_load_missing_returns_none(tmp_path):
    sm = SessionManager(tmp_path)
    assert sm.load("session_does_not_exist") is None