"""Smoke tests for the CLI dispatcher. Calls main() directly; subprocess
tests live under tests/integration/."""
from __future__ import annotations

import pytest

from consilium_cli.main import main  # noqa: F401


def test_help_lists_all_subcommands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for sub in ("debate", "jobs", "archive", "packs", "budget", "templates"):
        assert sub in out


def test_no_args_errors(capsys):
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code != 0


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "consilium" in out.lower()


def test_jobs_subcommand_requires_config(capsys, monkeypatch):
    """With no env/yaml config, all subcommands fail cleanly with exit 2
    instead of crashing."""
    monkeypatch.delenv("CONSILIUM_API_BASE", raising=False)
    monkeypatch.delenv("CONSILIUM_API_TOKEN", raising=False)
    monkeypatch.setenv("CONSILIUM_CLIENT_CONFIG", "/nonexistent/never.yaml")
    with pytest.raises(ValueError, match="Client config incomplete"):
        main(["jobs"])


def test_positional_topic_routes_to_debate(capsys, monkeypatch):
    """`consilium "тема"` should dispatch to the debate subcommand. With no
    config the debate command bails before hitting the API — but the
    argparse dispatch itself must succeed."""
    monkeypatch.delenv("CONSILIUM_API_BASE", raising=False)
    monkeypatch.delenv("CONSILIUM_API_TOKEN", raising=False)
    monkeypatch.setenv("CONSILIUM_CLIENT_CONFIG", "/nonexistent/never.yaml")
    rc = main(["some topic"])
    # debate-command bails on missing config with rc=2
    assert rc == 2
    err = capsys.readouterr().err
    assert "Client config" in err or "incomplete" in err


def test_debate_subcommand_without_topic_errors(capsys):
    rc = main(["debate"])
    assert rc == 2
    assert "тема" in capsys.readouterr().err.lower()
