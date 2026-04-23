from fastapi.testclient import TestClient

from consilium_server.api.main import app

client = TestClient(app)


def test_protected_endpoint_rejects_request_without_auth(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "secret123")
    r = client.get("/jobs")
    assert r.status_code == 401


def test_protected_endpoint_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "secret123")
    r = client.get("/jobs", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_protected_endpoint_rejects_malformed_scheme(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "secret123")
    r = client.get("/jobs", headers={"Authorization": "Basic secret123"})
    assert r.status_code == 401


def test_protected_endpoint_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "secret123")
    r = client.get("/jobs", headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 200


def test_health_endpoint_open_even_with_token_set(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "secret123")
    r = client.get("/health")
    assert r.status_code == 200


def test_missing_token_env_returns_500(monkeypatch):
    """Fail-safe: if env is not configured, refuse to accept any token."""
    monkeypatch.delenv("CONSILIUM_API_TOKEN", raising=False)
    r = client.get("/jobs", headers={"Authorization": "Bearer anything"})
    assert r.status_code == 500
