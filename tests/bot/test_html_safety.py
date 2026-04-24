"""
Guard against the class of bugs surfaced in prod when `/start` crashed with
`TelegramBadRequest: Unsupported start tag "запрос"`: any string literal
the bot sends with parse_mode="HTML" must not contain raw `<...>`
sequences that Telegram would interpret as unsupported tags.

This is a static scan of handler source code, not a runtime test — it
walks every literal sent via the HTML path and flags bare `<...>` that
isn't a known Telegram-supported tag.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_HANDLERS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "consilium_server"
    / "bot"
)

# Telegram supports this subset in parse_mode="HTML"
# (https://core.telegram.org/bots/api#html-style).
_ALLOWED_TAGS = {
    "b", "strong",
    "i", "em",
    "u", "ins",
    "s", "strike", "del",
    "span",
    "tg-spoiler",
    "a",
    "code",
    "pre",
    "blockquote",
    "tg-emoji",
    "br",
}

# Match `<word...>` — captures the tag name (letters/digits only).
_TAG_RE = re.compile(r"<(/?[A-Za-zа-яА-Я][\w-]*)", re.UNICODE)


def _extract_html_strings(py_file: Path) -> list[tuple[int, str]]:
    """Return (lineno, literal) for every string constant the file
    concatenates into an `.answer(..., parse_mode="HTML")` call."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    results: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Look for keyword parse_mode="HTML"
        uses_html = any(
            kw.arg == "parse_mode"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value == "HTML"
            for kw in node.keywords
        )
        if not uses_html:
            continue
        # Collect all string constants in positional args (also inside
        # BinOp/JoinedStr), recursively.
        def _collect(n):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                results.append((n.lineno, n.value))
            elif isinstance(n, ast.BinOp):
                _collect(n.left)
                _collect(n.right)
            elif isinstance(n, ast.JoinedStr):
                for v in n.values:
                    if isinstance(v, ast.Constant):
                        results.append((v.lineno, v.value or ""))

        for arg in node.args:
            _collect(arg)
    return results


def _find_bad_tags(text: str) -> list[str]:
    """Return tag names found in `text` that aren't in _ALLOWED_TAGS.
    Ignores anything already HTML-escaped (`&lt;`, `&gt;`)."""
    bad: list[str] = []
    for match in _TAG_RE.finditer(text):
        raw = match.group(1).lstrip("/").lower()
        if raw not in _ALLOWED_TAGS:
            bad.append(match.group(0))
    return bad


@pytest.mark.parametrize(
    "py_file",
    sorted(_HANDLERS_DIR.rglob("*.py")),
    ids=lambda p: str(p.relative_to(_HANDLERS_DIR.parent.parent)),
)
def test_html_strings_use_only_supported_tags(py_file):
    """Every HTML-mode string sent from the bot must stick to Telegram's
    supported tag set. Angle-bracketed placeholders (`<id>`, `<запрос>`)
    must be HTML-escaped as `&lt;id&gt;`."""
    offenders: list[str] = []
    for lineno, literal in _extract_html_strings(py_file):
        for bad in _find_bad_tags(literal):
            offenders.append(f"{py_file}:{lineno}  {bad!r}  in {literal[:80]!r}")
    if offenders:
        joined = "\n  ".join(offenders)
        pytest.fail(
            "HTML-mode strings contain unsupported tags (escape as &lt;...&gt;):\n  "
            + joined
        )
