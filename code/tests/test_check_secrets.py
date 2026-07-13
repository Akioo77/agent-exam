"""Tests for the secret scanner."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import tempfile
import os

from check_secrets import is_placeholder, scan_file


def test_is_placeholder_true_for_dots():
    assert is_placeholder("export ANTHROPIC_API_KEY=sk-...")
    assert is_placeholder("api_key = 'sk-...'")


def test_is_placeholder_true_for_your_key_here():
    assert is_placeholder("ANTHROPIC_API_KEY=sk-your-key-here")


def test_is_placeholder_false_for_real_key():
    assert not is_placeholder("api_key = 'sk-cp-abcdef1234567890ABCDEF1234567890XYZ'")


def test_scan_catches_openai_key():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('key = "sk-cp-DC19nDFKewgWcrZvSok2dhuCbbSNwYBjYmMLnpDq5b6smVm7DOuETzsw6t9VMCkEBUiCJn35UJQlIFcgsfwbmTqCqhPPpna6rMwRAwAc2Ks-8VOGOmRbCEs"\n')
        tmp = f.name
    try:
        findings = scan_file(Path(tmp))
        assert len(findings) >= 1
        names = {f[2] for f in findings}
        assert any("OpenAI" in n or "API key" in n for n in names)
    finally:
        os.unlink(tmp)


def test_scan_catches_github_token():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"\n')
        tmp = f.name
    try:
        findings = scan_file(Path(tmp))
        assert len(findings) >= 1
        assert any("GitHub" in f[2] for f in findings)
    finally:
        os.unlink(tmp)


def test_scan_ignores_placeholders():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('key = "sk-..."\n')
        f.write('key2 = "sk-your-key-here"\n')
        tmp = f.name
    try:
        findings = scan_file(Path(tmp))
        assert findings == []
    finally:
        os.unlink(tmp)


def test_scan_catches_hardcoded_password():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('password = "SuperSecretPass123"\n')
        tmp = f.name
    try:
        findings = scan_file(Path(tmp))
        assert any("password" in f[2].lower() for f in findings)
    finally:
        os.unlink(tmp)


def test_scan_ignores_short_strings():
    """Don't flag short strings as passwords."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('password = "abc"\n')   # too short
        f.write('x = 42\n')              # number, not a password
        tmp = f.name
    try:
        findings = scan_file(Path(tmp))
        assert findings == []
    finally:
        os.unlink(tmp)