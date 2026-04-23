"""/start, /help — onboarding handlers."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(m: Message) -> None:
    await m.answer(
        "🎛 <b>Consilium bot</b>\n\n"
        "Команды:\n"
        "/new — новая дискуссия\n"
        "/jobs — активные и недавние\n"
        "/archive <запрос> — поиск по архиву\n"
        "/result &lt;id&gt; — markdown по job_id\n"
        "/stats — расход за месяц\n"
        "/cost — сегодня\n"
        "/daily — дайджест\n"
        "/packs — контекст-паки\n"
        "/templates — доступные шаблоны\n"
        "/help — подробнее",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(m: Message) -> None:
    await m.answer(
        "Подробная справка:\n\n"
        "<b>/new</b> запускает мастер:\n"
        "1. Выбор шаблона\n"
        "2. Тема\n"
        "3. Контекст (pack, файлы или без)\n"
        "4. Preview с оценкой стоимости\n"
        "5. Подтверждение\n\n"
        "Дискуссия идёт 1–5 минут (fast) или до часа (deep).\n"
        "Я напишу, когда завершится — с TL;DR и полным .md-файлом.\n\n"
        "<b>Контекст</b>:\n"
        "/pack_new — создать пак из файлов (пришли файлы в чат)\n"
        "/pack_list — список паков\n\n"
        "<b>Безопасность</b>:\n"
        "Бот отвечает только на мой user_id. Всё через bearer-auth к API.",
        parse_mode="HTML",
    )
