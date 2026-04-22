from datetime import datetime, timezone

import pytest
from consilium.models import (
    JobConfig,
    JobResult,
    JudgeConfig,
    JudgeOutput,
    ParticipantConfig,
    RoundMessage,
)
from consilium.providers.base import CallUsage


def test_participant_config_minimum():
    p = ParticipantConfig(
        model="claude-opus-4-7",
        role="architect",
        system_prompt="You are an architect.",
    )
    assert p.deep is False
    assert p.max_tokens == 2500
    assert p.timeout_seconds == 300


def test_participant_config_deep_overrides_timeout():
    p = ParticipantConfig(
        model="openai/o3-pro",
        role="marketer",
        system_prompt="...",
        deep=True,
        timeout_seconds=3600,
    )
    assert p.timeout_seconds == 3600


def test_job_config_rejects_zero_rounds():
    with pytest.raises(ValueError):
        JobConfig(
            topic="test",
            participants=[
                ParticipantConfig(model="claude-opus-4-7", role="architect", system_prompt="s")
            ],
            judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
            rounds=0,
        )


def test_job_config_rejects_empty_participants():
    with pytest.raises(ValueError):
        JobConfig(
            topic="test",
            participants=[],
            judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        )


def test_job_config_rejects_duplicate_role_slugs():
    with pytest.raises(ValueError):
        JobConfig(
            topic="test",
            participants=[
                ParticipantConfig(model="claude-opus-4-7", role="architect", system_prompt="s"),
                ParticipantConfig(model="openai/gpt-5", role="architect", system_prompt="s"),
            ],
            judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        )


def test_round_message_records_error_without_text():
    m = RoundMessage(
        round_index=1,
        role_slug="engineer",
        text=None,
        error="timeout",
        usage=CallUsage(input_tokens=0, output_tokens=0),
        duration_seconds=300.0,
        cost_usd=0.0,
    )
    assert m.text is None
    assert m.error == "timeout"


def test_judge_output_roundtrip():
    j = JudgeOutput(
        raw_markdown="...",
        tldr="Consensus on X.",
        consensus=["X is important"],
        disagreements=["On pricing: A vs B"],
        unique_contributions={"architect": "system view", "marketer": "naming"},
        blind_spots=["regulation"],
        recommendation="Ship with X.",
        scores={"architect": 3, "marketer": 2},
    )
    data = j.model_dump()
    restored = JudgeOutput.model_validate(data)
    assert restored == j


def test_job_result_total_cost_matches_breakdown():
    result = JobResult(
        job_id=1,
        config=JobConfig(
            topic="t",
            participants=[
                ParticipantConfig(model="claude-opus-4-7", role="architect", system_prompt="s")
            ],
            judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        ),
        messages=[],
        judge=None,
        duration_seconds=0.0,
        total_cost_usd=1.50,
        cost_breakdown={"claude-opus-4-7": 1.00, "claude-haiku-4-5": 0.50},
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    assert sum(result.cost_breakdown.values()) == pytest.approx(result.total_cost_usd)


def test_judge_output_clamps_out_of_range_scores():
    j = JudgeOutput(
        raw_markdown="...",
        tldr="t",
        consensus=[],
        disagreements=[],
        unique_contributions={},
        blind_spots=[],
        recommendation="r",
        scores={"architect": 7, "marketer": -1, "analyst": 2},
    )
    assert j.scores == {"architect": 3, "marketer": 0, "analyst": 2}
