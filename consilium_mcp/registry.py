"""
Tool registry — a plain list-of-ToolSpec that each tool module appends to.

The MCP SDK uses decorator-based registration (`@server.list_tools()`,
`@server.call_tool()`), which is fine for dispatch but makes it awkward
to introspect which tools are defined (e.g. for a sanity test).

So we maintain our own `ToolSpec` list and build the SDK handlers on top
of it in `server.build_server()`. That gives tests something observable
(`server.tools`) without fighting the SDK's decorator convention.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Handler


class Registry:
    """Append-only list of `ToolSpec` built up by each `tools/*.py` module."""

    def __init__(self) -> None:
        self._tools: list[ToolSpec] = []

    def add(self, spec: ToolSpec) -> None:
        # Dupe check so a typo doesn't silently shadow an existing tool.
        if any(t.name == spec.name for t in self._tools):
            raise ValueError(f"Duplicate tool name: {spec.name}")
        self._tools.append(spec)

    @property
    def tools(self) -> list[ToolSpec]:
        return list(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        for t in self._tools:
            if t.name == name:
                return t
        return None
