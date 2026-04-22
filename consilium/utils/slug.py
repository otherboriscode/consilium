"""
Единый slugifier для имён файлов/путей.

Сохраняет кириллицу — чтобы имена архивных файлов были осмысленны для
русскоязычных тем. Всё остальное (пробелы, пунктуация, латиница в других
регистрах) приводится к lowercase + разделяется `-`.
"""
from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9а-яё]+")


def slugify(text: str, *, max_length: int = 60) -> str:
    """Lowercase slug with latin/digit/cyrillic runs joined by `-`.

    - Пустой результат → 'debate' (безопасный fallback для filename).
    - `max_length` обрезает по длине ПОСЛЕ нормализации.
    """
    s = text.lower().strip()
    s = _SLUG_RE.sub("-", s)
    s = s.strip("-")
    if not s:
        return "debate"
    return s[:max_length] if len(s) > max_length else s
