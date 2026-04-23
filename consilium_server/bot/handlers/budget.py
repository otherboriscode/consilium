"""/stats, /cost, /daily — budget visibility commands."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from consilium_server.bot.client import ConsiliumClient, ConsiliumClientError

router = Router()


def _fmt_by_model(by_model: dict[str, float]) -> str:
    if not by_model:
        return "  (нет данных)"
    total = sum(by_model.values()) or 1.0
    rows = sorted(by_model.items(), key=lambda kv: -kv[1])
    return "\n".join(
        f"  <code>{model:<28}</code> ${cost:>6.2f}  ({int(100 * cost / total)}%)"
        for model, cost in rows
    )


@router.message(Command("stats"))
async def cmd_stats(m: Message, client: ConsiliumClient) -> None:
    try:
        usage = await client.get_usage()
        limits = await client.get_limits()
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить статистику: {e}")
        return
    month = usage.get("month_usd", 0.0)
    cap = limits.get("max_cost_per_month_usd", 0) or 1
    pct = int(100 * month / cap) if cap else 0
    lines = [
        "📈 <b>За месяц</b>",
        f"  ${month:.2f} / ${cap:.0f} ({pct}%)",
        f"  Прогонов: {usage.get('jobs_this_month', 0)}",
        "",
        "<b>По моделям</b>:",
        _fmt_by_model(usage.get("by_model", {})),
    ]
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("cost"))
async def cmd_cost(m: Message, client: ConsiliumClient) -> None:
    try:
        usage = await client.get_usage()
        limits = await client.get_limits()
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить расход: {e}")
        return
    day = usage.get("today_usd", 0.0)
    day_cap = limits.get("max_cost_per_day_usd", 0) or 1
    day_pct = int(100 * day / day_cap) if day_cap else 0
    month = usage.get("month_usd", 0.0)
    month_cap = limits.get("max_cost_per_month_usd", 0) or 1
    month_pct = int(100 * month / month_cap) if month_cap else 0
    await m.answer(
        "💰 <b>Расход</b>\n\n"
        f"Сегодня: ${day:.2f} / ${day_cap:.0f} ({day_pct}%)\n"
        f"Месяц:   ${month:.2f} / ${month_cap:.0f} ({month_pct}%)",
        parse_mode="HTML",
    )


@router.message(Command("daily"))
async def cmd_daily(m: Message, client: ConsiliumClient) -> None:
    try:
        summary = await client.get_daily_summary()
    except ConsiliumClientError as e:
        await m.answer(f"⚠️ Не смог получить сводку: {e}")
        return
    await m.answer(summary)
