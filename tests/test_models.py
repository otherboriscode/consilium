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


def test_job_result_json_roundtrip():
    """Preparing for Phase 4 (archive): JobResult must serialize to JSON and
    deserialize back to an equal object. Catches any dataclass/pydantic friction
    early."""
    cfg = JobConfig(
        topic="Roundtrip topic",
        participants=[
            ParticipantConfig(model="claude-opus-4-7", role="architect", system_prompt="s")
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
    )
    msg = RoundMessage(
        round_index=0,
        role_slug="architect",
        text="some position",
        error=None,
        usage=CallUsage(input_tokens=100, output_tokens=50, cache_read_tokens=10),
        duration_seconds=1.23,
        cost_usd=0.0042,
    )
    judge_out = JudgeOutput(
        raw_markdown="# TL;DR\nfull",
        tldr="full",
        consensus=["a"],
        disagreements=["b"],
        unique_contributions={"architect": "x"},
        blind_spots=["c"],
        recommendation="ship",
        scores={"architect": 3},
    )
    original = JobResult(
        job_id=999,
        config=cfg,
        messages=[msg],
        judge=judge_out,
        judge_truncated=False,
        duration_seconds=12.3,
        total_cost_usd=0.0042,
        cost_breakdown={"claude-opus-4-7": 0.0042},
        started_at=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 22, 12, 0, 12, tzinfo=timezone.utc),
    )
    data = original.model_dump(mode="json")

    # Re-hydrate through JSON string to guarantee no in-memory references leak.
    import json as _json
    roundtrip = JobResult.model_validate(_json.loads(_json.dumps(data)))

    assert roundtrip.job_id == original.job_id
    assert roundtrip.config.topic == original.config.topic
    assert roundtrip.messages[0].text == "some position"
    assert roundtrip.messages[0].usage.input_tokens == 100
    assert roundtrip.messages[0].usage.cache_read_tokens == 10
    assert roundtrip.judge is not None
    assert roundtrip.judge.scores == {"architect": 3}
    assert roundtrip.started_at == original.started_at


def test_job_config_accepts_optional_project():
    cfg = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="claude-opus-4-7", role="r", system_prompt="s")
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        project="tanaa-ubud",
    )
    assert cfg.project == "tanaa-ubud"


def test_job_config_project_defaults_to_none():
    cfg = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="claude-opus-4-7", role="r", system_prompt="s")
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
    )
    assert cfg.project is None
