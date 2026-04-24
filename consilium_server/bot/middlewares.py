"""aiogram middlewares for the Consilium bot."""
from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from consilium_server.bot.client import ConsiliumClient

logger = logging.getLogger("consilium.bot")


def _parse_allowlist(env_value: str) -> set[int]:
    ids: set[int] = set()
    for part in env_value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning("ignoring non-integer user id %r in allowlist", part)
    return ids


class WhitelistMiddleware(BaseMiddleware):
    """Drop every update from a user not in TELEGRAM_ALLOWED_USER_IDS.

    Silent drop (no answer) — we don't want to confirm existence to strangers.
    One-user bot design; Boris sets his own Telegram user_id in env.
    """

    def __init__(self, allowed: set[int] | None = None) -> None:
        if allowed is None:
            allowed = _parse_allowlist(
                os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
            )
        self.allowed = allowed
        if not self.allowed:
            logger.warning(
                "TELEGRAM_ALLOWED_USER_IDS is empty — bot will drop ALL "
                "messages. Set the env var to your Telegram user_id."
            )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        # Diagnostic log: every update that enters the middleware. Keeps
        # the silent-drop UX but makes it obvious what's arriving.
        _preview = ""
        try:
            from aiogram.types import Message, CallbackQuery
            if isinstance(event, Message):
                _preview = f"message text={event.text!r}"
            elif isinstance(event, CallbackQuery):
                _preview = f"callback data={event.data!r}"
            else:
                _preview = f"type={type(event).__name__}"
        except Exception:  # noqa: BLE001
            pass
        logger.info(
            "incoming update from user_id=%s username=%s — %s",
            user.id if user else None,
            user.username if user else None,
            _preview,
        )
        if user is not None and user.id in self.allowed:
            return await handler(event, data)
        logger.warning(
            "blocked message from user_id=%s username=%s",
            user.id if user else None,
            user.username if user else None,
        )
        return None  # silent drop


class ClientInjectionMiddleware(BaseMiddleware):
    """Give handlers access to a ready-to-use ConsiliumClient via `data["client"]`.

    The client is constructed once at dispatcher build time and re-used
    across every request — one persistent httpx.AsyncClient connection
    pool, lifetime tied to the bot process.
    """

    def __init__(self, client: ConsiliumClient) -> None:
        self._client = client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["client"] = self._client
        return await handler(event, data)
