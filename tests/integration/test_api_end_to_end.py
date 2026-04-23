"""End-to-end API roundtrip: POST /jobs → poll status → fetch from archive.

Uses FastAPI's TestClient as a context manager (triggers startup lifespan
and keeps a persistent portal, so background tasks created inside handlers
survive across client calls). `run_debate` is monkeypatched to a tiny
synchronous fake so no real provider calls happen — this test exercises
the wiring, not the LLMs.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from consilium.models import JobResult, JudgeOutput
from consilium_server.api import state as state_module
from consilium_server.api.main import app


@pytest.fixture
def authed_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "test-token-e2e")
    monkeypatch.setenv("CONSILIUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-fake")
    state_module._state = None
    state_module.reset_state_for_tests(
        max_concurrent=3, min_seconds_between=0
    )
    yield tmp_path
    state_module._state = None


@pytest.fixture
def authed_headers(authed_env):
    return {"Authorization": "Bearer test-token-e2e"}


async def _fake_run_debate(config, registry, *, job_id, progress=None):
    """Near-instant stand-in for orchestrator.run_debate."""
    # Optional: emit a single progress event so the plumbing is exercised.
    if progress is not None:
        from consilium.models import ProgressEvent as OrcProgressEvent

        await progress(
            OrcProgressEvent(kind="round_started", round_index=0)
        )
        await progress(
            OrcProgressEvent(kind="round_completed", round_index=0)
        )

    judge = JudgeOutput(
        raw_markdown="# TL;DR\nIt works.",
        tldr="It works.",
        consensus=["all good"],
        disagreements=[],
        unique_contributions={},
        blind_spots=[],
        recommendation="ship",
        scores={},
    )
    now = datetime.now(timezone.utc)
    return JobResult(
        job_id=job_id,
        config=config,
        messages=[],
        judge=judge,
        judge_truncated=False,
        duration_seconds=0.01,
        total_cost_usd=0.001,
        cost_breakdown={"claude-haiku-4-5": 0.001},
        started_at=now,
        completed_at=now,
    )


def test_full_api_cycle_with_mock_run_debate(
    monkeypatch, tmp_path, authed_env, authed_headers
):
    """Submit a job through the real API, poll until completion, then fetch
    the archived result back. Exercises the whole wiring without spending $0.
    """
    monkeypatch.setattr(
        "consilium_server.api.routes.jobs.run_debate", _fake_run_debate
    )

    with TestClient(app) as client:
        r = client.post(
            "/jobs",
            json={"topic": "e2e test", "template": "quick_check"},
            headers=authed_headers,
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        # Poll status.
        for _ in range(50):
            status = client.get(
                f"/jobs/{job_id}", headers=authed_headers
            ).json()["status"]
            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.05)
        assert status == "completed"

        # Fetch the archived JobResult JSON.
        r = client.get(f"/archive/{job_id}", headers=authed_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["job_id"] == job_id
        assert body["config"]["topic"] == "e2e test"
        assert body["judge"]["tldr"] == "It works."

        # Fetch the markdown artifact.
        r = client.get(f"/archive/{job_id}/md", headers=authed_headers)
        assert r.status_code == 200
        assert "e2e test" in r.text
