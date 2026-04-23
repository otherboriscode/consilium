"""/templates — list available YAML templates. /template_show <name> — details."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from consilium_server.bot.client import (
    ConsiliumClient,
    ConsiliumClientError,
    JobNotFound,
)

router = Router()


@router.message(Command("templates"))
async def cmd_templates(m: Message, client: ConsiliumClient) -> None:
    try:
        names = await client.list_templates()
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить список: {e}")
        return
    if not names:
        await m.answer("📋 Шаблонов нет.")
        return
    lines = ["📋 <b>Шаблоны</b>:", ""]
    for n in names:
        lines.append(f"• <code>{n}</code>")
    lines.append("")
    lines.append("Подробнее: <code>/template_show &lt;name&gt;</code>")
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("template_show"))
async def cmd_template_show(
    m: Message, command: CommandObject, client: ConsiliumClient
) -> None:
    name = (command.args or "").strip()
    if not name:
        await m.answer(
            "Usage: <code>/template_show &lt;name&gt;</code>", parse_mode="HTML"
        )
        return
    try:
        info = await client.show_template(name)
    except JobNotFound:
        await m.answer(f"⚠️ Шаблон <code>{name}</code> не найден.", parse_mode="HTML")
        return
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить: {e}")
        return

    lines = [
        f"📋 <b>{info['name']}</b>",
        f"<i>{info['title']}</i>",
        "",
        info["description"],
        "",
        f"Раундов: {info['rounds']}",
        f"Участников: {len(info['participants'])}",
        "",
        "<b>Роли</b>:",
    ]
    for p in info["participants"]:
        deep = " 🧠" if p.get("deep") else ""
        lines.append(
            f"• <code>{p['role']:<18}</code> {p['model']}{deep}"
        )
    lines.append(f"⚖️ Судья: <code>{info['judge']['model']}</code>")
    await m.answer("\n".join(lines), parse_mode="HTML")
