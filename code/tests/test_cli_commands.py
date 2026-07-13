"""Tests for the CLI command parser — verify /switch and other commands
accept various argument formats (with/without space, with/without brackets).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as cli_main  # noqa: E402
from agent.session import SessionManager  # noqa: E402


def _setup():
    """Create a fresh session manager and current session."""
    td = tempfile.mkdtemp()
    sm = SessionManager(Path(td))
    current = sm.new_session()
    return sm, current


def test_switch_accepts_space_form():
    sm, current = _setup()
    other = sm.new_session()
    action, _ = cli_main._handle_command(f"/switch {other.session_id}", sm, current)
    # The session exists, so it should switch.
    assert action == "switched"


def test_switch_accepts_angle_bracket_form():
    sm, current = _setup()
    other = sm.new_session()
    action, _ = cli_main._handle_command(f"/switch<{other.session_id}>", sm, current)
    assert action == "switched"


def test_switch_accepts_paren_bracket_form():
    sm, current = _setup()
    other = sm.new_session()
    action, _ = cli_main._handle_command(f"/switch({other.session_id})", sm, current)
    assert action == "switched"


def test_switch_accepts_short_id():
    """The session_id may be entered as 'session_xxx' or just 'xxx'."""
    sm, current = _setup()
    other = sm.new_session()
    short_id = other.session_id.replace("session_", "")
    action, _ = cli_main._handle_command(f"/switch<{short_id}>", sm, current)
    # The CLI's SessionManager.load auto-prefixes "session_" if missing,
    # so this should succeed.
    assert action == "switched"


def test_switch_with_nonexistent_id_returns_continue():
    """Switching to a non-existent session should fail gracefully."""
    sm, current = _setup()
    action, _ = cli_main._handle_command("/switch<session_nonexistent>", sm, current)
    assert action == "continue"


def test_switch_actually_switches_when_session_exists():
    sm, current = _setup()
    other = sm.new_session()
    action, new_current = cli_main._handle_command(
        f"/switch {other.session_id}", sm, current
    )
    assert action == "switched"
    assert new_current.session_id == other.session_id


def test_trace_accepts_arg_with_brackets():
    sm, current = _setup()
    action, _ = cli_main._handle_command("/trace<on>", sm, current)
    assert action == "continue"
    assert current.trace.verbose is True


def test_trace_accepts_arg_with_space():
    sm, current = _setup()
    action, _ = cli_main._handle_command("/trace off", sm, current)
    assert action == "continue"


def test_help_still_works():
    sm, current = _setup()
    action, _ = cli_main._handle_command("/help", sm, current)
    assert action == "continue"


def test_quit_still_works():
    sm, current = _setup()
    action, _ = cli_main._handle_command("/quit", sm, current)
    assert action == "quit"


def test_unknown_command_doesnt_crash():
    sm, current = _setup()
    action, _ = cli_main._handle_command("/nonsense foo", sm, current)
    assert action == "continue"


def test_non_slash_input_doesnt_crash():
    sm, current = _setup()
    # Normal text input won't go through _handle_command (CLI checks the
    # slash first), but verify the parser handles it gracefully anyway.
    action, _ = cli_main._handle_command("hello world", sm, current)
    assert action == "continue"