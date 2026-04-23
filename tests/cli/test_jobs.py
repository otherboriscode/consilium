"""
CLI jobs command tests.

Uses respx to mock the Consilium API and exercises the three actions
(list / status / cancel) by calling `main()` directly.
"""
from __future__ import annotations

import pytest
import respx

from consilium_cli.main import main


BASE = "http://api.test"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_BASE", BASE)
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "t")
    monkeypatch.setenv("CONSILIUM_CLIENT_CONFIG", "/nonexistent/path.yaml")


@respx.mock
def test_jobs_list_empty(capsys):
    respx.get(f"{BASE}/jobs").respond(200, json=[])
    rc = main(["jobs"])
    assert rc == 0
    assert "пусто" in capsys.readouterr().out


@respx.mock
def test_jobs_list_items(capsys):
    respx.get(f"{BASE}/jobs").respond(
        200,
        json=[
            {
                "job_id": 42,
                "status": "running",
                "template": "quick_check",
                "topic": "test topic here",
                "project": "tanaa",
                "started_at": "2026-04-23T10:00:00+00:00",
                "cost_usd": 1.23,
            }
        ],
    )
    rc = main(["jobs", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "42" in out
    assert "quick_check" in out
    assert "test topic" in out


@respx.mock
def test_jobs_status(capsys):
    respx.get(f"{BASE}/jobs/42").respond(
        200,
        json={
            "job_id": 42,
            "status": "completed",
            "rounds_completed": 2,
            "rounds_total": 2,
            "current_cost_usd": 0.45,
            "estimated_cost_usd": 0.50,
            "template": "quick_check",
            "topic": "foo",
            "project": None,
            "started_at": "2026-04-23T10:00:00+00:00",
            "error": None,
        },
    )
    rc = main(["jobs", "status", "42"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "#42" in out
    assert "completed" in out
    assert "2/2" in out


@respx.mock
def test_jobs_status_404(capsys):
    respx.get(f"{BASE}/jobs/999").respond(
        404, json={"detail": "Job 999 not found"}
    )
    rc = main(["jobs", "status", "999"])
    assert rc == 2


@respx.mock
def test_jobs_cancel(capsys):
    respx.post(f"{BASE}/jobs/42/cancel").respond(
        200, json={"job_id": 42, "status": "cancelled"}
    )
    rc = main(["jobs", "cancel", "42"])
    assert rc == 0
    assert "cancelled" in capsys.readouterr().out


@respx.mock
def test_jobs_list_passes_project_filter(capsys):
    route = respx.get(f"{BASE}/jobs").respond(200, json=[])
    rc = main(["jobs", "list", "--project", "tanaa"])
    assert rc == 0
    req = route.calls[0].request
    assert b"project=tanaa" in req.url.query
