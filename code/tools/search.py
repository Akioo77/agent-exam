"""Mock search tool.

Returns canned results based on keywords. The real implementation
would call a search API; here we keep it deterministic and offline.
"""
from __future__ import annotations

from agent.tools import Tool, register_tool


_MOCK_DB = {
    "weather": [
        {"title": "Weather in Tokyo", "snippet": "Sunny, 22°C, humidity 60%."},
        {"title": "Weather in Beijing", "snippet": "Cloudy, 18°C, humidity 45%."},
        {"title": "Weather in Shanghai", "snippet": "Rainy, 25°C, humidity 80%."},
    ],
    "python": [
        {"title": "Python Official Docs", "snippet": "Python is a programming language."},
        {"title": "PEP 8 Style Guide", "snippet": "Code style conventions for Python."},
    ],
    "agent": [
        {"title": "What is an AI Agent?", "snippet": "An autonomous system that uses tools."},
        {"title": "ReAct: Reasoning + Acting", "snippet": "A paradigm for LLM-based agents."},
    ],
}


@register_tool
class SearchTool(Tool):
    name = "search"
    description = (
        "Search for information using a query keyword. "
        "Returns up to 3 mock results (this is a mock implementation, "
        "not a real web search). Use when the user asks about weather, "
        "general knowledge, or to look up any external information."
    )

    def execute(self, query: str, max_results: int = 3) -> str:
        """Perform a mock search.

        Args:
            query: The search query (e.g. "weather tokyo", "python list").
            max_results: Maximum number of results to return.

        Returns:
            A formatted string listing the search results.
        """
        q = query.lower()
        # Pick matching bucket
        bucket = None
        for key, items in _MOCK_DB.items():
            if key in q:
                bucket = items
                break
        if bucket is None:
            bucket = [
                {"title": f"Mock result for {query}",
                 "snippet": f"This is a placeholder result for query '{query}'. "
                            f"The real search would return real information here."}
            ]

        results = bucket[: max(1, int(max_results))]
        lines = [f"Search results for '{query}':"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']} — {r['snippet']}")
        return "\n".join(lines)