"""
Парсер markdown-ответа судьи в структуру `JudgeOutput`.

Работает как state-machine по строкам: смена `# Заголовок первого уровня`
переключает секцию, содержимое аккумулируется. Для секции «Уникальный вклад»
внутренняя смена `## role_slug` начинает новый вклад.

Парсер снисходителен к преамбуле/постамбуле вокруг канонических секций, но
падает `JudgeParseError`, если ни одной из ожидаемых секций не найдено.
"""
from __future__ import annotations

import re

from consilium.models import JudgeOutput

# Точные заголовки первого уровня, на которые смотрит парсер.
_SECTION_TLDR = "TL;DR"
_SECTION_CONSENSUS = "Точки консенсуса"
_SECTION_DISAGREEMENTS = "Точки разногласия"
_SECTION_CONTRIBUTIONS = "Уникальный вклад каждого участника"
_SECTION_BLIND_SPOTS = "Слепые зоны консилиума"
_SECTION_RECOMMENDATION = "Рекомендованное решение"
_SECTION_SCORES = "Оценка вклада"

_ALL_SECTIONS = frozenset(
    {
        _SECTION_TLDR,
        _SECTION_CONSENSUS,
        _SECTION_DISAGREEMENTS,
        _SECTION_CONTRIBUTIONS,
        _SECTION_BLIND_SPOTS,
        _SECTION_RECOMMENDATION,
        _SECTION_SCORES,
    }
)

_H1 = re.compile(r"^#\s+(.+?)\s*$")
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*-\s+(.+?)\s*$")
_SCORE_LINE = re.compile(r"^\s*-\s*([\w_]+)\s*:\s*(\d+)\s*$")


class JudgeParseError(Exception):
    """Raised when judge markdown cannot be interpreted."""


def parse_judge_markdown(text: str) -> JudgeOutput:
    """Parse markdown produced by the judge into a structured JudgeOutput.

    Preserves `raw_markdown = text`. Missing sections map to empty
    list/dict/string defaults. Raises `JudgeParseError` if no known section
    header is found at all.
    """
    lines = text.splitlines()

    current_section: str | None = None
    current_contribution_role: str | None = None
    section_buffers: dict[str, list[str]] = {name: [] for name in _ALL_SECTIONS}
    contributions: dict[str, list[str]] = {}

    for raw_line in lines:
        h1 = _H1.match(raw_line)
        if h1 and h1.group(1) in _ALL_SECTIONS:
            current_section = h1.group(1)
            current_contribution_role = None
            continue

        if current_section is None:
            continue  # still in preamble

        if current_section == _SECTION_CONTRIBUTIONS:
            h2 = _H2.match(raw_line)
            if h2:
                current_contribution_role = h2.group(1).strip()
                contributions[current_contribution_role] = []
                continue
            if current_contribution_role is not None:
                contributions[current_contribution_role].append(raw_line)
            continue

        section_buffers[current_section].append(raw_line)

    if current_section is None:
        raise JudgeParseError(
            "No known judge section headers found — output appears malformed"
        )

    # Extract bullet lists
    consensus = _extract_bullets(section_buffers[_SECTION_CONSENSUS])
    disagreements = _extract_bullets(section_buffers[_SECTION_DISAGREEMENTS])
    blind_spots = _extract_bullets(section_buffers[_SECTION_BLIND_SPOTS])

    # Scores: lines like "- role: N"
    scores: dict[str, int] = {}
    for line in section_buffers[_SECTION_SCORES]:
        m = _SCORE_LINE.match(line)
        if m:
            scores[m.group(1)] = int(m.group(2))

    tldr = _join_paragraph(section_buffers[_SECTION_TLDR])
    recommendation = _join_paragraph(section_buffers[_SECTION_RECOMMENDATION])

    unique_contributions = {
        role: _join_paragraph(lines).strip()
        for role, lines in contributions.items()
    }

    return JudgeOutput(
        raw_markdown=text,
        tldr=tldr,
        consensus=consensus,
        disagreements=disagreements,
        unique_contributions=unique_contributions,
        blind_spots=blind_spots,
        recommendation=recommendation,
        scores=scores,
    )


def _extract_bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        m = _LIST_ITEM.match(line)
        if m:
            items.append(m.group(1).strip())
    return items


def _join_paragraph(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line.strip()).strip()
