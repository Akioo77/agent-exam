#!/usr/bin/env python3
"""Pre-commit security check.

Scans the codebase for accidentally committed secrets:
- API keys (sk-..., ghp_..., AKIA...)
- Hardcoded passwords / tokens
- Private keys (-----BEGIN ... PRIVATE KEY-----)
- .env files containing real values

Exit code 0 = clean, 1 = secrets detected.

Usage:
    python3 scripts/check_secrets.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# Regexes for common secret formats
SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "OpenAI/MiniMax API key (sk-...)"),
    (re.compile(r"sk-ant-[A-Za-z0-9-]{20,}"), "Anthropic API key (sk-ant-...)"),
    (re.compile(r"sk-or-[A-Za-z0-9-]{20,}"), "OpenRouter API key (sk-or-...)"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub personal access token (ghp_...)"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "GitHub OAuth token (gho_...)"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained PAT"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "Google API key"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "Private key block"),
    (re.compile(r"(?i)password\s*[=:]\s*['\"][^'\"\s]{8,}"), "Hardcoded password"),
    (re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"][^'\"\s]{16,}"), "Hardcoded API key"),
]

# File extensions to scan
SCAN_EXTS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".sh", ".toml", ".cfg", ".ini", ".env", ".example"}

# Files/dirs to skip
SKIP_PATHS = {".git", ".pytest_cache", "__pycache__", "node_modules", ".venv", "venv"}

# Files where secrets are EXPECTED (we list them as known-safe)
KNOWN_SAFE_PATTERNS = [
    re.compile(r"sk-\.\.\."),         # placeholder
    re.compile(r"sk-your-key-here"),  # placeholder in .env.example
]


def is_placeholder(text: str) -> bool:
    """Check whether a matched secret is actually a placeholder."""
    return any(p.search(text) for p in KNOWN_SAFE_PATTERNS)


def should_scan(path: Path) -> bool:
    if any(part in SKIP_PATHS for part in path.parts):
        return False
    if path.suffix.lower() in SCAN_EXTS:
        return True
    if path.name in (".env", ".env.example", "Dockerfile", "Makefile"):
        return True
    return False


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, snippet, pattern_name) for findings."""
    findings: list[tuple[int, str, str]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings
    for lineno, line in enumerate(content.splitlines(), start=1):
        if is_placeholder(line):
            continue
        for pattern, name in SECRET_PATTERNS:
            if pattern.search(line):
                # Trim long lines for the report
                snippet = line.strip()
                if len(snippet) > 100:
                    snippet = snippet[:50] + "..." + snippet[-30:]
                findings.append((lineno, snippet, name))
    return findings


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    print(f"Scanning {root} for secrets...")

    all_findings: list[tuple[Path, int, str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not should_scan(path):
            continue
        for lineno, snippet, name in scan_file(path):
            all_findings.append((path, lineno, snippet, name))

    if not all_findings:
        print("✓ No secrets found. Safe to commit.")
        return 0

    print(f"\n✗ Found {len(all_findings)} potential secret(s):\n")
    for path, lineno, snippet, name in all_findings:
        rel = path.relative_to(root)
        print(f"  {rel}:{lineno}  [{name}]")
        print(f"    {snippet}")
        print()
    print("→ Remove the secret, move it to .env (gitignored), or replace with a placeholder.")
    return 1


if __name__ == "__main__":
    sys.exit(main())