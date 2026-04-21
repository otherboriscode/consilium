from datetime import datetime, timezone

from consilium.models import (
    JobConfig,
    JobResult,
    JudgeConfig,
    JudgeOutput,
    ParticipantConfig,
    RoundMessage,
)
from consilium.providers.base import CallUsage
from consilium.transcript import build_transcript_for_next_round, format_full_markdown


def _msg(round_idx, role, text=None, error=None):
    return RoundMessage(
        round_index=round_idx,
        role_slug=role,
        text=text,
        error=error,
        usage=CallUsage(input_tokens=100, output_tokens=50),
        duration_seconds=1.0,
        cost_usd=0.01,
    )


def test_transcript_empty_when_no_messages():
    assert build_transcript_for_next_round([]) == ""


def test_transcript_groups_by_round_with_headers():
    messages = [
        _msg(0, "architect", text="A0"),
        _msg(0, "marketer", text="M0"),
        _msg(1, "architect", text="A1"),
    ]
    out = build_transcript_for_next_round(messages)
    assert "# Раунд 0" in out
    assert "# Раунд 1" in out
    assert "## architect" in out
    assert "A0" in out
    assert "M0" in out
    assert "A1" in out
    assert out.index("# Раунд 0") < out.index("# Раунд 1")


def test_transcript_marks_failed_participants():
    messages = [
        _msg(0, "engineer", error="timeout"),
        _msg(0, "architect", text="A0"),
    ]
    out = build_transcript_for_next_round(messages)
    assert "## engineer" in out
    assert "не ответил" in out.lower() or "timeout" in out.lower()


def test_format_full_markdown_has_frontmatter_and_body():
    cfg = JobConfig(
        topic="Test topic",
        participants=[
            ParticipantConfig(model="claude-opus-4-7", role="architect", system_prompt="s")
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
    )
    judge = JudgeOutput(
        raw_markdown="RAW",
        tldr="t",
        consensus=[],
        disagreements=[],
        unique_contributions={},
        blind_spots=[],
        recommendation="r",
        scores={},
    )
    result = JobResult(
        job_id=42,
        config=cfg,
        messages=[_msg(0, "architect", text="A0")],
        judge=judge,
        duration_seconds=10.5,
        total_cost_usd=0.15,
        cost_breakdown={"claude-opus-4-7": 0.10, "claude-haiku-4-5": 0.05},
        started_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 21, 10, 0, 10, tzinfo=timezone.utc),
    )
    md = format_full_markdown(result)
    assert md.startswith("---\n")
    assert "job_id: 42" in md
    assert "topic: " in md and "Test topic" in md
    assert "cost_usd: 0.15" in md
    assert "# Раунд 0" in md
    assert "# Синтез" in md or "# TL;DR" in md
    assert "RAW" in md
