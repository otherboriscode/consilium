"""Tests for /packs endpoints: list / show / create / delete."""
from __future__ import annotations

from fastapi.testclient import TestClient

from consilium_server.api.main import app

client = TestClient(app)


def test_list_packs_requires_auth(authed_env):
    r = client.get("/packs")
    assert r.status_code == 401


def test_list_packs_empty(authed_env, authed_headers):
    r = client.get("/packs", headers=authed_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_list_show_delete_cycle(authed_env, authed_headers):
    # Create: upload two markdown files
    files = [
        ("files", ("a.md", b"# A\nhello", "text/markdown")),
        ("files", ("b.md", b"# B\nworld", "text/markdown")),
    ]
    r = client.post("/packs/demo", files=files, headers=authed_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "demo"
    assert set(body["files"]) == {"a.md", "b.md"}
    assert body["total_tokens"] > 0

    # List
    r = client.get("/packs", headers=authed_headers)
    assert "demo" in r.json()

    # Show
    r = client.get("/packs/demo", headers=authed_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "demo"
    assert len(r.json()["files"]) == 2

    # Delete
    r = client.delete("/packs/demo", headers=authed_headers)
    assert r.status_code == 204

    # List again → empty
    assert client.get("/packs", headers=authed_headers).json() == []


def test_show_missing_pack_returns_404(authed_env, authed_headers):
    r = client.get("/packs/nope", headers=authed_headers)
    assert r.status_code == 404


def test_delete_missing_pack_returns_404(authed_env, authed_headers):
    r = client.delete("/packs/nope", headers=authed_headers)
    assert r.status_code == 404


def test_create_without_files_returns_400(authed_env, authed_headers):
    r = client.post("/packs/demo", files=[], headers=authed_headers)
    # FastAPI's own validator may short-circuit this as 422; we accept either.
    assert r.status_code in (400, 422)


def test_create_overwrites_existing_pack(authed_env, authed_headers):
    def _upload(content: bytes):
        files = [("files", ("a.md", content, "text/markdown"))]
        return client.post("/packs/same", files=files, headers=authed_headers)

    r1 = _upload(b"# first content")
    r2 = _upload(b"# different")
    assert r1.status_code == 200 and r2.status_code == 200
    # show returns current state — content isn't in response, but pack still has 1 file
    r = client.get("/packs/same", headers=authed_headers)
    assert len(r.json()["files"]) == 1
