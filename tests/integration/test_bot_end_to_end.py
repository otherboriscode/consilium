"""Bot ↔ API integration: ConsiliumClient talks to the real FastAPI app
through ASGITransport (no network, no uvicorn). Proves the client contract
matches what the server actually serves, for every endpoint the bot uses."""
from __future__ import annotations

import pytest
from httpx import ASGITransport

from consilium_server.api import state as state_module
from consilium_server.api.main import app
from consilium_server.bot.client import (
    AuthError,
    ConsiliumClient,
    JobNotFound,
)


@pytest.fixture
def authed_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "bot-e2e-token")
    monkeypatch.setenv("CONSILIUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-fake")
    state_module._state = None
    state_module.reset_state_for_tests(
        max_concurrent=5, min_seconds_between=0
    )
    yield tmp_path
    state_module._state = None


def _client() -> ConsiliumClient:
    return ConsiliumClient(
        base_url="http://test",
        token="bot-e2e-token",
        transport=ASGITransport(app=app),
    )


@pytest.mark.asyncio
async def test_auth_error_raised_on_bad_token(authed_env):
    bad = ConsiliumClient(
        base_url="http://test",
        token="wrong",
        transport=ASGITransport(app=app),
    )
    async with bad as client:
        with pytest.raises(AuthError):
            await client.list_jobs()


@pytest.mark.asyncio
async def test_list_templates_returns_all_defaults(authed_env):
    async with _client() as client:
        names = await client.list_templates()
    assert "product_concept" in names
    assert "quick_check" in names


@pytest.mark.asyncio
async def test_show_template_returns_roles(authed_env):
    async with _client() as client:
        info = await client.show_template("quick_check")
    assert info["name"] == "quick_check"
    assert len(info["participants"]) >= 1
    assert info["judge"]["model"]


@pytest.mark.asyncio
async def test_show_template_404(authed_env):
    async with _client() as client:
        with pytest.raises(JobNotFound):
            await client.show_template("does_not_exist")


@pytest.mark.asyncio
async def test_preview_returns_estimate(authed_env):
    async with _client() as client:
        preview = await client.preview_job(
            topic="e2e", template="quick_check"
        )
    assert preview.estimated_cost_usd > 0
    assert preview.estimated_duration_seconds > 0


@pytest.mark.asyncio
async def test_pack_crud_cycle(authed_env):
    async with _client() as client:
        # Empty
        assert await client.list_packs() == []

        # Create
        created = await client.create_pack(
            "e2e-pack", files=[("a.md", b"# A\nhello")]
        )
        assert created["name"] == "e2e-pack"

        # List
        assert "e2e-pack" in await client.list_packs()

        # Show
        info = await client.show_pack("e2e-pack")
        assert info["name"] == "e2e-pack"
        assert len(info["files"]) == 1

        # Delete
        await client.delete_pack("e2e-pack")
        assert "e2e-pack" not in await client.list_packs()


@pytest.mark.asyncio
async def test_budget_endpoints(authed_env):
    async with _client() as client:
        usage = await client.get_usage()
        assert "today_usd" in usage and "month_usd" in usage
        limits = await client.get_limits()
        assert limits["max_cost_per_month_usd"] > 0
        summary = await client.get_daily_summary()
        assert isinstance(summary, str)


@pytest.mark.asyncio
async def test_job_status_404_for_unknown(authed_env):
    async with _client() as client:
        with pytest.raises(JobNotFound):
            await client.get_status(99999)


@pytest.mark.asyncio
async def test_archive_search_returns_list(authed_env):
    async with _client() as client:
        hits = await client.search_archive("nothing", limit=5)
    assert hits == []
