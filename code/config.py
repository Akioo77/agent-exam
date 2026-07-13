"""Configuration for the Agent."""
import os
from pathlib import Path

# ====== LLM Configuration ======
# MiniMax provides Anthropic-compatible API
LLM_BASE_URL = os.environ.get(
    "ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic"
)
LLM_API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY", os.environ.get("MINIMAX_API_KEY", "")
)
LLM_MODEL = os.environ.get("AGENT_MODEL", "MiniMax-M3")
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.7

# ====== Agent Configuration ======
MAX_ROUNDS = 20  # Maximum ReAct loop iterations
CONTEXT_MAX_TOKENS = 100_000  # Trigger compression threshold
CONTEXT_KEEP_RECENT_MESSAGES = 10  # When compressing, keep last N
MAX_RETRIES = 3  # LLM call retries on failure

# ====== Session Configuration ======
SESSION_DIR = Path.home() / ".agent_sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# ====== Trace Configuration ======
TRACE_ENABLED = True
TRACE_VERBOSE = False