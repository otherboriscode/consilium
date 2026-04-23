"""
Tests for `consilium_client.ConsiliumClient` — respx-mocked.

Covers: typed error translation, request shape (bodies, params), and the
new PreviewResult parsing including fallbacks for missing fields.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from consilium_client import (
    AuthError,
    ConsiliumClient,
    CostDenied,
    JobNotFound,
    NetworkError,
    RateLimited,
)


BASE = "http://api.test"


@pytest.fixture
def cm_client():
    """A configured but not-yet-entered ConsiliumClient. Tests `async with` it."""
    return ConsiliumClient(base_url=BASE, token="t")


@respx.mock
async def test_submit_job_posts_body_and_returns_result(cm_client):
    respx.post(f"{BASE}/jobs").respond(
        200,
        json={
            "job_id": 42,
            "status": "running",
            "estimated_cost_usd": 1.0,
            "estimated_duration_seconds": 120,
            "warnings": [],
        },
    )
    async with cm_client as client:
        r = await client.submit_job(topic="x", template="quick_check")
        assert r.job_id == 42


@respx.mock
async def test_preview_job_parses_rich_response(cm_client):
    respx.post(f"{BASE}/preview").respond(
        200,
        json={
            "estimated_cost_usd": 0.5,
            "estimated_duration_seconds": 60,
            "context_tokens": 1500,
            "template": "quick_check",
            "rounds": 2,
            "participants": [
                {
                    "role": "architect",
                    "model": "claude-sonnet-4.5",
                    "mode": "deep",
                    "fit": "full",
                    "estimated_cost_usd": 0.0,
                }
            ],
            "judge_model": "claude-haiku-4.5",
            "allowed": True,
            "violations": [],
            "violation_messages": [],
            "warnings": ["50% of day"],
        },
    )
    async with cm_client as client:
        r = await client.preview_job(topic="x", template="quick_check")
    assert r.context_tokens == 1500
    assert r.allowed is True
    assert r.participants[0].fit == "full"
    assert r.warnings == ["50% of day"]


@respx.mock
async def test_preview_handles_allowed_false(cm_client):
    respx.post(f"{BASE}/preview").respond(
        200,
        json={
            "estimated_cost_usd": 100,
            "estimated_duration_seconds": 60,
            "context_tokens": 0,
            "template": "quick_check",
            "rounds": 2,
            "participants": [],
            "judge_model": "m",
            "allowed": False,
            "violations": ["per_job_cap_exceeded"],
            "violation_messages": ["too expensive"],
            "warnings": [],
        },
    )
    async with cm_client as client:
        r = await client.preview_job(topic="x", template="quick_check")
    assert r.allowed is False
    assert "per_job_cap_exceeded" in r.violations


@respx.mock
async def test_401_raises_auth_error(cm_client):
    respx.post(f"{BASE}/jobs").respond(
        401, json={"detail": "bad token"}
    )
    async with cm_client as client:
        with pytest.raises(AuthError, match="bad token"):
            await client.submit_job(topic="x", template="t")


@respx.mock
async def test_404_raises_job_not_found(cm_client):
    respx.get(f"{BASE}/jobs/42").respond(
        404, json={"detail": "Job 42 not found"}
    )
    async with cm_client as client:
        with pytest.raises(JobNotFound, match="42"):
            await client.get_status(42)


@respx.mock
async def test_402_raises_cost_denied_with_details(cm_client):
    respx.post(f"{BASE}/jobs").respond(
        402,
        json={
            "detail": {
                "violations": ["per_day_cap_exceeded"],
                "messages": ["$50/day reached"],
                "estimated_cost_usd": 5.0,
            }
        },
    )
    async with cm_client as client:
        with pytest.raises(CostDenied) as excinfo:
            await client.submit_job(topic="x", template="t")
        err = excinfo.value
        assert err.violations == ["per_day_cap_exceeded"]
        assert err.estimate == 5.0


@respx.mock
async def test_429_raises_rate_limited(cm_client):
    respx.post(f"{BASE}/jobs").respond(
        429, json={"detail": "too many concurrent"}
    )
    async with cm_client as client:
        with pytest.raises(RateLimited):
            await client.submit_job(topic="x", template="t")


@respx.mock
async def test_connection_error_translates_to_network_error(cm_client):
    respx.post(f"{BASE}/jobs").mock(
        side_effect=httpx.ConnectError("refused")
    )
    async with cm_client as client:
        with pytest.raises(NetworkError, match="refused"):
            await client.submit_job(topic="x", template="t")


@respx.mock
async def test_list_jobs_passes_filters(cm_client):
    route = respx.get(f"{BASE}/jobs").respond(200, json=[])
    async with cm_client as client:
        await client.list_jobs(project="tanaa", limit=5)
    assert route.called
    req = route.calls[0].request
    assert b"project=tanaa" in req.url.query
    assert b"limit=5" in req.url.query


@respx.mock
async def test_show_pack_returns_dict(cm_client):
    respx.get(f"{BASE}/packs/tanaa").respond(
        200,
        json={
            "name": "tanaa",
            "files": [{"name": "brief.md", "tokens": 1000, "type": "md"}],
            "total_tokens": 1000,
            "has_stale_files": False,
        },
    )
    async with cm_client as client:
        p = await client.show_pack("tanaa")
    assert p["name"] == "tanaa"
    assert p["total_tokens"] == 1000


@respx.mock
async def test_create_pack_uses_multipart(cm_client):
    route = respx.post(f"{BASE}/packs/newpack").respond(
        200, json={"name": "newpack", "files": ["a.md"], "total_tokens": 10}
    )
    async with cm_client as client:
        await client.create_pack(
            "newpack", files=[("a.md", b"hello")]
        )
    assert route.called
    req = route.calls[0].request
    assert b"multipart/form-data" in req.headers["content-type"].encode()


def test_requires_context_manager():
    client = ConsiliumClient(base_url=BASE, token="t")
    with pytest.raises(RuntimeError, match="async context manager"):
        client._c()
