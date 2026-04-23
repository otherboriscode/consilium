"""
Global aiogram error handler — turns unexpected exceptions into polite
Telegram messages instead of silent drops + a Python traceback in logs.

Typed client errors (AuthError, CostDenied, RateLimited, JobNotFound) are
expected to be handled locally in each command with a domain-appropriate
reply; this handler catches anything that escaped.
"""
from __future__ import annotations

import logging

import httpx
from aiogram import Router
from aiogram.types import ErrorEvent, InaccessibleMessage, Message

from consilium_server.bot.client import (
    AuthError,
    ConsiliumClientError,
    CostDenied,
    JobNotFound,
    RateLimited,
)

logger = logging.getLogger("consilium.bot")

router = Router()


def _reply_target(update) -> Message | None:
    """Pull a usable Message out of whatever triggered the error."""
    msg = getattr(update, "message", None)
    if isinstance(msg, Message):
        return msg
    cq = getattr(update, "callback_query", None)
    if cq is not None:
        cq_msg = getattr(cq, "message", None)
        if isinstance(cq_msg, Message) and not isinstance(cq_msg, InaccessibleMessage):
            return cq_msg
    return None


@router.error()
async def on_unhandled_error(event: ErrorEvent) -> bool:
    """Return True = "handled, don't log" (we log explicitly below)."""
    exc = event.exception
    reply_to = _reply_target(event.update)
    logger.exception("bot handler raised: %s", exc)

    if reply_to is None:
        return True  # nowhere to reply; already logged

    # Typed client errors — friendly copy.
    if isinstance(exc, AuthError):
        await reply_to.answer("🔒 Сервер отказал в авторизации. Проверь CONSILIUM_API_TOKEN.")
    elif isinstance(exc, CostDenied):
        await reply_to.answer(
            "⛔ Cost guard отказал:\n"
            + "\n".join(f"• {m}" for m in exc.messages)
        )
    elif isinstance(exc, RateLimited):
        await reply_to.answer(f"⏸ Сервер перегружен: {exc}. Попробуй позже.")
    elif isinstance(exc, JobNotFound):
        await reply_to.answer(f"⚠️ {exc}")
    elif isinstance(exc, ConsiliumClientError):
        await reply_to.answer(f"⚠️ API-ошибка: {exc}")
    elif isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)):
        await reply_to.answer(
            "🛜 Не могу достучаться до Consilium API.\n"
            "Проверь, что сервер запущен (CONSILIUM_API_BASE) и попробуй снова."
        )
    else:
        await reply_to.answer(
            f"❌ Неожиданная ошибка: {type(exc).__name__}: {exc}\n"
            f"(подробности — в логах бота)"
        )
    return True
