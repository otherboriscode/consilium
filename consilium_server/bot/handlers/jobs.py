"""/jobs — list active + recent; /cancel <id> — cancel an in-flight job."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from consilium_server.bot.client import (
    ConsiliumClient,
    ConsiliumClientError,
    JobNotFound,
)

logger = logging.getLogger("consilium.bot")

router = Router()


def _status_emoji(status: str) -> str:
    return {
        "running": "⏳",
        "queued": "⏳",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "⛔",
    }.get(status, "•")


@router.message(Command("jobs"))
async def cmd_jobs(m: Message, client: ConsiliumClient) -> None:
    try:
        jobs = await client.list_jobs(limit=15)
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить список: {e}")
        return
    if not jobs:
        await m.answer("📭 В архиве и активных — пусто.")
        return

    lines = ["📋 <b>Последние дискуссии</b>:", ""]
    for j in jobs:
        status = j.get("status", "?")
        emoji = _status_emoji(status)
        job_id = j.get("job_id")
        topic = (j.get("topic") or "")[:60]
        cost = j.get("cost_usd", 0.0) or 0.0
        project = j.get("project")
        proj = f" [{project}]" if project else ""
        lines.append(
            f"{emoji} <b>#{job_id:04d}</b>{proj} ${cost:.3f}\n    {topic}"
        )
    lines.append("")
    lines.append("Отменить: <code>/cancel &lt;id&gt;</code>")
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(
    m: Message, command: CommandObject, client: ConsiliumClient
) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await m.answer("Usage: <code>/cancel &lt;job_id&gt;</code>", parse_mode="HTML")
        return
    try:
        job_id = int(arg)
    except ValueError:
        await m.answer(f"⚠️ <code>{arg}</code> — не число", parse_mode="HTML")
        return
    try:
        await client.cancel_job(job_id)
    except JobNotFound:
        await m.answer(
            f"⚠️ Дискуссия #{job_id} не активна "
            f"(возможно, уже завершилась)."
        )
        return
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог отменить #{job_id}: {e}")
        return
    await m.answer(f"⛔ #{job_id} отменена.")
