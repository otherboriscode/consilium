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

from consilium_server.bot.client import ConsiliumClient
from consilium_server.bot.error_handler import router as error_router
from consilium_server.bot.handlers.archive import router as archive_router
from consilium_server.bot.handlers.basic import router as basic_router
from consilium_server.bot.handlers.budget import router as budget_router
from consilium_server.bot.handlers.jobs import router as jobs_router
from consilium_server.bot.handlers.new_debate import router as new_debate_router
from consilium_server.bot.handlers.packs import router as packs_router
from consilium_server.bot.handlers.run_debate import router as run_debate_router
from consilium_server.bot.handlers.templates import router as templates_router
from consilium_server.bot.middlewares import (
    ClientInjectionMiddleware,
    WhitelistMiddleware,
)


def build_dispatcher(client: ConsiliumClient | None = None) -> Dispatcher:
    """Build a Dispatcher with all routers and middlewares wired in.
    Factored out so tests can exercise routing without starting polling."""
    dp = Dispatcher()
    whitelist = WhitelistMiddleware()
    dp.message.middleware(whitelist)
    dp.callback_query.middleware(whitelist)
    if client is not None:
        inject = ClientInjectionMiddleware(client)
        dp.message.middleware(inject)
        dp.callback_query.middleware(inject)
    dp.include_router(basic_router)
    dp.include_router(new_debate_router)
    dp.include_router(run_debate_router)
    dp.include_router(jobs_router)
    dp.include_router(archive_router)
    dp.include_router(budget_router)
    dp.include_router(packs_router)
    dp.include_router(templates_router)
    # Error router last so it doesn't shadow normal handlers.
    dp.include_router(error_router)
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
    async with ConsiliumClient(
        base_url=os.environ["CONSILIUM_API_BASE"],
        token=os.environ["CONSILIUM_API_TOKEN"],
    ) as client:
        dp = build_dispatcher(client)
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
