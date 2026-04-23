"""Pack management:
  /packs — list
  /pack_show <name>
  /pack_new — FSM: name → files → /done
  /pack_delete <name> — with inline confirm
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from consilium_server.bot.client import (
    ConsiliumClient,
    ConsiliumClientError,
    JobNotFound,
)
from consilium_server.bot.states import NewPack

logger = logging.getLogger("consilium.bot")

router = Router()


def _as_message(cb: CallbackQuery) -> Message | None:
    msg = cb.message
    if msg is None or isinstance(msg, InaccessibleMessage):
        return None
    return msg


@router.message(Command("packs"))
async def cmd_packs(m: Message, client: ConsiliumClient) -> None:
    try:
        names = await client.list_packs()
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить список: {e}")
        return
    if not names:
        await m.answer(
            "📦 Паков пока нет. Создай: /pack_new"
        )
        return
    lines = ["📦 <b>Паки</b>:", ""]
    for n in names:
        lines.append(f"• <code>{n}</code>")
    lines.append("")
    lines.append("Подробнее: /pack_show &lt;name&gt;")
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("pack_show"))
async def cmd_pack_show(
    m: Message, command: CommandObject, client: ConsiliumClient
) -> None:
    name = (command.args or "").strip()
    if not name:
        await m.answer("Usage: <code>/pack_show &lt;name&gt;</code>", parse_mode="HTML")
        return
    try:
        info = await client.show_pack(name)
    except JobNotFound:
        await m.answer(f"⚠️ Пак <code>{name}</code> не найден.", parse_mode="HTML")
        return
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить пак: {e}")
        return
    lines = [
        f"📦 <b>{info['name']}</b>",
        f"Файлов: {len(info['files'])}",
        f"Токенов: {info['total_tokens']:,}",
        "",
    ]
    for f in info["files"]:
        lines.append(
            f"• <code>{f['name']}</code> — {f['tokens']:,} tokens ({f['type']})"
        )
    if info.get("has_stale_files"):
        lines.append("")
        lines.append("⚠️ Файлы редактировались после создания — пересоздай пак.")
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("pack_delete"))
async def cmd_pack_delete(
    m: Message, command: CommandObject
) -> None:
    name = (command.args or "").strip()
    if not name:
        await m.answer(
            "Usage: <code>/pack_delete &lt;name&gt;</code>", parse_mode="HTML"
        )
        return
    # Inline confirm
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"❌ Удалить {name}",
                    callback_data=f"pack_del:{name}",
                ),
                InlineKeyboardButton(text="Отмена", callback_data="pack_del:cancel"),
            ]
        ]
    )
    await m.answer(
        f"Точно удалить пак <code>{name}</code>?", parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data.startswith("pack_del:"))
async def pack_delete_confirm(
    cb: CallbackQuery, client: ConsiliumClient
) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    arg = (cb.data or "").removeprefix("pack_del:")
    if arg == "cancel":
        await msg.answer("Отменено.")
        await cb.answer()
        return
    try:
        await client.delete_pack(arg)
    except JobNotFound:
        await msg.answer(f"⚠️ Пак <code>{arg}</code> уже удалён.", parse_mode="HTML")
        await cb.answer()
        return
    except ConsiliumClientError as e:
        await msg.answer(f"⚠️ Не смог удалить: {e}")
        await cb.answer()
        return
    await msg.answer(f"🗑 Пак <code>{arg}</code> удалён.", parse_mode="HTML")
    await cb.answer()


# -----  /pack_new FSM  ---------------------------------------------------

_DONE_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="pack_new:done")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="pack_new:cancel")],
    ]
)


@router.message(Command("pack_new"))
async def cmd_pack_new(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer(
        "Как назвать пак? (буквы, цифры, дефисы, подчёркивания)"
    )
    await state.set_state(NewPack.waiting_name)


@router.message(NewPack.waiting_name, F.text)
async def pack_name(m: Message, state: FSMContext) -> None:
    name = (m.text or "").strip()
    if not name or not all(
        c.isalnum() or c in "-_" for c in name
    ):
        await m.answer("⚠️ Имя пустое или содержит странные символы. Ещё раз?")
        return
    await state.update_data(name=name, files=[])
    await m.answer(
        f"✨ Буду называть пак <b>{name}</b>.\n\n"
        "Теперь присылай файлы (MD / TXT / DOCX / PDF). "
        "Когда всё загрузишь — «✅ Готово».",
        parse_mode="HTML",
        reply_markup=_DONE_KB,
    )
    await state.set_state(NewPack.waiting_files)


@router.message(NewPack.waiting_files, F.document)
async def pack_collect(m: Message, state: FSMContext) -> None:
    data = await state.get_data()
    files: list[tuple[str, bytes]] = list(data.get("files", []))
    if m.document is None or m.bot is None:
        return
    buf = await m.bot.download(m.document)
    if buf is None:
        await m.answer("⚠️ Не смог скачать файл — ещё раз?")
        return
    content = buf.read()
    fname = m.document.file_name or f"file-{len(files) + 1}"
    files.append((fname, content))
    await state.update_data(files=files)
    await m.answer(f"📎 <code>{fname}</code> добавлен. Всего: {len(files)}.", parse_mode="HTML")


@router.callback_query(NewPack.waiting_files, F.data == "pack_new:done")
async def pack_finish(
    cb: CallbackQuery, state: FSMContext, client: ConsiliumClient
) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    data = await state.get_data()
    files: list[tuple[str, bytes]] = data.get("files", [])
    name: str = data.get("name", "")
    if not files:
        await cb.answer("Пока нет файлов", show_alert=True)
        return
    try:
        info = await client.create_pack(name, files=files)
    except ConsiliumClientError as e:
        await msg.answer(f"⚠️ Не смог создать: {e}")
        await state.clear()
        await cb.answer()
        return
    await state.clear()
    await msg.answer(
        f"✅ Пак <b>{name}</b> создан: "
        f"{len(info.get('files', []))} файлов, "
        f"{info.get('total_tokens', 0):,} токенов.",
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(NewPack.waiting_files, F.data == "pack_new:cancel")
@router.callback_query(NewPack.waiting_name, F.data == "pack_new:cancel")
async def pack_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    msg = _as_message(cb)
    if msg is not None:
        await msg.answer("Отменено.")
    await cb.answer()
