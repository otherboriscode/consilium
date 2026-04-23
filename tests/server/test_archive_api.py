from fastapi.testclient import TestClient

from consilium.archive import Archive
from consilium_server.api.main import app
from tests.test_archive_save import make_result

client = TestClient(app)


def _populate_archive(root_path):
    archive = Archive(root=root_path / "archive")
    archive.save_job(make_result(job_id=1, project="demo"))
    return archive


def test_search_requires_auth(authed_env):
    r = client.get("/archive/search?q=foo")
    assert r.status_code == 401


def test_search_returns_matches(authed_env, authed_headers):
    _populate_archive(authed_env / "data")
    r = client.get("/archive/search?q=Test", headers=authed_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(item["job_id"] == 1 for item in body)


def test_get_archived_job(authed_env, authed_headers):
    _populate_archive(authed_env / "data")
    r = client.get("/archive/1", headers=authed_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == 1
    assert body["config"]["topic"] == "Test topic"


def test_get_archived_job_404(authed_env, authed_headers):
    _populate_archive(authed_env / "data")
    r = client.get("/archive/9999", headers=authed_headers)
    assert r.status_code == 404


def test_get_markdown(authed_env, authed_headers):
    _populate_archive(authed_env / "data")
    r = client.get("/archive/1/md", headers=authed_headers)
    assert r.status_code == 200
    assert "Test topic" in r.text


def test_stats_by_model(authed_env, authed_headers):
    _populate_archive(authed_env / "data")
    r = client.get("/archive/stats/by-model", headers=authed_headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["key"] == "claude-opus-4-7" for row in rows)


def test_stats_roi(authed_env, authed_headers):
    _populate_archive(authed_env / "data")
    r = client.get("/archive/stats/roi", headers=authed_headers)
    assert r.status_code == 200
    rows = r.json()
    assert any(row["model"] == "claude-opus-4-7" for row in rows)
