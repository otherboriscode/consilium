"""
MCP server — wires the Consilium API up as Claude Code tools over stdio.

`build_server()` creates the `mcp.server.Server` instance and registers
`list_tools` + `call_tool` handlers that dispatch through our
`Registry` (see `consilium_mcp.registry`). Actual tool definitions live
in `consilium_mcp/tools/*.py` — each has a `register(registry, *,
client_factory)` hook.

The `client_factory` indirection lets tests swap in a mock client instead
of building a real `ConsiliumClient` against a live API.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mcp import types
from mcp.server import Server

from consilium_client import ClientConfig, ConsiliumClient, load_config
from consilium_mcp.registry import Registry
from consilium_mcp.tools import (
    archive as archive_tools,
    budget as budget_tools,
    debate as debate_tools,
    packs as packs_tools,
    templates as templates_tools,
)

ClientFactory = Callable[[], "Awaitable[ConsiliumClient] | ConsiliumClient"]


@dataclass
class ConsiliumMCPServer:
    """Wrapper exposing the underlying `mcp.server.Server` + our Registry.

    Tests can inspect `.registry.tools` without spinning up stdio.
    """

    server: Server
    registry: Registry
    config: ClientConfig | None


def _default_client_factory(config: ClientConfig) -> ClientFactory:
    def _make() -> ConsiliumClient:
        return ConsiliumClient(
            base_url=config.api_base,
            token=config.token,
            timeout=config.timeout_seconds,
        )

    return _make


def build_server(
    *,
    config: ClientConfig | None = None,
    client_factory: ClientFactory | None = None,
) -> ConsiliumMCPServer:
    """Construct the MCP server + tool registry.

    `config=None` means load from env/YAML at call time; tests pass an
    explicit ClientConfig to avoid touching the filesystem.

    `client_factory=None` builds a real ConsiliumClient from config. Tests
    can pass a callable that returns a fake for deterministic behaviour.
    """
    if config is None:
        config = load_config()
    if client_factory is None:
        client_factory = _default_client_factory(config)

    registry = Registry()
    debate_tools.register(registry, client_factory=client_factory)
    archive_tools.register(registry, client_factory=client_factory)
    packs_tools.register(registry, client_factory=client_factory)
    templates_tools.register(registry, client_factory=client_factory)
    budget_tools.register(registry, client_factory=client_factory)

    server: Server = Server("consilium-mcp")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.input_schema,
            )
            for t in registry.tools
        ]

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict
    ) -> list[types.ContentBlock]:
        spec = registry.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name}")
        result = await spec.handler(arguments or {})
        # Normalize all results to a single TextContent block. MCP clients
        # (incl. Claude Code) render this fine; more elaborate content
        # types are follow-up work if we ever want images/files.
        if isinstance(result, str):
            text = result
        else:
            text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        return [types.TextContent(type="text", text=text)]

    return ConsiliumMCPServer(
        server=server, registry=registry, config=config
    )


async def run_stdio() -> None:
    """Entry point for the `consilium-mcp` command — connect to stdio and
    serve until the parent (Claude Code) disconnects."""
    from mcp.server.stdio import stdio_server

    wrapper = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await wrapper.server.run(
            read_stream,
            write_stream,
            wrapper.server.create_initialization_options(),
        )
