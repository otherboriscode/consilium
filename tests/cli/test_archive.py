"""CLI archive subcommand tests — respx-mocked."""
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
def test_archive_search_renders_rows(capsys):
    respx.get(f"{BASE}/archive/search").respond(
        200,
        json=[
            {
                "job_id": 7,
                "status": "completed",
                "template": "quick_check",
                "topic": "best product choice",
                "project": None,
                "started_at": "2026-04-23T10:00:00+00:00",
                "cost_usd": 0.42,
            }
        ],
    )
    rc = main(["archive", "search", "product"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "#   7" in out
    assert "best product" in out


@respx.mock
def test_archive_search_empty(capsys):
    respx.get(f"{BASE}/archive/search").respond(200, json=[])
    rc = main(["archive", "search", "unknown"])
    assert rc == 0
    assert "не найдено" in capsys.readouterr().out


@respx.mock
def test_archive_show_prints_md(capsys):
    respx.get(f"{BASE}/archive/42/md").respond(200, text="# Title\nbody")
    rc = main(["archive", "show", "42"])
    assert rc == 0
    assert "# Title" in capsys.readouterr().out


@respx.mock
def test_archive_show_404(capsys):
    respx.get(f"{BASE}/archive/999/md").respond(
        404, json={"detail": "not found"}
    )
    rc = main(["archive", "show", "999"])
    assert rc == 2


@respx.mock
def test_archive_get_saves_to_default_path(tmp_path, monkeypatch, capsys):
    respx.get(f"{BASE}/archive/42/md").respond(200, text="# Content")
    monkeypatch.chdir(tmp_path)
    rc = main(["archive", "get", "42"])
    assert rc == 0
    out = tmp_path / "consilium" / "0042.md"
    assert out.read_text() == "# Content"


@respx.mock
def test_archive_get_saves_to_given_path(tmp_path, capsys):
    respx.get(f"{BASE}/archive/42/md").respond(200, text="X")
    target = tmp_path / "x.md"
    rc = main(["archive", "get", "42", str(target)])
    assert rc == 0
    assert target.read_text() == "X"


@respx.mock
def test_archive_stats_by_model(capsys):
    respx.get(f"{BASE}/archive/stats/by-model").respond(
        200,
        json=[
            {"model": "claude-sonnet", "n": 5, "total_cost_usd": 10.0},
            {"model": "gpt-5", "n": 3, "total_cost_usd": 4.5},
        ],
    )
    rc = main(["archive", "stats", "--by", "model"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "claude-sonnet" in out
    assert "gpt-5" in out


@respx.mock
def test_archive_roi_empty(capsys):
    respx.get(f"{BASE}/archive/stats/roi").respond(200, json=[])
    rc = main(["archive", "roi"])
    assert rc == 0
    assert "недостаточно" in capsys.readouterr().out
