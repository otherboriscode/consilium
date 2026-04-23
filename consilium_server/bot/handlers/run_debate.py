"""
Confirm → submit → stream progress → deliver TL;DR + full markdown.

Splits out from /new dialog (handlers/new_debate.py) to keep each module
focused. Two callback routes here:
  - confirm:run    — the happy path
  - confirm:force  — bypass soft-caps (after a CostDenied preview)
"""
from __future__ import annotations

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InaccessibleMessage, Message

from consilium_server.bot.client import (
    ConsiliumClient,
    ConsiliumClientError,
    CostDenied,
    JobNotFound,
    RateLimited,
)
from consilium_server.bot.progress import ProgressPoster

logger = logging.getLogger("consilium.bot")

router = Router()

_TLDR_RE = re.compile(r"^#+\s*TL;DR\s*$", re.IGNORECASE | re.MULTILINE)
_H1_RE = re.compile(r"^#\s+.+", re.MULTILINE)


def _extract_tldr(md: str) -> str:
    """Pull the text between '# TL;DR' and the next '# Header'."""
    m = _TLDR_RE.search(md)
    if not m:
        return ""
    start = m.end()
    tail = md[start:]
    next_h1 = _H1_RE.search(tail)
    section = tail[: next_h1.start()] if next_h1 else tail
    return section.strip()[:2000]


def _as_message(cb: CallbackQuery) -> Message | None:
    msg = cb.message
    if msg is None or isinstance(msg, InaccessibleMessage):
        return None
    return msg


@router.callback_query(F.data == "confirm:run")
@router.callback_query(F.data == "confirm:force")
async def confirm_and_run(
    cb: CallbackQuery,
    state: FSMContext,
    client: ConsiliumClient,
    bot: Bot,
) -> None:
    msg = _as_message(cb)
    if msg is None:
        await cb.answer()
        return
    data = await state.get_data()
    topic = data.get("topic")
    template = data.get("template")
    pack = data.get("pack")
    if not topic or not template:
        await msg.answer("⚠️ Потерял контекст диалога — начни с /new.")
        await state.clear()
        await cb.answer()
        return

    force = cb.data == "confirm:force"
    try:
        submit = await client.submit_job(
            topic=topic, template=template, pack=pack, force=force
        )
    except CostDenied as e:
        await msg.answer(
            "⛔ Всё ещё превышен hard-stop — ничего не запустил:\n"
            + "\n".join(f"• {m}" for m in e.messages)
        )
        await state.clear()
        await cb.answer()
        return
    except RateLimited as e:
        await msg.answer(
            f"⏸ Слишком много активных дискуссий: {e}\n"
            f"Отмени одну через /jobs или подожди."
        )
        await state.clear()
        await cb.answer()
        return
    except ConsiliumClientError as e:
        await msg.answer(f"⚠️ Не смог запустить: {e}")
        await state.clear()
        await cb.answer()
        return

    await state.clear()
    await cb.answer()

    status_msg = await msg.answer(
        f"🚀 Дискуссия #{submit.job_id} запущена\n"
        f"⏱ ~{int(submit.estimated_duration_seconds // 60)} мин  "
        f"💰 ~${submit.estimated_cost_usd:.2f}\n\n"
        f"⏳ Жду первых событий…"
    )
    asyncio.create_task(
        _watch_job(
            bot=bot,
            client=client,
            job_id=submit.job_id,
            chat_id=msg.chat.id,
            status_message_id=status_msg.message_id,
            pack_name=pack,
        )
    )


async def _watch_job(
    *,
    bot: Bot,
    client: ConsiliumClient,
    job_id: int,
    chat_id: int,
    status_message_id: int,
    pack_name: str | None = None,
) -> None:
    """Consume SSE, push progress, deliver final TL;DR + .md on completion.

    If `pack_name` is an `adhoc-…` ephemeral pack created during /new,
    it's deleted in a finally so the user's pack list doesn't accrete
    junk over time (R3 from Phase 8 review).
    """
    poster = ProgressPoster(
        bot=bot, chat_id=chat_id, message_id=status_message_id
    )
    delivered = False
    try:
        try:
            async for event in client.stream_events(job_id):
                kind = event.get("kind", "")
                if kind == "round_started":
                    await poster.push(
                        f"🎯 Дискуссия #{job_id}\n⏳ Раунд {event.get('round_index', 0)} пошёл…"
                    )
                elif kind == "participant_completed":
                    role = event.get("role_slug") or "?"
                    await poster.push(
                        f"🎯 Дискуссия #{job_id}\n✓ {role} ответил "
                        f"(раунд {event.get('round_index', 0)})"
                    )
                elif kind == "participant_failed":
                    role = event.get("role_slug") or "?"
                    err = event.get("error") or event.get("message") or "неизвестно"
                    await poster.push(
                        f"🎯 Дискуссия #{job_id}\n⚠️ {role}: {err}"
                    )
                elif kind == "round_completed":
                    await poster.push(
                        f"🎯 Дискуссия #{job_id}\n"
                        f"✅ Раунд {event.get('round_index', 0)} завершён"
                    )
                elif kind == "judge_started":
                    await poster.push(
                        f"🎯 Дискуссия #{job_id}\n⚖️ Судья синтезирует…"
                    )
                elif kind in ("judge_completed", "done"):
                    await poster.flush_now()
                    await _deliver_final(bot, client, job_id, chat_id)
                    delivered = True
                    return
                elif kind == "judge_failed":
                    await poster.push(
                        f"🎯 Дискуссия #{job_id}\n❌ Судья сорвался: "
                        f"{event.get('error') or 'неизвестно'}"
                    )
                elif kind == "error":
                    await poster.push(
                        f"❌ Дискуссия #{job_id} упала: {event.get('message', '')}"
                    )
                    return
        except JobNotFound:
            # Race: job finished before we subscribed. Fall through to archive.
            pass
        except Exception as e:
            logger.exception("SSE watch failed for job %d", job_id)
            await bot.send_message(
                chat_id, f"❌ Потеря связи с API для #{job_id}: {e}"
            )
            return

        # Stream ended without a terminal event we handled — fall back to archive.
        if not delivered:
            try:
                await _deliver_final(bot, client, job_id, chat_id)
            except Exception:
                logger.exception("fallback delivery failed for job %d", job_id)
    finally:
        # Cleanup ephemeral adhoc-pack regardless of outcome (R3).
        if pack_name and pack_name.startswith("adhoc-"):
            try:
                await client.delete_pack(pack_name)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "failed to cleanup adhoc pack %s: %s", pack_name, e
                )


async def _deliver_final(
    bot: Bot,
    client: ConsiliumClient,
    job_id: int,
    chat_id: int,
) -> None:
    try:
        md = await client.get_archive_md(job_id)
    except JobNotFound:
        await bot.send_message(
            chat_id,
            f"⚠️ #{job_id} завершилась, но в архиве markdown не найден.",
        )
        return

    tldr = _extract_tldr(md) or "(TL;DR не найден в стенограмме)"
    await bot.send_message(
        chat_id,
        f"✅ Дискуссия #{job_id} завершена\n\n<b>TL;DR</b>\n{tldr}",
        parse_mode="HTML",
    )
    file = BufferedInputFile(
        md.encode("utf-8"), filename=f"debate-{job_id:04d}.md"
    )
    await bot.send_document(
        chat_id, file, caption="📄 Полная стенограмма + синтез"
    )
