import time


def _wait_done(job_id: int, timeout: float = 5.0) -> None:
    from consilium_server.api.state import get_state

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if get_state().get(job_id) is None:
            return
        time.sleep(0.01)


def test_get_job_returns_active_then_archived(
    api_client, authed_headers, mock_registry
):
    submit = api_client.post(
        "/jobs",
        json={"topic": "тема", "template": "quick_check"},
        headers=authed_headers,
    )
    job_id = submit.json()["job_id"]

    _wait_done(job_id)

    r = api_client.get(f"/jobs/{job_id}", headers=authed_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] == job_id
    assert body["status"] == "completed"
    assert body["topic"] == "тема"
    assert body["rounds_completed"] == 1
    assert body["rounds_total"] == 1


def test_get_job_unknown_returns_404(api_client, authed_headers):
    r = api_client.get("/jobs/9999", headers=authed_headers)
    assert r.status_code == 404


def test_list_jobs_includes_active_and_archived(
    api_client, authed_headers, mock_registry
):
    r1 = api_client.post(
        "/jobs",
        json={"topic": "first", "template": "quick_check"},
        headers=authed_headers,
    )
    job_id = r1.json()["job_id"]
    _wait_done(job_id)

    lst = api_client.get("/jobs", headers=authed_headers)
    assert lst.status_code == 200
    items = lst.json()
    ids = {item["job_id"] for item in items}
    assert job_id in ids


def test_list_jobs_requires_auth(api_client):
    r = api_client.get("/jobs")
    assert r.status_code == 401
