"""CORS / body-size / request-id middleware tests."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from consilium_server.api.main import app

client = TestClient(app)


def test_health_response_includes_request_id(authed_env):
    r = client.get("/health")
    assert r.status_code == 200
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) >= 4


def test_echoes_request_id_when_client_sends_one(authed_env):
    rid = "abcd1234"
    r = client.get("/health", headers={"x-request-id": rid})
    assert r.headers["x-request-id"] == rid


def test_body_size_limit_rejects_oversized_content_length(
    authed_env, authed_headers
):
    """A 15 MB Content-Length exceeds the 10 MB cap. The guard rejects before
    we allocate the body, so we can simulate with just a header."""
    r = client.post(
        "/jobs",
        json={"topic": "t", "template": "quick_check"},
        headers={**authed_headers, "content-length": str(15 * 1024 * 1024)},
    )
    assert r.status_code == 413
    assert "exceeds" in r.json()["detail"].lower()


def test_body_size_limit_allows_normal_requests(authed_env, authed_headers):
    r = client.get("/health", headers=authed_headers)
    assert r.status_code == 200


def test_cors_middleware_disabled_when_env_missing(monkeypatch):
    monkeypatch.delenv("CONSILIUM_CORS_ORIGINS", raising=False)
    # Fresh import with no env — middleware stack should not include CORS.
    import consilium_server.api.main as api_main

    importlib.reload(api_main)
    has_cors = any(
        "CORSMiddleware" in str(type(mw).__name__)
        or "CORSMiddleware" in repr(mw)
        for mw in getattr(api_main.app, "user_middleware", [])
    )
    assert not has_cors


def test_cors_middleware_enabled_with_env(monkeypatch):
    monkeypatch.setenv("CONSILIUM_CORS_ORIGINS", "https://example.com")
    import consilium_server.api.main as api_main

    importlib.reload(api_main)
    has_cors = any(
        "CORSMiddleware" in repr(mw)
        for mw in getattr(api_main.app, "user_middleware", [])
    )
    assert has_cors
    # Reload again without env to leave global state clean for other tests
    monkeypatch.delenv("CONSILIUM_CORS_ORIGINS")
    importlib.reload(api_main)
