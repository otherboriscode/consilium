from fastapi.testclient import TestClient

from consilium.archive import Archive
from consilium_server.api.main import app
from tests.test_archive_save import make_result

client = TestClient(app)


def test_usage_requires_auth(authed_env):
    r = client.get("/budget/usage")
    assert r.status_code == 401


def test_usage_empty_archive(authed_env, authed_headers):
    r = client.get("/budget/usage", headers=authed_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["today_usd"] == 0.0
    assert body["month_usd"] == 0.0
    assert body["by_model"] == {}


def test_usage_reflects_saved_job(authed_env, authed_headers):
    Archive().save_job(make_result(job_id=1))
    r = client.get("/budget/usage", headers=authed_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["jobs_this_month"] == 1
    assert body["month_usd"] > 0


def test_limits_endpoint_returns_defaults(authed_env, authed_headers):
    r = client.get("/budget/limits", headers=authed_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["max_cost_per_job_usd"] > 0
    assert body["max_cost_per_month_usd"] > 0


def test_daily_endpoint(authed_env, authed_headers):
    r = client.get("/budget/daily", headers=authed_headers)
    assert r.status_code == 200
    assert "summary_markdown" in r.json()


def test_alerts_read_only_default(authed_env, authed_headers):
    r = client.get("/budget/alerts", headers=authed_headers)
    assert r.status_code == 200
    assert "fired" in r.json()
