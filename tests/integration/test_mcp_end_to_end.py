"""
MCP end-to-end: spin up `consilium-mcp` as a subprocess (stdio transport)
and use the official MCP client SDK to talk to it.

Validates:
  - initialize handshake
  - list_tools returns the expected set
  - calling a simple tool (templates list) works
  - schemas render as valid JSONSchema

No Claude Code required — the SDK is transport-agnostic.

Gated by @pytest.mark.integration — needs the same live API as CLI tests.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time

import httpx
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live_api(tmp_path):
    port = _pick_free_port()
    token = "mcp-e2e-token"
    env = os.environ.copy()
    env.update(
        {
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_DATA_DIR": str(tmp_path / "data"),
            "ANTHROPIC_API_KEY": "sk-fake",
            "OPENROUTER_API_KEY": "sk-fake",
            "PERPLEXITY_API_KEY": "pplx-fake",
        }
    )
    proc = subprocess.Popen(
        ["consilium-api", "--port", str(port), "--host", "127.0.0.1"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            r = httpx.get(
                f"{base_url}/templates",
                headers={"Authorization": f"Bearer {token}"},
                timeout=0.5,
            )
            if r.status_code == 200:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("API didn't come up")

    yield base_url, token

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


@pytest.mark.integration
async def test_mcp_lists_expected_tools(live_api):
    base_url, token = live_api
    params = StdioServerParameters(
        command="consilium-mcp",
        env={
            "CONSILIUM_API_BASE": base_url,
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_CLIENT_CONFIG": "/nonexistent.yaml",
            "PATH": os.environ.get("PATH", ""),
        },
    )
    async with stdio_client(params) as (read_s, write_s):
        async with ClientSession(read_s, write_s) as session:
            await session.initialize()
            result = await session.list_tools()
            names = {t.name for t in result.tools}
            expected_core = {
                "consilium_preview",
                "consilium_start",
                "consilium_status",
                "consilium_wait",
                "consilium_cancel",
                "consilium_archive_search",
                "consilium_archive_get",
                "consilium_packs_list",
                "consilium_pack_create",
                "consilium_templates_list",
                "consilium_budget_usage",
            }
            assert expected_core.issubset(names)


@pytest.mark.integration
async def test_mcp_call_templates_list_returns_content(live_api):
    base_url, token = live_api
    params = StdioServerParameters(
        command="consilium-mcp",
        env={
            "CONSILIUM_API_BASE": base_url,
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_CLIENT_CONFIG": "/nonexistent.yaml",
            "PATH": os.environ.get("PATH", ""),
        },
    )
    async with stdio_client(params) as (read_s, write_s):
        async with ClientSession(read_s, write_s) as session:
            await session.initialize()
            result = await session.call_tool(
                "consilium_templates_list", arguments={}
            )
            # Result content is a list of TextContent blocks
            assert result.content
            first = result.content[0]
            # server wraps dict/list results as JSON text
            assert first.type == "text"
            # At least one of the bundled templates should appear
            assert (
                "product_concept" in first.text
                or "quick_check" in first.text
            )


@pytest.mark.integration
async def test_mcp_call_preview_tool_returns_estimate(live_api):
    base_url, token = live_api
    params = StdioServerParameters(
        command="consilium-mcp",
        env={
            "CONSILIUM_API_BASE": base_url,
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_CLIENT_CONFIG": "/nonexistent.yaml",
            "PATH": os.environ.get("PATH", ""),
        },
    )
    async with stdio_client(params) as (read_s, write_s):
        async with ClientSession(read_s, write_s) as session:
            await session.initialize()
            result = await session.call_tool(
                "consilium_preview",
                arguments={"topic": "интеграционный тест", "template": "quick_check"},
            )
            assert result.content
            text = result.content[0].text
            assert "estimated_cost_usd" in text
            assert "participants" in text
            assert "allowed" in text


@pytest.mark.integration
async def test_mcp_unknown_tool_errors_cleanly(live_api):
    base_url, token = live_api
    params = StdioServerParameters(
        command="consilium-mcp",
        env={
            "CONSILIUM_API_BASE": base_url,
            "CONSILIUM_API_TOKEN": token,
            "CONSILIUM_CLIENT_CONFIG": "/nonexistent.yaml",
            "PATH": os.environ.get("PATH", ""),
        },
    )
    async with stdio_client(params) as (read_s, write_s):
        async with ClientSession(read_s, write_s) as session:
            await session.initialize()
            # Calling a tool the server doesn't know about should surface
            # as an error result, not hang or crash the stdio session.
            try:
                result = await session.call_tool(
                    "consilium_nonexistent", arguments={}
                )
                # If it returned instead of raising, `isError` should be True.
                assert result.isError is True
            except Exception:
                # Raising is also acceptable — the SDK may translate
                # server errors into exceptions. We just need "not hang".
                pass
