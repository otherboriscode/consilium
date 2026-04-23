"""POST /preview — dry-run of /jobs."""
from __future__ import annotations

from fastapi.testclient import TestClient

from consilium_server.api.main import app

client = TestClient(app)


def test_preview_requires_auth(authed_env):
    r = client.post("/preview", json={"topic": "t", "template": "quick_check"})
    assert r.status_code == 401


def test_preview_returns_estimate(authed_env, authed_headers):
    r = client.post(
        "/preview",
        json={"topic": "test", "template": "quick_check"},
        headers=authed_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estimated_cost_usd"] > 0
    assert body["estimated_duration_seconds"] > 0
    assert "warnings" in body


def test_preview_does_not_create_job(authed_env, authed_headers):
    """/preview must not consume a job_id or leave any ServerState trace."""
    from consilium_server.api.state import get_state

    before = len(get_state().all_active())
    r = client.post(
        "/preview",
        json={"topic": "t", "template": "quick_check"},
        headers=authed_headers,
    )
    assert r.status_code == 200
    after = len(get_state().all_active())
    assert after == before


def test_preview_404_unknown_template(authed_env, authed_headers):
    r = client.post(
        "/preview",
        json={"topic": "t", "template": "does_not_exist"},
        headers=authed_headers,
    )
    assert r.status_code == 404


def test_preview_402_on_cost_cap(authed_env, authed_headers, tmp_path, monkeypatch):
    limits_file = tmp_path / "tight.yaml"
    limits_file.write_text("max_cost_per_job_usd: 0.001\n")
    monkeypatch.setenv("CONSILIUM_LIMITS_FILE", str(limits_file))

    r = client.post(
        "/preview",
        json={"topic": "t", "template": "product_concept"},
        headers=authed_headers,
    )
    assert r.status_code == 402
    assert "per_job_cap_exceeded" in r.json()["detail"]["violations"]
