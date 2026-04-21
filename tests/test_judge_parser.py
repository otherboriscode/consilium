from pathlib import Path

import pytest

from consilium.judge_parser import JudgeParseError, parse_judge_markdown


FIXTURE = (Path(__file__).parent / "fixtures" / "judge_output_sample.md").read_text()


def test_parse_valid_sample_extracts_all_sections():
    parsed = parse_judge_markdown(FIXTURE)
    assert parsed.raw_markdown == FIXTURE
    assert "Консенсус: продукт жизнеспособен" in parsed.tldr
    assert len(parsed.consensus) == 3
    assert parsed.consensus[0].startswith("Продукт технически")
    assert len(parsed.disagreements) == 2
    assert any("architect" in c for c in parsed.unique_contributions)
    assert parsed.unique_contributions["architect"].startswith("Увидел связь")
    assert len(parsed.blind_spots) == 2
    assert "Запускать с новым именем" in parsed.recommendation
    assert parsed.scores == {
        "architect": 3,
        "marketer": 3,
        "analyst": 2,
        "engineer": 2,
        "devil_advocate": 3,
    }


def test_parse_preserves_raw_markdown():
    parsed = parse_judge_markdown(FIXTURE)
    assert parsed.raw_markdown == FIXTURE


def test_parse_missing_scores_section_returns_empty_scores():
    stripped = FIXTURE.split("# Оценка вклада")[0].rstrip() + "\n"
    parsed = parse_judge_markdown(stripped)
    assert parsed.scores == {}
    assert parsed.tldr  # остальные поля на месте


def test_parse_ignores_preamble_and_trailing_text():
    wrapped = "Introductory blather.\n\n" + FIXTURE + "\n\nTrailing note."
    parsed = parse_judge_markdown(wrapped)
    assert len(parsed.consensus) == 3
    assert parsed.scores["architect"] == 3


def test_parse_malformed_markdown_raises():
    with pytest.raises(JudgeParseError):
        parse_judge_markdown("это не markdown судьи вовсе")


def test_parse_score_with_extra_whitespace():
    parsed = parse_judge_markdown(FIXTURE.replace("- architect: 3", "-    architect  :   3"))
    assert parsed.scores["architect"] == 3
