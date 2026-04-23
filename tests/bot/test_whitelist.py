"""Whitelist middleware: allowed ids pass through, others are silently dropped."""
from __future__ import annotations

import pytest

from consilium_server.bot.middlewares import WhitelistMiddleware, _parse_allowlist


class _FakeUser:
    def __init__(self, user_id: int, username: str | None = None) -> None:
        self.id = user_id
        self.username = username


@pytest.mark.asyncio
async def test_allowed_user_passes_through():
    mw = WhitelistMiddleware(allowed={12345})
    handled: list[str] = []

    async def handler(event, data):
        handled.append("called")
        return "ok"

    result = await mw(handler, object(), {"event_from_user": _FakeUser(12345)})
    assert result == "ok"
    assert handled == ["called"]


@pytest.mark.asyncio
async def test_blocked_user_is_silently_dropped():
    mw = WhitelistMiddleware(allowed={12345})
    called: list[bool] = []

    async def handler(event, data):
        called.append(True)
        return "should-not-run"

    result = await mw(
        handler, object(), {"event_from_user": _FakeUser(99999, "stranger")}
    )
    assert result is None
    assert called == []


@pytest.mark.asyncio
async def test_missing_user_is_also_dropped():
    """Channel posts / anonymous updates land here — we drop them since
    this is a strictly-private bot."""
    mw = WhitelistMiddleware(allowed={12345})
    handled: list[bool] = []

    async def handler(event, data):
        handled.append(True)
        return "ok"

    result = await mw(handler, object(), {})
    assert result is None
    assert handled == []


def test_parse_allowlist_skips_garbage():
    ids = _parse_allowlist("123, 456, garbage, 789")
    assert ids == {123, 456, 789}


def test_parse_allowlist_empty_string_yields_empty_set():
    assert _parse_allowlist("") == set()
    assert _parse_allowlist(" , , ") == set()


def test_parse_allowlist_trims_whitespace():
    assert _parse_allowlist("  111  ,  222  ") == {111, 222}


def test_empty_allowlist_warns_and_still_drops_everyone(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="consilium.bot")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    _ = WhitelistMiddleware()
    assert any("empty" in rec.message.lower() for rec in caplog.records)
