"""CLI entry point — one session per CLI invocation.

Usage:
    python main.py                       # start a new session
    python main.py --resume <session_id> # resume an existing session
    python main.py --list                # list all sessions
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Make 'agent' package importable when running from code/
sys.path.insert(0, str(Path(__file__).parent))

import config
# Importing the tool modules registers them with the global registry
# via their @register_tool decorator. The order matters.
import tools.calculator  # noqa: F401
import tools.search  # noqa: F401
import tools.todo  # noqa: F401
from agent.runtime import AgentRuntime
from agent.session import Session, SessionManager


BANNER = """
╔══════════════════════════════════════════════════════╗
║  Agent Runtime · minimal viable Agent from scratch    ║
║  Model: {model:<46}║
║  Session: {sid:<44}║
╚══════════════════════════════════════════════════════╝
""".strip()


HELP_TEXT = """
Commands (start a line with '/' to use):
  /new              start a fresh session (saves current)
  /list             list all sessions
  /switch <id>      switch to another session
  /state            show current context state
  /trace [on|off]   toggle verbose trace
  /compress         force context compression
  /quit             save and exit

Otherwise just type your message and press Enter.
""".strip()


def _print_banner(session: Session) -> None:
    print(BANNER.format(model=config.LLM_MODEL, sid=session.session_id))


def _build_runtime(session: Session, verbose: bool = False) -> AgentRuntime:
    if verbose:
        session.trace.verbose = True
        session.trace.enabled = True
    return AgentRuntime(
        session_id=session.session_id,
        context=session.context,
        trace=session.trace,
    )


def _handle_command(line: str, sm: SessionManager, current: Session) -> tuple[str, Session]:
    """Handle a slash command. Returns (action, new_session_or_current).

    action in {"continue", "quit", "switched"}

    Accepts both "/switch ID" and "/switch<ID>" forms (with or without space,
    with or without <>/() separators).
    """
    line = line.strip()
    # Split the command name from any attached arg.
    # "/switch<id>" → cmd="/switch", arg="<id>"
    # "/switch ID" → cmd="/switch", arg="ID"
    m = re.match(r"^/([a-zA-Z]+)(.*)$", line)
    if not m:
        return ("continue", current)
    cmd = "/" + m.group(1).lower()
    rest = m.group(2).strip()
    # Strip common arg delimiters like <>, (), []
    arg = re.sub(r"^[<(\[]+|[>)\]]+$", "", rest).strip()
    if not arg and " " in rest:
        arg = rest.split(maxsplit=1)[-1]

    if cmd == "/quit":
        sm.save(current)
        print(f"Session saved: {current.session_id}")
        return ("quit", current)

    if cmd == "/new":
        sm.save(current)
        s = sm.new_session(title="Ad-hoc CLI session")
        print(f"Started new session: {s.session_id}")
        return ("switched", s)

    if cmd == "/list":
        items = sm.list_sessions()
        if not items:
            print("(no sessions yet)")
        else:
            print(f"{'Session ID':<30} {'Title':<24} {'Msgs':<6} Updated")
            for it in items:
                print(f"{it['session_id']:<30} {it['title'][:22]:<24} {it['n_messages']:<6} "
                      f"{it['updated_at']:.0f}")
        return ("continue", current)

    if cmd == "/switch" and arg:
        s = sm.load(arg.strip())
        if s is None:
            print(f"No session with id '{arg}'")
            return ("continue", current)
        sm.save(current)
        print(f"Switched to session: {s.session_id}")
        return ("switched", s)

    if cmd == "/state":
        print(f"Session: {current.session_id}")
        print(f"Title: {current.title}")
        print(f"Messages in context: {len(current.context)}")
        print(f"Trace events: {len(current.trace.events)}")
        return ("continue", current)

    if cmd == "/trace":
        if arg == "on":
            current.trace.verbose = True
            current.trace.enabled = True
            print("Trace: verbose ON")
        elif arg == "off":
            current.trace.verbose = False
            current.trace.enabled = False
            print("Trace: OFF")
        else:
            current.trace.enabled = not current.trace.enabled
            print(f"Trace: {'ON' if current.trace.enabled else 'OFF'}")
        return ("continue", current)

    if cmd == "/compress":
        before = len(current.context)
        current.context.maybe_compress()
        after = len(current.context)
        print(f"Compressed: {before} → {after} messages")
        return ("continue", current)

    if cmd == "/help":
        print(HELP_TEXT)
        return ("continue", current)

    print(f"Unknown command: {cmd}. Type /help for the list.")
    return ("continue", current)


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal viable Agent CLI")
    parser.add_argument("--resume", help="Resume a session by id")
    parser.add_argument("--list", action="store_true", help="List sessions and exit")
    parser.add_argument("--trace", action="store_true", help="Start with verbose trace")
    args = parser.parse_args()

    sm = SessionManager(config.SESSION_DIR)

    if args.list:
        items = sm.list_sessions()
        if not items:
            print("(no sessions yet)")
        else:
            print(f"{'Session ID':<30} {'Title':<24} {'Msgs':<6}")
            for it in items:
                print(f"{it['session_id']:<30} {it['title'][:22]:<24} {it['n_messages']:<6}")
        return 0

    # Resolve session
    if args.resume:
        s = sm.load(args.resume)
        if s is None:
            print(f"No session with id '{args.resume}'. Starting a new one.")
            s = sm.new_session()
    else:
        s = sm.new_session()

    _print_banner(s)
    print(HELP_TEXT)
    print()

    runtime = _build_runtime(s, verbose=args.trace)
    current = s

    # Main loop
    while True:
        try:
            line = input(f"[{current.session_id[-8:]}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sm.save(current)
            print(f"Session saved: {current.session_id}")
            return 0

        if not line:
            continue

        if line.startswith("/"):
            action, current = _handle_command(line, sm, current)
            if action == "quit":
                return 0
            if action == "switched":
                runtime = _build_runtime(current, verbose=args.trace)
            continue

        # Regular user message → run one ReAct turn
        result = runtime.run_turn(line)
        print()
        if result.error:
            print(f"[error] {result.error}")
        else:
            print(f"[assistant] {result.final_text}")
        print(f"[trace] rounds={result.rounds}, tool_calls={len(result.tool_calls)}")
        print()
        # Persist after every turn
        sm.save(current)


if __name__ == "__main__":
    sys.exit(main())