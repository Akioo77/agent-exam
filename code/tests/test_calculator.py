"""Tests for the calculator tool — pure unit tests, no LLM needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.calculator import CalculatorTool


def test_simple_addition():
    assert CalculatorTool().execute(expression="2 + 3") == "5"


def test_complex_expression():
    assert CalculatorTool().execute(expression="(1 + 2) ** 3") == "27"


def test_division():
    out = CalculatorTool().execute(expression="10 / 4")
    assert out == "2.5"


def test_division_by_zero():
    out = CalculatorTool().execute(expression="1/0")
    assert "Error" in out and "division by zero" in out


def test_invalid_expression():
    out = CalculatorTool().execute(expression="__import__('os')")
    assert out.startswith("Error")