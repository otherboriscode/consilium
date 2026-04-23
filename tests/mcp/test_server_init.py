"""
Basic sanity checks for the MCP server skeleton: it builds without a
live API, the Registry is empty at skeleton-stage (tools come in 8.8/8.9),
and config loads via env vars.
"""
from __future__ import annotations

import pytest

from consilium_client import ClientConfig
from consilium_mcp.registry import Registry, ToolSpec
from consilium_mcp.server import build_server


@pytest.fixture
def fake_config():
    return ClientConfig(
        api_base="http://test", token="t", timeout_seconds=5
    )


def test_build_server_from_explicit_config(fake_config):
    wrapper = build_server(config=fake_config)
    assert wrapper.config is fake_config
    assert wrapper.server is not None
    assert wrapper.registry is not None


def test_registry_rejects_duplicate_tool_names():
    r = Registry()

    async def handler(_args):
        return "x"

    spec = ToolSpec(
        name="dup", description="d", input_schema={}, handler=handler
    )
    r.add(spec)
    with pytest.raises(ValueError, match="Duplicate tool name"):
        r.add(spec)


def test_registry_get_returns_tool(fake_config):
    r = Registry()

    async def handler(_args):
        return "ok"

    r.add(
        ToolSpec(
            name="one",
            description="uno",
            input_schema={"type": "object"},
            handler=handler,
        )
    )
    spec = r.get("one")
    assert spec is not None
    assert spec.description == "uno"
    assert r.get("missing") is None


def test_build_server_reads_env_when_config_none(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_BASE", "http://env-base")
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "env-token")
    monkeypatch.setenv("CONSILIUM_CLIENT_CONFIG", "/nonexistent.yaml")
    wrapper = build_server()
    assert wrapper.config is not None
    assert wrapper.config.api_base == "http://env-base"


async def test_list_tools_handler_callable(fake_config):
    """Smoke: the MCP SDK's list_tools handler can be invoked without
    crashing even with an empty registry (pre-8.8)."""
    wrapper = build_server(config=fake_config)
    # We can't easily invoke the registered handler directly (it's wrapped
    # inside SDK decorators), but we can verify the registry exposes tools.
    assert isinstance(wrapper.registry.tools, list)
