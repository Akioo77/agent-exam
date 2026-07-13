"""Tests for the search tool."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.search import SearchTool


def test_search_weather_returns_results():
    out = SearchTool().execute(query="weather tokyo")
    assert "Search results" in out
    assert "Tokyo" in out or "tokyo" in out


def test_search_unknown_keyword_falls_back():
    out = SearchTool().execute(query="some obscure topic xyz")
    assert "Search results" in out
    assert "some obscure topic xyz" in out


def test_search_max_results_limits_output():
    out = SearchTool().execute(query="python", max_results=1)
    # exactly one result entry
    numbered = [ln for ln in out.split("\n") if ln.strip().startswith(("1.", "2.", "3."))]
    assert len(numbered) == 1