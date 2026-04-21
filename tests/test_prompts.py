from consilium.models import ParticipantConfig
from consilium.prompts import (
    JUDGE_OUTPUT_SCHEMA_INSTRUCTION,
    build_judge_user_message,
    build_round_user_message,
)


def _p(role="architect", sp="You are architect."):
    return ParticipantConfig(model="claude-opus-4-7", role=role, system_prompt=sp)


def test_round0_message_contains_topic_and_instruction():
    msg = build_round_user_message(
        topic="Concept for Ubud",
        round_index=0,
        transcript_so_far="",
        participant=_p(),
        total_rounds=2,
    )
    assert "Concept for Ubud" in msg
    assert "Раунд 0" in msg
    assert "с чистого листа" in msg


def test_round1_message_includes_transcript_and_critique_instruction():
    transcript = "## architect\nSome position.\n\n## marketer\nOther position."
    msg = build_round_user_message(
        topic="Concept",
        round_index=1,
        transcript_so_far=transcript,
        participant=_p(),
        total_rounds=2,
    )
    assert transcript in msg
    assert "Раунд 1" in msg
    assert "слабость" in msg.lower() or "критик" in msg.lower()


def test_round2_message_is_final_position():
    msg = build_round_user_message(
        topic="T",
        round_index=2,
        transcript_so_far="prev rounds",
        participant=_p(),
        total_rounds=3,
    )
    assert "Раунд 2" in msg
    assert "финальн" in msg.lower()


def test_round_message_does_not_mutate_system_prompt():
    """Cache-hit invariant: system prompt goes separately, never embedded in user message."""
    participant = _p(sp="VERY SPECIFIC SYSTEM TEXT")
    m0 = build_round_user_message(
        topic="t",
        round_index=0,
        transcript_so_far="",
        participant=participant,
        total_rounds=2,
    )
    m1 = build_round_user_message(
        topic="t",
        round_index=1,
        transcript_so_far="...",
        participant=participant,
        total_rounds=2,
    )
    assert "VERY SPECIFIC SYSTEM TEXT" not in m0
    assert "VERY SPECIFIC SYSTEM TEXT" not in m1


def test_judge_message_contains_full_transcript_and_schema():
    full_transcript = "## architect R0\n...\n## marketer R0\n..."
    msg = build_judge_user_message(topic="T", full_transcript=full_transcript)
    assert full_transcript in msg
    assert JUDGE_OUTPUT_SCHEMA_INSTRUCTION in msg
    for header in (
        "TL;DR",
        "консенсус",
        "разногласия",
        "Уникальный вклад",
        "Слепые зоны",
        "Рекомендованное решение",
        "Оценка вклада",
    ):
        assert header in JUDGE_OUTPUT_SCHEMA_INSTRUCTION
