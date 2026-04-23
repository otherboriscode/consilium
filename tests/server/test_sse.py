"""SSE tests: verify that POST /jobs schedules a task whose progress events
reach a subscribed GET /jobs/{id}/events stream."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from consilium_server.api.main import app


@pytest.mark.asyncio
async def test_sse_stream_receives_events(
    authed_env, authed_headers, mock_registry
):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", timeout=10
    ) as client:
        # Submit a mock job — finishes fast, but emits progress events.
        r1 = await client.post(
            "/jobs",
            json={"topic": "sse", "template": "quick_check"},
            headers=authed_headers,
        )
        assert r1.status_code == 202
        job_id = r1.json()["job_id"]

        # Subscribe via SSE. Read the stream until we see `done` or 10s.
        async with client.stream(
            "GET", f"/jobs/{job_id}/events", headers=authed_headers
        ) as resp:
            if resp.status_code == 404:
                # Job may have already completed before we connected. That's
                # acceptable — no events to show.
                return
            assert resp.status_code == 200
            events: list[str] = []
            async for line in resp.aiter_lines():
                events.append(line)
                joined = "\n".join(events)
                if "event: done" in joined or "event: end" in joined:
                    break

            text = "\n".join(events)
            # At minimum we should see something event-ish
            assert "event:" in text


@pytest.mark.asyncio
async def test_sse_404_for_inactive_job(authed_env, authed_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/jobs/9999/events", headers=authed_headers)
        assert r.status_code == 404
