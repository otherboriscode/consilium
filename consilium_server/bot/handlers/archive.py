"""/archive <query> — FTS5 search; /result <id> — fetch archived .md."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from consilium_server.bot.client import (
    ConsiliumClient,
    ConsiliumClientError,
    JobNotFound,
)

router = Router()


@router.message(Command("archive"))
async def cmd_archive(
    m: Message, command: CommandObject, client: ConsiliumClient
) -> None:
    query = (command.args or "").strip()
    if not query:
        await m.answer(
            "Usage: <code>/archive &lt;запрос&gt;</code>\n"
            "Поддерживается префикс через <code>*</code> "
            "(<code>/archive концепц*</code>).",
            parse_mode="HTML",
        )
        return
    try:
        hits = await client.search_archive(query, limit=10)
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Поиск упал: {e}")
        return
    if not hits:
        await m.answer(f"🔍 По запросу <code>{query}</code> ничего.", parse_mode="HTML")
        return

    lines = [f"🔍 <b>Найдено</b>: {len(hits)}", ""]
    for h in hits:
        job_id = h.get("job_id")
        topic = (h.get("topic") or "")[:60]
        proj = h.get("project")
        proj_str = f" [{proj}]" if proj else ""
        lines.append(
            f"<b>#{job_id:04d}</b>{proj_str}\n    {topic}"
        )
    lines.append("")
    lines.append("Открыть: <code>/result &lt;id&gt;</code>")
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("result"))
async def cmd_result(
    m: Message, command: CommandObject, client: ConsiliumClient
) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await m.answer("Usage: <code>/result &lt;job_id&gt;</code>", parse_mode="HTML")
        return
    try:
        job_id = int(arg)
    except ValueError:
        await m.answer(f"⚠️ <code>{arg}</code> — не число", parse_mode="HTML")
        return
    try:
        md = await client.get_archive_md(job_id)
    except JobNotFound:
        await m.answer(f"⚠️ Дискуссия #{job_id} не найдена.")
        return
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить #{job_id}: {e}")
        return
    file = BufferedInputFile(
        md.encode("utf-8"), filename=f"debate-{job_id:04d}.md"
    )
    await m.answer_document(
        file, caption=f"📄 Дискуссия #{job_id:04d}"
    )
