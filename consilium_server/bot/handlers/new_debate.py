"""
/new — guided dialog: template → topic → context → preview → confirm.

Uses aiogram FSM. The confirm step calls `POST /preview` (cheap, no state
leaked in the server) to show cost/duration estimates. Actual submit +
SSE streaming lands in Task 7.4 (new_debate_run.py) to keep this handler
focused on the dialog shape.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage, Message

from consilium_server.bot.client import (
    ConsiliumClient,
    JobNotFound,
)
from consilium_server.bot.keyboards import (
    TEMPLATES,
    confirm_keyboard,
    context_choice_keyboard,
    files_done_keyboard,
    force_or_cancel_keyboard,
    template_keyboard,
)
from consilium_server.bot.states import NewDebate

logger = logging.getLogger("consilium.bot")

router = Router()


def _as_message(cb: CallbackQuery) -> Message | None:
    """Narrow `cb.message` to the subset we can reply to."""
    msg = cb.message
    if msg is None or isinstance(msg, InaccessibleMessage):
        return None
    return msg


@router.message(Command("new"))
async def cmd_new(m: Message, state: FSMContext) -> None:
    await state.clear()
    await m.answer(
        "Выбери шаблон дискуссии:",
        reply_markup=template_keyboard(TEMPLATES),
    )
    await state.set_state(NewDebate.waiting_template)


@router.callback_query(NewDebate.waiting_template, F.data.startswith("tpl:"))
async def pick_template(cb: CallbackQuery, state: FSMContext) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    tpl = cb.data.removeprefix("tpl:") if cb.data else ""
    await state.update_data(template=tpl)
    await msg.answer(
        f"Шаблон: <b>{tpl}</b>\n\nНапиши тему дискуссии одним сообщением:",
        parse_mode="HTML",
    )
    await state.set_state(NewDebate.waiting_topic)
    await cb.answer()


@router.message(NewDebate.waiting_topic, F.text)
async def got_topic(
    m: Message, state: FSMContext, client: ConsiliumClient
) -> None:
    topic = (m.text or "").strip()
    if not topic:
        await m.answer("Тема пустая — напиши текстом.")
        return
    await state.update_data(topic=topic)
    try:
        packs = await client.list_packs()
    except Exception as e:
        logger.exception("list_packs failed")
        packs = []
        await m.answer(f"⚠️ Не удалось получить список паков: {e}")
    await m.answer(
        "Контекст для дискуссии?",
        reply_markup=context_choice_keyboard(packs),
    )
    await state.set_state(NewDebate.waiting_context_choice)


@router.callback_query(NewDebate.waiting_context_choice, F.data == "ctx:none")
async def ctx_none(
    cb: CallbackQuery, state: FSMContext, client: ConsiliumClient
) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    await state.update_data(pack=None, files=[])
    await _show_preview(msg, state, client)
    await cb.answer()


@router.callback_query(
    NewDebate.waiting_context_choice, F.data.startswith("ctx:pack:")
)
async def ctx_pack(
    cb: CallbackQuery, state: FSMContext, client: ConsiliumClient
) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    name = cb.data.removeprefix("ctx:pack:") if cb.data else ""
    await state.update_data(pack=name, files=[])
    await _show_preview(msg, state, client)
    await cb.answer()


@router.callback_query(NewDebate.waiting_context_choice, F.data == "ctx:upload")
async def ctx_upload(cb: CallbackQuery, state: FSMContext) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    await state.update_data(pack=None, files=[])
    await msg.answer(
        "Пришли мне файлы (MD / TXT / DOCX / PDF) по одному или пачкой.\n"
        "Когда всё загрузишь — нажми «✅ Готово».",
        reply_markup=files_done_keyboard(),
    )
    await state.set_state(NewDebate.waiting_files)
    await cb.answer()


@router.callback_query(NewDebate.waiting_files, F.data == "files:cancel")
@router.callback_query(NewDebate.waiting_context_choice, F.data == "files:cancel")
@router.callback_query(F.data == "confirm:cancel")
async def cancel_flow(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    msg = _as_message(cb)
    if msg is not None:
        await msg.answer("Отменено.")
    await cb.answer()


@router.callback_query(NewDebate.waiting_files, F.data == "files:done")
async def files_done(
    cb: CallbackQuery, state: FSMContext, client: ConsiliumClient
) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    data = await state.get_data()
    files: list[tuple[str, bytes]] = data.get("files", [])
    if not files:
        await cb.answer("Пока не загружено ни одного файла", show_alert=True)
        return
    pack_name = f"adhoc-{cb.from_user.id}-{msg.message_id}"
    try:
        await client.create_pack(pack_name, files=files)
    except Exception as e:
        logger.exception("ad-hoc create_pack failed")
        await msg.answer(f"⚠️ Не удалось создать временный пак: {e}")
        await cb.answer()
        return
    await state.update_data(pack=pack_name)
    await _show_preview(msg, state, client)
    await cb.answer()


@router.message(NewDebate.waiting_files, F.document)
async def collect_file(m: Message, state: FSMContext) -> None:
    data = await state.get_data()
    files: list[tuple[str, bytes]] = list(data.get("files", []))
    if m.document is None or m.bot is None:
        return
    buf = await m.bot.download(m.document)
    if buf is None:
        await m.answer("⚠️ Не смог скачать файл — попробуй ещё раз.")
        return
    content = buf.read()
    filename = m.document.file_name or f"file-{len(files) + 1}"
    files.append((filename, content))
    await state.update_data(files=files)
    await m.answer(f"📎 <i>{filename}</i> ({len(content):,} байт) добавлен. Файлов: {len(files)}.")


async def _show_preview(
    chat_target: Message,
    state: FSMContext,
    client: ConsiliumClient,
) -> None:
    data = await state.get_data()
    topic = data["topic"]
    template = data["template"]
    pack = data.get("pack")
    try:
        preview = await client.preview_job(
            topic=topic, template=template, pack=pack
        )
    except JobNotFound as e:
        await chat_target.answer(f"⛔ {e}")
        await state.clear()
        return
    except Exception as e:
        logger.exception("preview failed")
        await chat_target.answer(f"⚠️ Ошибка preview: {e}")
        await state.clear()
        return

    # Cost-cap violations come back in the body now (not as 402).
    if not preview.allowed:
        lines = [
            "⛔ <b>Cost guard отказал</b>:",
            *[f"• {msg}" for msg in preview.violation_messages],
            f"💰 Оценка: ${preview.estimated_cost_usd:.2f}",
        ]
        await chat_target.answer(
            "\n".join(lines),
            reply_markup=force_or_cancel_keyboard(),
            parse_mode="HTML",
        )
        await state.set_state(NewDebate.waiting_confirm)
        return

    lines = [
        f"🎯 Тема: <i>{_short(topic, 200)}</i>",
        f"📋 Шаблон: <b>{template}</b>",
        (
            f"📎 Контекст: pack <b>{pack}</b>"
            if pack
            else "📎 Контекст: нет"
        ),
        "",
        f"⏱ Оценка времени: ~{int(preview.estimated_duration_seconds // 60)} мин",
        f"💰 Оценка стоимости: ${preview.estimated_cost_usd:.2f}",
    ]
    if preview.context_tokens:
        lines.append(f"📚 Контекст: ~{preview.context_tokens:,} токенов")
    # Surface per-participant fit decisions if any participant isn't "full".
    degraded = [p for p in preview.participants if p.fit != "full"]
    if degraded:
        lines.append("")
        for p in degraded:
            icon = "📄" if p.fit == "summary" else "🚫"
            lines.append(f"{icon} <b>{p.role}</b>: {p.fit}")
    if preview.warnings:
        lines.append("")
        lines.extend(f"⚠️ {w}" for w in preview.warnings)
    await chat_target.answer(
        "\n".join(lines),
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(NewDebate.waiting_confirm)


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
