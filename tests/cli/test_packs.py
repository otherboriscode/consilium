"""CLI packs subcommand tests — respx-mocked."""
from __future__ import annotations

import pytest
import respx

from consilium_cli.main import main


BASE = "http://api.test"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CONSILIUM_API_BASE", BASE)
    monkeypatch.setenv("CONSILIUM_API_TOKEN", "t")
    monkeypatch.setenv("CONSILIUM_CLIENT_CONFIG", "/nonexistent.yaml")


@respx.mock
def test_packs_list_empty(capsys):
    respx.get(f"{BASE}/packs").respond(200, json=[])
    rc = main(["packs", "list"])
    assert rc == 0
    assert "ни одного" in capsys.readouterr().out


@respx.mock
def test_packs_list_names(capsys):
    respx.get(f"{BASE}/packs").respond(200, json=["tanaa", "ubud"])
    rc = main(["packs", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tanaa" in out and "ubud" in out


@respx.mock
def test_packs_show(capsys):
    respx.get(f"{BASE}/packs/tanaa").respond(
        200,
        json={
            "name": "tanaa",
            "files": [
                {"name": "brief.md", "tokens": 1200, "type": "md"},
                {"name": "market.pdf", "tokens": 4500, "type": "pdf"},
            ],
            "total_tokens": 5700,
            "has_stale_files": False,
        },
    )
    rc = main(["packs", "show", "tanaa"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tanaa" in out
    assert "5,700" in out
    assert "brief.md" in out


@respx.mock
def test_packs_show_404(capsys):
    respx.get(f"{BASE}/packs/nope").respond(
        404, json={"detail": "Pack 'nope' not found"}
    )
    rc = main(["packs", "show", "nope"])
    assert rc == 2


@respx.mock
def test_packs_create(capsys, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("# hello\nworld")
    route = respx.post(f"{BASE}/packs/newpack").respond(
        200,
        json={"name": "newpack", "files": ["brief.md"], "total_tokens": 5},
    )
    rc = main(["packs", "create", "newpack", str(brief)])
    assert rc == 0
    assert route.called
    req = route.calls[0].request
    assert b"multipart/form-data" in req.headers["content-type"].encode()
    assert "newpack" in capsys.readouterr().out


def test_packs_create_missing_file_errors(capsys):
    rc = main(["packs", "create", "x", "/nonexistent/file.md"])
    assert rc == 2


@respx.mock
def test_packs_delete(capsys):
    respx.delete(f"{BASE}/packs/old").respond(204)
    rc = main(["packs", "delete", "old"])
    assert rc == 0
    assert "удалён" in capsys.readouterr().out


@respx.mock
def test_packs_delete_404(capsys):
    respx.delete(f"{BASE}/packs/nope").respond(
        404, json={"detail": "not found"}
    )
    rc = main(["packs", "delete", "nope"])
    assert rc == 2
