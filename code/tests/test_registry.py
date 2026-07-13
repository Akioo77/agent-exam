"""Tests for the tool registry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import agent.tools  # noqa: F401  (registers tools via @register_tool)
from agent.tools import Tool, ToolRegistry, registry
from tools.calculator import CalculatorTool
from tools.search import SearchTool
from tools.todo import TodoTool


def test_default_registry_has_three_tools():
    names = registry.list_names()
    assert "calculator" in names
    assert "search" in names
    assert "todo" in names


def test_schemas_returns_anthropic_format():
    schemas = registry.schemas()
    assert isinstance(schemas, list)
    for s in schemas:
        assert "name" in s
        assert "description" in s
        assert "input_schema" in s
        assert s["input_schema"]["type"] == "object"


def test_calculator_schema_requires_expression():
    schemas = registry.schemas()
    calc = next(s for s in schemas if s["name"] == "calculator")
    assert "expression" in calc["input_schema"]["properties"]
    assert "expression" in calc["input_schema"]["required"]


def test_separate_registry_does_not_pollute_global():
    fresh = ToolRegistry()
    assert fresh.list_names() == []
    fresh.register(CalculatorTool())
    assert fresh.list_names() == ["calculator"]
    # global registry unchanged by this list
    assert "search" in registry.list_names()


def test_register_duplicate_name_raises():
    fresh = ToolRegistry()
    fresh.register(CalculatorTool())
    try:
        fresh.register(CalculatorTool())
    except ValueError:
        return
    raise AssertionError("Expected ValueError on duplicate registration")