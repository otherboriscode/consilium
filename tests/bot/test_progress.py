"""ProgressPoster — throttling, coalescing, duplicate-suppression."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from consilium_server.bot.progress import ProgressPoster


def _make_poster(min_interval: float = 0.1) -> tuple[ProgressPoster, AsyncMock]:
    bot = AsyncMock()
    poster = ProgressPoster(
        bot, chat_id=1, message_id=2, min_interval=min_interval
    )
    return poster, bot.edit_message_text


@pytest.mark.asyncio
async def test_first_push_flushes_immediately():
    poster, edit = _make_poster(min_interval=1.0)
    await poster.push("first")
    edit.assert_awaited_once()
    assert edit.await_args.args[0] == "first"


@pytest.mark.asyncio
async def test_rapid_pushes_are_coalesced():
    """Three pushes in quick succession → one immediate flush + one delayed
    flush carrying only the LAST text."""
    poster, edit = _make_poster(min_interval=0.05)
    await poster.push("a")  # flushes immediately
    await poster.push("b")  # scheduled
    await poster.push("c")  # replaces pending text
    await asyncio.sleep(0.15)  # wait for the delayed flush
    assert edit.await_count == 2
    # First = "a", second = "c" (not "b")
    calls = [c.args[0] for c in edit.await_args_list]
    assert calls == ["a", "c"]


@pytest.mark.asyncio
async def test_duplicate_text_is_not_flushed_twice():
    poster, edit = _make_poster(min_interval=0.01)
    await poster.push("same")
    await asyncio.sleep(0.05)
    await poster.push("same")  # same text — should be suppressed
    await asyncio.sleep(0.05)
    assert edit.await_count == 1


@pytest.mark.asyncio
async def test_flush_now_pushes_pending_immediately():
    poster, edit = _make_poster(min_interval=1.0)
    await poster.push("a")  # immediate
    await poster.push("b")  # pending (within cooldown)
    await poster.flush_now()
    calls = [c.args[0] for c in edit.await_args_list]
    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_flush_swallows_edit_errors(caplog):
    """`edit_message_text` may raise (MessageNotModified, network blip).
    The poster must not propagate — progress reporting is best-effort."""
    bot = AsyncMock()
    bot.edit_message_text.side_effect = RuntimeError("network down")
    poster = ProgressPoster(bot, chat_id=1, message_id=2, min_interval=0.01)
    await poster.push("x")  # must not raise
    # No assertion on caplog — we just want to survive the exception.
