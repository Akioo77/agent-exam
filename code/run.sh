#!/usr/bin/env bash
# Quick start for the Agent Runtime CLI.
#
# Usage:
#   ./run.sh                       # new session
#   ./run.sh --list                # list sessions
#   ./run.sh --resume <session_id> # resume a session
#   ./run.sh --trace               # verbose trace
#
# Required environment:
#   ANTHROPIC_API_KEY — your MiniMax API key
# Optional:
#   ANTHROPIC_BASE_URL — defaults to https://api.minimaxi.com/anthropic
#   AGENT_MODEL        — defaults to MiniMax-M3

set -e
cd "$(dirname "$0")"

if [[ -z "$ANTHROPIC_API_KEY" ]]; then
    echo "Error: ANTHROPIC_API_KEY env var is not set."
    echo "Export your MiniMax API key first:"
    echo "    export ANTHROPIC_API_KEY=sk-..."
    exit 1
fi

# Use python3 from PATH (no venv required for a tiny project)
exec python3 main.py "$@"