"""Smoke tests for the CLI dispatcher. Calls main() directly; subprocess
tests live under tests/integration/."""
from __future__ import annotations

import pytest

from consilium_cli.main import main


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


def test_subcommand_routes_to_stub(capsys):
    rc = main(["jobs"])
    assert rc == 0
    assert "jobs" in capsys.readouterr().out.lower()


def test_positional_topic_routes_to_debate(capsys):
    """`consilium "тема"` should dispatch to the debate subcommand."""
    rc = main(["some topic"])
    assert rc == 0
    # The stub prints "consilium debate — not yet implemented"
    assert "debate" in capsys.readouterr().out.lower()


def test_explicit_debate_subcommand(capsys):
    rc = main(["debate", "topic"])
    assert rc == 0
    assert "debate" in capsys.readouterr().out.lower()
