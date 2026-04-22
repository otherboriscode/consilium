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


def test_parse_h2_headers():
    md = (
        "## TL;DR\nsome tldr\n\n"
        "## Точки консенсуса\n- item\n\n"
        "## Точки разногласия\n- d1\n\n"
        "## Уникальный вклад каждого участника\n"
        "### architect\nspace logic\n\n"
        "## Слепые зоны консилиума\n- b1\n\n"
        "## Рекомендованное решение\nship it\n\n"
        "## Оценка вклада\n- architect: 3\n"
    )
    result = parse_judge_markdown(md)
    assert result.tldr == "some tldr"
    assert result.consensus == ["item"]
    assert result.disagreements == ["d1"]
    assert result.unique_contributions == {"architect": "space logic"}
    assert result.blind_spots == ["b1"]
    assert result.recommendation == "ship it"
    assert result.scores == {"architect": 3}


def test_parse_score_with_fraction():
    md = FIXTURE.replace("- architect: 3", "- architect: 3/3").replace("- marketer: 3", "- marketer: 2/3")
    result = parse_judge_markdown(md)
    assert result.scores["architect"] == 3
    assert result.scores["marketer"] == 2


def test_parse_score_with_asterisk_bullet():
    md = "# Оценка вклада\n* architect: 3\n* marketer: 2"
    result = parse_judge_markdown(md)
    assert result.scores == {"architect": 3, "marketer": 2}


def test_parse_score_clamps_to_valid_range(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    md = "# TL;DR\nt\n# Оценка вклада\n- architect: 7\n- marketer: -1"
    result = parse_judge_markdown(md)
    assert result.scores["architect"] == 3
    assert result.scores["marketer"] == 0
    assert "out of range" in caplog.text.lower() or "clamp" in caplog.text.lower()


def test_parse_missing_recommendation_section():
    md = "# TL;DR\nt\n# Точки консенсуса\n- x\n"
    result = parse_judge_markdown(md)
    assert result.recommendation == ""
    assert result.scores == {}
    assert result.raw_markdown == md


def test_parse_h3_subsections_in_unique_contributions():
    md = (
        "# TL;DR\nt\n\n"
        "# Уникальный вклад каждого участника\n"
        "### architect\nspace logic\n"
        "### marketer\nnaming"
    )
    result = parse_judge_markdown(md)
    assert result.unique_contributions == {
        "architect": "space logic",
        "marketer": "naming",
    }
