"""aiogram middlewares for the Consilium bot."""
from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

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
        if user is not None and user.id in self.allowed:
            return await handler(event, data)
        logger.warning(
            "blocked message from user_id=%s username=%s",
            user.id if user else None,
            user.username if user else None,
        )
        return None  # silent drop
