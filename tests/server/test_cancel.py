"""Cancel tests use httpx.AsyncClient so the event loop persists across
requests — FastAPI's sync TestClient creates a fresh loop per call, which
cancels any asyncio.create_task() spawned during the handler."""
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from consilium.providers.base import BaseProvider, CallResult, CallUsage, Message
from consilium_server.api.main import app


class _ForeverProvider(BaseProvider):
    """Never resolves. Lets us keep a job permanently in 'running' state so
    the cancel endpoint has something to cancel."""

    name = "forever"

    async def call(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        deep: bool = False,
        cache_last_system_block: bool = True,
        timeout_seconds: float = 300.0,
    ) -> CallResult:
        await asyncio.Event().wait()
        # Unreachable — kept for typing.
        return CallResult(
            text="",
            usage=CallUsage(input_tokens=0, output_tokens=0),
            model=model,
            finish_reason="stop",
            duration_seconds=0.0,
        )


class _ForeverRegistry:
    def get_provider(self, model: str) -> BaseProvider:
        return _ForeverProvider()


@pytest.mark.asyncio
async def test_cancel_active_job(authed_env, authed_headers, monkeypatch):
    monkeypatch.setattr(
        "consilium_server.api.routes.jobs._build_registry",
        lambda: _ForeverRegistry(),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/jobs",
            json={"topic": "hanging", "template": "quick_check"},
            headers=authed_headers,
        )
        assert r1.status_code == 202, r1.text
        job_id = r1.json()["job_id"]
        await asyncio.sleep(0.2)  # let the background task reach Event.wait()

        r2 = await client.post(
            f"/jobs/{job_id}/cancel", headers=authed_headers
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_unknown_returns_404(authed_env, authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/jobs/9999/cancel", headers=authed_headers)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_cancel_completed_returns_409(authed_env, authed_headers):
    """Pre-register a handle whose task is already done → 409."""
    from consilium_server.api.state import JobHandle, get_state

    async def _done():
        return None

    task = asyncio.create_task(_done())
    await task
    state = get_state()
    state.register(JobHandle(job_id=555, task=task, status="completed"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/jobs/555/cancel", headers=authed_headers)
        assert r.status_code == 409
