"""CLI budget + templates subcommand tests."""
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


# ---------- budget ----------


@respx.mock
def test_budget_usage(capsys):
    respx.get(f"{BASE}/budget/usage").respond(
        200,
        json={
            "today_usd": 2.5,
            "month_usd": 47.0,
            "jobs_today": 3,
            "jobs_this_month": 19,
            "by_model": {"claude-sonnet": 30.0, "gpt-5": 17.0},
        },
    )
    rc = main(["budget", "usage"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "$2.50" in out
    assert "$47.00" in out
    assert "claude-sonnet" in out


@respx.mock
def test_budget_limits(capsys):
    respx.get(f"{BASE}/budget/limits").respond(
        200,
        json={"max_cost_per_job_usd": 25.0, "monthly_budget_usd": 500.0},
    )
    rc = main(["budget", "limits"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "max_cost_per_job_usd" in out
    assert "25" in out


@respx.mock
def test_budget_daily(capsys):
    respx.get(f"{BASE}/budget/daily").respond(
        200, json={"summary_markdown": "# Today\n$2.50 spent"}
    )
    rc = main(["budget", "daily"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# Today" in out
    assert "$2.50" in out


@respx.mock
def test_budget_alerts_none(capsys):
    respx.get(f"{BASE}/budget/alerts").respond(200, json={"fired": []})
    rc = main(["budget", "alerts"])
    assert rc == 0
    assert "активных алертов" in capsys.readouterr().out


@respx.mock
def test_budget_alerts_fired(capsys):
    respx.get(f"{BASE}/budget/alerts").respond(
        200,
        json={
            "fired": [
                {
                    "threshold": 80,
                    "month_cost_usd": 240.0,
                    "monthly_cap_usd": 300.0,
                    "message": "80% of monthly budget",
                }
            ]
        },
    )
    rc = main(["budget", "alerts"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "80" in out
    assert "$240.00" in out


# ---------- templates ----------


@respx.mock
def test_templates_list(capsys):
    respx.get(f"{BASE}/templates").respond(
        200, json=["quick_check", "product_concept"]
    )
    rc = main(["templates", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "quick_check" in out
    assert "product_concept" in out


@respx.mock
def test_templates_show(capsys):
    respx.get(f"{BASE}/templates/product_concept").respond(
        200,
        json={
            "name": "product_concept",
            "title": "Product Concept Debate",
            "description": "For fleshing out a product idea",
            "rounds": 2,
            "version": "abc123",
            "participants": [
                {
                    "role": "architect",
                    "model": "claude-sonnet-4.5",
                    "deep": True,
                },
                {
                    "role": "critic",
                    "model": "gpt-5",
                    "deep": False,
                },
            ],
            "judge": {"model": "claude-haiku-4.5"},
        },
    )
    rc = main(["templates", "show", "product_concept"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "product_concept" in out
    assert "architect" in out
    assert "critic" in out
    assert "claude-haiku-4.5" in out


@respx.mock
def test_templates_show_404(capsys):
    respx.get(f"{BASE}/templates/nope").respond(
        404, json={"detail": "not found"}
    )
    rc = main(["templates", "show", "nope"])
    assert rc == 2
