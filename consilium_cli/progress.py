"""
Render SSE progress events as plain stdout lines.

No Rich Live/TUI — the plan deliberately keeps output log-style so it
composes with pipes, tees, and crontab. Each event gets one line with a
timestamp so long debates are still reviewable after the fact.
"""
from __future__ import annotations

import sys
from datetime import datetime


def render_event(event: dict) -> None:
    """Print one line per SSE event. Flush so tail -f style consumption works."""
    kind = event.get("kind", "?")
    ts = datetime.now().strftime("%H:%M:%S")
    if kind == "round_started":
        msg = f"⏳ раунд {event.get('round_index', 0)} пошёл"
    elif kind == "participant_completed":
        role = event.get("role_slug") or "?"
        msg = f"✓ {role} (раунд {event.get('round_index', 0)})"
    elif kind == "participant_failed":
        role = event.get("role_slug") or "?"
        err = event.get("error") or event.get("message") or "?"
        msg = f"⚠ {role}: {err}"
    elif kind == "round_completed":
        msg = f"✅ раунд {event.get('round_index', 0)} завершён"
    elif kind == "judge_started":
        msg = "⚖️ судья синтезирует"
    elif kind == "judge_completed":
        msg = "⚖️ судья готов"
    elif kind == "judge_failed":
        msg = f"❌ судья сорвался: {event.get('error') or event.get('message') or '?'}"
    elif kind == "done":
        msg = f"✅ завершено — {event.get('message', '')}"
    elif kind == "error":
        msg = f"❌ ошибка: {event.get('message', '')}"
    else:
        msg = f"{kind}: {event.get('message', '')}"
    print(f"[{ts}] {msg}", flush=True)
    sys.stdout.flush()


def extract_tldr(md: str) -> str:
    """Pull the text between '# TL;DR' and the next '# Header'. Empty string
    if not found. Mirrors the bot-side helper so both surfaces agree."""
    import re

    tldr_re = re.compile(r"^#+\s*TL;DR\s*$", re.IGNORECASE | re.MULTILINE)
    h1_re = re.compile(r"^#\s+.+", re.MULTILINE)
    m = tldr_re.search(md)
    if not m:
        return ""
    tail = md[m.end():]
    next_h = h1_re.search(tail)
    section = tail[: next_h.start()] if next_h else tail
    return section.strip()[:2000]


def slugify(text: str, max_len: int = 40) -> str:
    """Filename-safe slug for output paths. Cyrillic-tolerant."""
    import re

    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w\-а-яё]", "", text, flags=re.UNICODE)
    return text[:max_len] or "debate"
