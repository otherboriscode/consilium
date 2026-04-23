"""ConsiliumClient — all HTTP interactions mocked via respx."""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from consilium_server.bot.client import (
    AuthError,
    ConsiliumClient,
    CostDenied,
    JobNotFound,
    RateLimited,
)


@pytest.mark.asyncio
async def test_submit_job_happy_path():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.post("/jobs").mock(
                return_value=Response(
                    202,
                    json={
                        "job_id": 42,
                        "status": "running",
                        "estimated_cost_usd": 0.5,
                        "estimated_duration_seconds": 60,
                        "warnings": [],
                    },
                )
            )
            r = await client.submit_job(topic="test", template="quick_check")
    assert r.job_id == 42
    assert r.status == "running"


@pytest.mark.asyncio
async def test_submit_drops_none_fields():
    """None-valued fields are stripped so the server sees a clean payload."""
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            route = mock.post("/jobs").mock(
                return_value=Response(
                    202,
                    json={
                        "job_id": 1,
                        "status": "running",
                        "estimated_cost_usd": 0.1,
                        "estimated_duration_seconds": 60,
                        "warnings": [],
                    },
                )
            )
            await client.submit_job(topic="t", template="quick_check")

    import json as _json
    body = _json.loads(route.calls[0].request.content)
    assert body == {"topic": "t", "template": "quick_check", "force": False}


@pytest.mark.asyncio
async def test_get_status_404_raises_job_not_found():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.get("/jobs/999").mock(
                return_value=Response(404, json={"detail": "Job 999 not found"})
            )
            with pytest.raises(JobNotFound, match="999"):
                await client.get_status(job_id=999)


@pytest.mark.asyncio
async def test_auth_error_on_401():
    async with ConsiliumClient(base_url="http://test", token="bad") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.get("/jobs").mock(
                return_value=Response(401, json={"detail": "Invalid token"})
            )
            with pytest.raises(AuthError):
                await client.list_jobs()


@pytest.mark.asyncio
async def test_cost_denied_carries_details():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.post("/jobs").mock(
                return_value=Response(
                    402,
                    json={
                        "detail": {
                            "violations": ["per_job_cap_exceeded"],
                            "messages": ["over cap"],
                            "estimated_cost_usd": 30.0,
                        }
                    },
                )
            )
            with pytest.raises(CostDenied) as exc:
                await client.submit_job(topic="t", template="product_concept")
    assert "per_job_cap_exceeded" in exc.value.violations
    assert exc.value.estimate == 30.0


@pytest.mark.asyncio
async def test_rate_limited_on_429():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.post("/jobs").mock(
                return_value=Response(
                    429, json={"detail": "too many active jobs"}
                )
            )
            with pytest.raises(RateLimited):
                await client.submit_job(topic="t", template="quick_check")


@pytest.mark.asyncio
async def test_list_jobs_passes_filters():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            route = mock.get("/jobs").mock(
                return_value=Response(200, json=[])
            )
            await client.list_jobs(project="demo", limit=5)
    req = route.calls[0].request
    assert "project=demo" in str(req.url)
    assert "limit=5" in str(req.url)


@pytest.mark.asyncio
async def test_cancel_job():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.post("/jobs/42/cancel").mock(
                return_value=Response(
                    200, json={"job_id": 42, "status": "cancelled"}
                )
            )
            await client.cancel_job(42)


@pytest.mark.asyncio
async def test_get_archive_md_returns_text():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.get("/archive/7/md").mock(
                return_value=Response(200, text="# TL;DR\nhi")
            )
            md = await client.get_archive_md(7)
    assert "TL;DR" in md


@pytest.mark.asyncio
async def test_create_pack_sends_multipart():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.post("/packs/demo").mock(
                return_value=Response(
                    200,
                    json={
                        "name": "demo",
                        "total_tokens": 10,
                        "files": ["a.md"],
                    },
                )
            )
            r = await client.create_pack(
                "demo", files=[("a.md", b"# A")]
            )
    assert r["name"] == "demo"


@pytest.mark.asyncio
async def test_stream_events_yields_parsed_json():
    sse_body = (
        "event: round_started\n"
        'data: {"kind":"round_started","round_index":0,'
        '"message":"go","timestamp":"2026-04-23T00:00:00+00:00"}\n\n'
        "event: done\n"
        'data: {"kind":"done","message":"ok",'
        '"timestamp":"2026-04-23T00:00:01+00:00"}\n\n'
    )
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.get("/jobs/5/events").mock(
                return_value=Response(
                    200,
                    text=sse_body,
                    headers={"content-type": "text/event-stream"},
                )
            )
            kinds: list[str] = []
            async for event in client.stream_events(5):
                kinds.append(event["kind"])
    assert kinds == ["round_started", "done"]


@pytest.mark.asyncio
async def test_stream_events_raises_on_404():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.get("/jobs/99/events").mock(
                return_value=Response(404, json={"detail": "not active"})
            )
            with pytest.raises(JobNotFound):
                async for _ in client.stream_events(99):
                    pass


@pytest.mark.asyncio
async def test_preview_job_when_preview_endpoint_exists():
    async with ConsiliumClient(base_url="http://test", token="x") as client:
        with respx.mock(base_url="http://test") as mock:
            mock.post("/preview").mock(
                return_value=Response(
                    200,
                    json={
                        "estimated_cost_usd": 0.3,
                        "estimated_duration_seconds": 90,
                        "warnings": [],
                    },
                )
            )
            r = await client.preview_job(topic="t", template="quick_check")
    assert r.estimated_cost_usd == 0.3


def test_requires_context_manager():
    client = ConsiliumClient(base_url="http://test", token="x")
    import pytest

    async def _run():
        with pytest.raises(RuntimeError, match="context manager"):
            await client.list_jobs()

    import asyncio

    asyncio.run(_run())
