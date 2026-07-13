"""Calculator tool — evaluates simple math expressions safely."""
from __future__ import annotations

import ast
import operator

from agent.tools import Tool, register_tool


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(expr: str):
    """Safely evaluate a math expression. Only allows numbers and basic ops."""
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand))
    raise ValueError(f"unsupported node: {type(node).__name__}")


@register_tool
class CalculatorTool(Tool):
    name = "calculator"
    description = (
        "Evaluate a math expression and return the numeric result. "
        "Supports +, -, *, /, //, %, ** and parentheses. "
        "Use this whenever the user asks for arithmetic."
    )

    def execute(self, expression: str) -> str:
        """Evaluate a math expression.

        Args:
            expression: A math expression like "2 + 3 * 4" or "(1 + 2) ** 3".

        Returns:
            A string describing the result, e.g. '14'.
        """
        try:
            value = _safe_eval(expression)
            return f"{value}"
        except ZeroDivisionError:
            return "Error: division by zero"
        except Exception as e:
            return f"Error: could not evaluate {expression!r}: {e}"