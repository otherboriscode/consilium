from fastapi.testclient import TestClient

from consilium_server.api.main import app

client = TestClient(app)


def test_health_endpoint_is_open_and_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_app_title_and_version_set():
    assert app.title == "Consilium"
    assert app.version.startswith("0.")
