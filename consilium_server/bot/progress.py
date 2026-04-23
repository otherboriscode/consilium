"""
Throttled in-place progress updates for a running debate.

Edits a single chat message as SSE events arrive, capped at one update
every `min_interval` seconds to stay well within Telegram's rate limits.
Latest text always wins — intermediate updates are coalesced.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot

logger = logging.getLogger("consilium.bot")


class ProgressPoster:
    def __init__(
        self,
        bot: Bot,
        *,
        chat_id: int,
        message_id: int,
        min_interval: float = 3.0,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.min_interval = min_interval
        self._last_update: float = 0.0
        self._pending_text: str | None = None
        self._flush_task: asyncio.Task | None = None
        self._last_flushed_text: str | None = None

    async def push(self, text: str) -> None:
        """Queue a new text. Flushes immediately if min_interval elapsed,
        else schedules a flush for when it does."""
        self._pending_text = text
        elapsed = time.monotonic() - self._last_update
        if elapsed >= self.min_interval:
            await self._flush()
        elif self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(
                self._delayed_flush(self.min_interval - elapsed)
            )

    async def flush_now(self) -> None:
        """Force-flush any pending text — used on terminal events."""
        if self._flush_task is not None:
            self._flush_task.cancel()
        await self._flush()

    async def _delayed_flush(self, wait: float) -> None:
        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return
        await self._flush()

    async def _flush(self) -> None:
        text = self._pending_text
        if text is None or text == self._last_flushed_text:
            # Nothing new — skip the edit to avoid `MessageNotModified`.
            return
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=self.message_id,
            )
        except Exception as e:
            # Telegram throws `MessageNotModified` if the body is unchanged,
            # and transient network errors are also possible — neither is
            # fatal for progress reporting.
            logger.debug("progress edit failed: %s", e)
        self._last_update = time.monotonic()
        self._last_flushed_text = text
        self._pending_text = None
