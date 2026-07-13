"""Tool registry and base class.

Implements the tool registration mechanism:
- Each tool has a name, description, and parameter Schema
- LLM uses the Schema to autonomously decide which tool to call
- Tools are executed and results are returned to the LLM
"""
from __future__ import annotations

import json
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Callable, Optional, get_type_hints


@dataclass
class ToolSchema:
    """Schema for a tool, in Anthropic-compatible format."""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema for the input

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert to Anthropic API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class Tool(ABC):
    """Abstract base class for all tools.

    Subclasses should:
    1. Set name, description as class attributes
    2. Implement execute(**kwargs) -> str (return result as string)
    3. Use @register_tool decorator to register
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments. Return result as string."""
        raise NotImplementedError

    def schema(self) -> ToolSchema:
        """Build the tool's schema by inspecting the execute signature."""
        sig = inspect.signature(self.execute)
        hints = get_type_hints(self.execute)

        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "kwargs"):
                continue

            param_type = hints.get(param_name, str)
            json_type = _python_type_to_json_type(param_type)

            prop: Dict[str, Any] = {"type": json_type}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
            else:
                # Mark optional with default in description
                pass

            # Pull description from docstring if available
            doc = inspect.getdoc(self.execute) or ""
            prop["description"] = _extract_param_description(doc, param_name)

            properties[param_name] = prop

        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": properties,
                "required": required,
            },
        )


def _python_type_to_json_type(t) -> str:
    """Map Python type to JSON Schema type."""
    import typing
    origin = typing.get_origin(t)
    if origin in (list, List):
        return "array"
    if origin in (dict, Dict):
        return "object"
    if t is int:
        return "integer"
    if t is float:
        return "number"
    if t is bool:
        return "boolean"
    return "string"


def _extract_param_description(doc: str, param_name: str) -> str:
    """Extract parameter description from docstring (Google/NumPy style)."""
    # Simple parser: find "param_name: description" pattern
    lines = doc.split("\n")
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{param_name}:"):
            return stripped[len(param_name) + 1:].strip()
        if stripped.startswith("Args:") or stripped.startswith("Parameters:"):
            capture = True
            continue
        if capture:
            if stripped and not stripped.startswith((":", " ")):
                # New section
                break
    return f"Parameter {param_name}"


class ToolRegistry:
    """Global registry for all available tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def schemas(self) -> List[Dict[str, Any]]:
        """Return all tool schemas in Anthropic-compatible format."""
        return [tool.schema().to_anthropic_format() for tool in self._tools.values()]

    def schemas_for_prompt(self) -> str:
        """Return tool schemas as a JSON string for prompt injection (backup)."""
        schemas = []
        for tool in self._tools.values():
            s = tool.schema()
            schemas.append({
                "name": s.name,
                "description": s.description,
                "input_schema": s.input_schema,
            })
        return json.dumps(schemas, ensure_ascii=False, indent=2)


# Global registry
registry = ToolRegistry()


def register_tool(cls=None):
    """Class decorator to auto-register a tool.

    Usage:
        @register_tool
        class CalculatorTool(Tool):
            name = "calculator"
            description = "..."

            def execute(self, expression: str) -> str:
                ...
    """
    def wrap(klass):
        instance = klass()
        registry.register(instance)
        return klass
    if cls is None:
        return wrap
    wrap(cls)
    return cls