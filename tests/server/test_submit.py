import time


def _wait_for_job(api_client, job_id: int, headers: dict, timeout_s: float = 5.0):
    """Poll /jobs/{id} until the job leaves active state (via stub) or disappears.
    In unit tests with mock_registry the debate completes nearly instantly."""
    # We don't have GET /jobs/{id} yet (Task 6.5). Poll active registry directly.
    from consilium_server.api.state import get_state

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        h = get_state().get(job_id)
        if h is None:
            return  # unregistered = finished
        time.sleep(0.01)


def test_submit_requires_auth(api_client):
    r = api_client.post(
        "/jobs", json={"topic": "t", "template": "quick_check"}
    )
    assert r.status_code == 401


def test_submit_minimal_returns_202(api_client, authed_headers, mock_registry):
    r = api_client.post(
        "/jobs",
        json={"topic": "тест", "template": "quick_check"},
        headers=authed_headers,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["job_id"] >= 1
    assert body["status"] in ("queued", "running")
    assert body["estimated_cost_usd"] > 0
    _wait_for_job(api_client, body["job_id"], authed_headers)


def test_submit_unknown_template_returns_404(api_client, authed_headers):
    r = api_client.post(
        "/jobs",
        json={"topic": "t", "template": "does_not_exist"},
        headers=authed_headers,
    )
    assert r.status_code == 404


def test_submit_invalid_body_pack_and_context_returns_422(
    api_client, authed_headers
):
    r = api_client.post(
        "/jobs",
        json={
            "topic": "t",
            "template": "quick_check",
            "pack": "x",
            "context_block": "y",
        },
        headers=authed_headers,
    )
    assert r.status_code == 422


def test_submit_rejects_cost_over_per_job_cap(
    api_client, authed_headers, monkeypatch, mock_registry, tmp_path
):
    """With per_job_cap tight enough, product_concept preview exceeds it → 402."""
    limits_file = tmp_path / "limits.yaml"
    limits_file.write_text("max_cost_per_job_usd: 0.001\n")
    monkeypatch.setenv("CONSILIUM_LIMITS_FILE", str(limits_file))

    r = api_client.post(
        "/jobs",
        json={"topic": "тема", "template": "product_concept"},
        headers=authed_headers,
    )
    assert r.status_code == 402, r.text
    detail = r.json()["detail"]
    assert "per_job_cap_exceeded" in detail["violations"]


def test_submit_over_concurrency_limit_returns_429(
    api_client, authed_headers, mock_registry
):
    """Tighten the singleton to 1 concurrent, pre-fill the slot, then submit
    one job — it must be rejected with 429."""
    from consilium_server.api import state as state_module
    from consilium_server.api.state import JobHandle

    state_module._state = state_module.ServerState(
        max_concurrent=1, min_seconds_between=0
    )
    # Pre-fill the only slot with a dummy handle.
    state_module.get_state().register(
        JobHandle(job_id=9999, task=None, topic="placeholder")
    )

    r = api_client.post(
        "/jobs",
        json={"topic": "t2", "template": "quick_check"},
        headers=authed_headers,
    )
    assert r.status_code == 429, r.text
