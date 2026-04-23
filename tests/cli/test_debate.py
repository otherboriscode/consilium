"""
Unit tests for `consilium debate` helpers — progress rendering, slug,
tldr extract, and the `_print_preview` formatter.

End-to-end flow (preview → submit → stream → save) is covered in the
integration suite (Task 8.12).
"""
from __future__ import annotations

from consilium_cli.commands.debate import _print_preview
from consilium_cli.progress import extract_tldr, render_event, slugify
from consilium_client.client import ParticipantPreviewRow, PreviewResult


def test_slugify_cyrillic_and_punctuation():
    assert slugify("Tanaa — commercial infra!") == "tanaa--commercial-infra"
    assert slugify("Концепция: продукт") == "концепция-продукт"
    assert slugify("") == "debate"


def test_slugify_truncates():
    long = "x" * 200
    assert len(slugify(long)) <= 40


def test_extract_tldr_between_headers():
    md = (
        "# Тема\n\nfoo\n\n"
        "# TL;DR\nSummary here\n\n"
        "# Next section\nbar\n"
    )
    assert "Summary here" in extract_tldr(md)
    assert "Next section" not in extract_tldr(md)


def test_extract_tldr_missing():
    assert extract_tldr("no header") == ""


def test_render_event_known_kinds(capsys):
    for kind in (
        "round_started",
        "participant_completed",
        "round_completed",
        "judge_started",
        "judge_completed",
        "done",
    ):
        render_event({"kind": kind, "round_index": 1, "role_slug": "x"})
    out = capsys.readouterr().out
    # At least one line per kind
    assert out.count("\n") == 6


def test_render_event_error(capsys):
    render_event({"kind": "error", "message": "boom"})
    out = capsys.readouterr().out
    assert "boom" in out


def test_print_preview_shows_all_fields(capsys):
    pv = PreviewResult(
        estimated_cost_usd=1.23,
        estimated_duration_seconds=180,
        context_tokens=5000,
        template="quick_check",
        rounds=2,
        participants=[
            ParticipantPreviewRow(
                role="architect",
                model="claude-sonnet-4.5",
                mode="deep",
                fit="full",
                estimated_cost_usd=0.0,
            ),
            ParticipantPreviewRow(
                role="critic",
                model="gpt-5",
                mode="fast",
                fit="summary",
                estimated_cost_usd=0.0,
            ),
        ],
        judge_model="claude-haiku-4.5",
        allowed=True,
        violations=[],
        violation_messages=[],
        warnings=["50% of daily spent"],
    )
    _print_preview(pv)
    out = capsys.readouterr().out
    assert "$1.23" in out
    assert "3 min" in out
    assert "5,000" in out
    assert "architect" in out
    assert "critic" in out
    assert "[summary]" in out
    assert "50% of daily" in out


def test_print_preview_surfaces_violations(capsys):
    pv = PreviewResult(
        estimated_cost_usd=100,
        estimated_duration_seconds=60,
        context_tokens=0,
        template="t",
        rounds=2,
        participants=[],
        judge_model="m",
        allowed=False,
        violations=["per_job_cap_exceeded"],
        violation_messages=["too expensive"],
        warnings=[],
    )
    _print_preview(pv)
    out = capsys.readouterr().out
    assert "too expensive" in out
    assert "⛔" in out
