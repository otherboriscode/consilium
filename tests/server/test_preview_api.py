"""POST /preview — dry-run of /jobs.

Semantics intentionally diverge from /jobs:
  - 404 / 422 — same (unknown template/pack, structural violation)
  - 402 — NEVER returned; cost-cap violations surface in the body as
    `allowed=false` + `violations[]` so the bot FSM can render
    force-or-cancel without re-submitting.
"""
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
    assert "context_tokens" in body
    assert "participants" in body
    assert "allowed" in body
    assert body["allowed"] is True
    assert body["violations"] == []


def test_preview_surfaces_participants_with_fit(authed_env, authed_headers):
    r = client.post(
        "/preview",
        json={"topic": "t", "template": "quick_check"},
        headers=authed_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["participants"]) >= 1
    p = body["participants"][0]
    assert {"role", "model", "mode", "fit", "estimated_cost_usd"}.issubset(p)
    assert p["mode"] in ("fast", "deep")
    assert p["fit"] in ("full", "summary", "exclude")
    assert body["judge_model"]
    assert body["rounds"] >= 1


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


def test_preview_404_unknown_pack(authed_env, authed_headers):
    r = client.post(
        "/preview",
        json={
            "topic": "t",
            "template": "quick_check",
            "pack": "nonexistent_pack",
        },
        headers=authed_headers,
    )
    assert r.status_code == 404


def test_preview_surfaces_cost_violations_without_blocking(
    authed_env, authed_headers, tmp_path, monkeypatch
):
    """Cost violations → 200 with allowed=false + violations[], NOT 402.

    This is the whole point of /preview vs /jobs — the bot FSM wants to
    render a force-or-cancel keyboard without burning a job_id.
    """
    limits_file = tmp_path / "tight.yaml"
    limits_file.write_text("max_cost_per_job_usd: 0.001\n")
    monkeypatch.setenv("CONSILIUM_LIMITS_FILE", str(limits_file))

    r = client.post(
        "/preview",
        json={"topic": "t", "template": "product_concept"},
        headers=authed_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is False
    assert any("per_job_cap" in v for v in body["violations"])
    assert len(body["violation_messages"]) == len(body["violations"])


def test_preview_respects_structural_limits(
    authed_env, authed_headers, tmp_path, monkeypatch
):
    """Structural violations (rounds > limit) still return 422 as /jobs does."""
    limits_file = tmp_path / "tight.yaml"
    limits_file.write_text("max_rounds: 1\n")
    monkeypatch.setenv("CONSILIUM_LIMITS_FILE", str(limits_file))

    r = client.post(
        "/preview",
        json={"topic": "t", "template": "quick_check", "rounds": 3},
        headers=authed_headers,
    )
    assert r.status_code == 422


def test_preview_with_context_block_shows_token_count(authed_env, authed_headers):
    ctx = "контекст " * 100
    r = client.post(
        "/preview",
        json={
            "topic": "t",
            "template": "quick_check",
            "context_block": ctx,
        },
        headers=authed_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["context_tokens"] > 0
