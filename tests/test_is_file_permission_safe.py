"""
Regression: systemd ProtectHome=yes makes Path.home() / ... raise
PermissionError on is_file() in Python 3.12 (used to return False).

load_template / list_templates / load_limits must degrade gracefully —
fall back to built-ins / defaults — instead of surfacing a 500 to API
clients.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from consilium.limits import DEFAULT_LIMITS, load_limits
from consilium.templates import (
    TemplateError,
    _is_file_safe,
    list_templates,
    load_template,
)


class _BlockedPath:
    """Stand-in for a Path-like object whose is_file() raises EACCES.
    Used to simulate a ProtectHome=yes sandbox without actually root'ing."""

    def __init__(self, real: Path) -> None:
        self._real = real

    def __truediv__(self, other):
        return _BlockedPath(self._real / other)

    def is_file(self):
        raise PermissionError(f"[Errno 13] Permission denied: {self._real}")

    def is_dir(self):
        raise PermissionError(f"[Errno 13] Permission denied: {self._real}")

    def glob(self, pattern):
        raise PermissionError(f"[Errno 13] Permission denied: {self._real}")


def test_is_file_safe_returns_false_on_permission_error(tmp_path):
    blocked = _BlockedPath(tmp_path / "nope")
    assert _is_file_safe(blocked) is False  # type: ignore[arg-type]


def test_is_file_safe_returns_false_on_missing_file(tmp_path):
    assert _is_file_safe(tmp_path / "missing.yaml") is False


def test_is_file_safe_returns_true_on_real_file(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("hi")
    assert _is_file_safe(f) is True


def test_load_template_falls_back_past_blocked_dir(tmp_path):
    """First dir is blocked (EACCES), second has the template → succeed."""
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    (fallback_dir / "smoke.yaml").write_text(
        "name: smoke\n"
        "title: smoke\n"
        "description: test\n"
        "rounds: 1\n"
        "participants:\n"
        "  - role: a\n"
        "    model: claude-sonnet-4.5\n"
        "    system_prompt: be brief\n"
        "judge:\n"
        "  model: claude-haiku-4.5\n"
        "  system_prompt: judge it\n"
    )
    blocked = _BlockedPath(tmp_path / "blocked")
    tpl = load_template("smoke", search_dirs=[blocked, fallback_dir])  # type: ignore[list-item]
    assert tpl.name == "smoke"


def test_load_template_still_raises_when_nothing_found(tmp_path):
    with pytest.raises(TemplateError, match="not found"):
        load_template("nope", search_dirs=[tmp_path])


def test_list_templates_skips_blocked_dir(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "a.yaml").write_text("")
    (ok / "b.yaml").write_text("")
    blocked = _BlockedPath(tmp_path / "blocked")
    names = list_templates(search_dirs=[blocked, ok])  # type: ignore[list-item]
    assert names == ["a", "b"]


def test_load_limits_falls_back_to_defaults_on_permission_error(monkeypatch):
    monkeypatch.delenv("CONSILIUM_LIMITS_FILE", raising=False)

    blocked = _BlockedPath(Path("/home/blocked/.config/consilium/limits.yaml"))
    with patch("consilium.limits._default_limits_path", return_value=blocked):
        result = load_limits()
    assert result == DEFAULT_LIMITS
