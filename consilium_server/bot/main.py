"""
Consilium Telegram bot entry-point.

Long-polling (no webhook), single-user (whitelist), thin client over the
Consilium HTTPS API (never reaches into core/archive directly).

Env vars:
  TELEGRAM_BOT_TOKEN          — BotFather token (required)
  TELEGRAM_ALLOWED_USER_IDS   — comma-separated user ids (required)
  CONSILIUM_API_BASE          — e.g. http://127.0.0.1:8421 (required)
  CONSILIUM_API_TOKEN         — bearer token (required)
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from consilium_server.bot.handlers.basic import router as basic_router
from consilium_server.bot.middlewares import WhitelistMiddleware


def build_dispatcher() -> Dispatcher:
    """Build a Dispatcher with all routers and middlewares wired in.
    Factored out so tests can exercise routing without starting polling."""
    dp = Dispatcher()
    whitelist = WhitelistMiddleware()
    dp.message.middleware(whitelist)
    dp.callback_query.middleware(whitelist)
    dp.include_router(basic_router)
    return dp


async def run_bot() -> None:
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "CONSILIUM_API_BASE",
        "CONSILIUM_API_TOKEN",
    ):
        if not os.environ.get(key):
            raise SystemExit(f"Missing required env var: {key}")

    bot = Bot(
        token=os.environ["TELEGRAM_BOT_TOKEN"],
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="consilium-bot")
    parser.add_argument(
        "--log-level", default=os.environ.get("CONSILIUM_BOT_LOG_LEVEL", "INFO")
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
