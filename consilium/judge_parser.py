"""
Парсер markdown-ответа судьи в структуру `JudgeOutput`.

Работает как state-machine по строкам: смена канонического заголовка (H1–H3)
переключает секцию, содержимое аккумулируется. Для секции «Уникальный вклад»
внутренняя смена `## <role_slug>` / `### <role_slug>` начинает новый вклад.

Парсер снисходителен:
- Секционные заголовки опознаются на любом уровне H1–H3, сопоставление по
  substring в lowercase (модели часто меняют регистр и добавляют точки).
- Bullets: `-`, `*`, `•` — все валидны.
- Оценки: принимаются `3`, `3/3`, `3 / 3` — берём первое число.
- Оценки вне [0, 3] clamp-ятся с `logging.warning`.

Падает `JudgeParseError`, если ни одной из ожидаемых секций не найдено.
"""
from __future__ import annotations

import logging
import re

from consilium.models import JudgeOutput

logger = logging.getLogger(__name__)

# Canonical section names — lowercase-нормализованные, substring-сопоставление.
_SECTION_TLDR = "tl;dr"
_SECTION_CONSENSUS = "точки консенсуса"
_SECTION_DISAGREEMENTS = "точки разногласия"
_SECTION_CONTRIBUTIONS = "уникальный вклад"
_SECTION_BLIND_SPOTS = "слепые зоны"
_SECTION_RECOMMENDATION = "рекомендованное решение"
_SECTION_SCORES = "оценка вклада"

_CANONICAL_SECTIONS = (
    _SECTION_TLDR,
    _SECTION_CONSENSUS,
    _SECTION_DISAGREEMENTS,
    _SECTION_CONTRIBUTIONS,
    _SECTION_BLIND_SPOTS,
    _SECTION_RECOMMENDATION,
    _SECTION_SCORES,
)

_SECTION_HEADER = re.compile(r"^#{1,3}\s+(.+?)\s*$")  # H1/H2/H3 section boundary
_SUBSECTION_HEADER = re.compile(r"^#{2,4}\s+(.+?)\s*$")  # H2/H3/H4 inside contributions
_LIST_ITEM = re.compile(r"^\s*[-*•]\s+(.+?)\s*$")
_SCORE_LINE = re.compile(
    r"^\s*[-*•]\s*([^:]+?)\s*:\s*(-?\d+)(?:\s*/\s*\d+)?\s*$"
)


class JudgeParseError(Exception):
    """Raised when judge markdown cannot be interpreted."""


def _match_section(header_text: str) -> str | None:
    """Return the canonical section key if `header_text` matches any of them,
    else None. Matching is case-insensitive and based on substring containment —
    e.g. `TL;DR:` or `# TL;DR — краткое изложение` both map to `tl;dr`."""
    lowered = header_text.lower()
    for canonical in _CANONICAL_SECTIONS:
        if canonical in lowered:
            return canonical
    return None


def parse_judge_markdown(text: str) -> JudgeOutput:
    """Parse markdown produced by the judge into a structured JudgeOutput.

    Preserves `raw_markdown = text`. Missing sections map to empty
    list/dict/string defaults. Raises `JudgeParseError` if no known section
    header is found at all.
    """
    lines = text.splitlines()

    current_section: str | None = None
    current_contribution_role: str | None = None
    section_buffers: dict[str, list[str]] = {name: [] for name in _CANONICAL_SECTIONS}
    contributions: dict[str, list[str]] = {}

    for raw_line in lines:
        header_match = _SECTION_HEADER.match(raw_line)
        matched_section = (
            _match_section(header_match.group(1)) if header_match else None
        )
        if matched_section is not None:
            current_section = matched_section
            current_contribution_role = None
            continue

        if current_section is None:
            continue  # still in preamble

        if current_section == _SECTION_CONTRIBUTIONS:
            # Within contributions, an H2/H3/H4 that isn't a known top-level
            # section becomes a participant sub-header.
            sub_match = _SUBSECTION_HEADER.match(raw_line)
            if sub_match and _match_section(sub_match.group(1)) is None:
                current_contribution_role = sub_match.group(1).strip()
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

    consensus = _extract_bullets(section_buffers[_SECTION_CONSENSUS])
    disagreements = _extract_bullets(section_buffers[_SECTION_DISAGREEMENTS])
    blind_spots = _extract_bullets(section_buffers[_SECTION_BLIND_SPOTS])

    scores: dict[str, int] = {}
    for line in section_buffers[_SECTION_SCORES]:
        m = _SCORE_LINE.match(line)
        if m:
            role = m.group(1).strip().strip("*").strip()
            raw_score = int(m.group(2))
            clamped = max(0, min(3, raw_score))
            if clamped != raw_score:
                logger.warning(
                    "score %d for %r out of range [0, 3], clamping to %d",
                    raw_score,
                    role,
                    clamped,
                )
            scores[role] = clamped

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
