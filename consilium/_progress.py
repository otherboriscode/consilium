"""
Безопасная обёртка над progress-callback.

Если потребитель колбэка упадёт (IOError на stdout, race в UI, любое другое), мы
не дадим этому убить уже оплаченную дискуссию. Ошибка логируется, дискуссия
продолжается.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from consilium.models import ProgressEvent

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressEvent], Awaitable[None]]


async def safe_progress(
    progress: ProgressCallback | None,
    event: ProgressEvent,
) -> None:
    """Call `progress(event)` if provided, swallowing any exception."""
    if progress is None:
        return
    try:
        await progress(event)
    except Exception:
        logger.exception("progress callback failed, continuing debate")
