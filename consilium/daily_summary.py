"""
Pure builder for a morning digest string. Emitted as markdown for Telegram/CLI.
Scheduling (cron / bot loop) is out of scope — Phase 7/9 wires this.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from consilium.archive import Archive
from consilium.limits import Limits


def build_daily_summary(
    *,
    archive: Archive,
    limits: Limits,
    now: datetime | None = None,
) -> str:
    """Return a human-readable digest of yesterday's activity and the
    month-to-date state against limits. Empty string (conceptually "no
    activity") when there were zero jobs yesterday AND this month."""
    now = now or datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    month_start = today_start.replace(day=1)

    yesterday_jobs = archive.list_jobs(
        since=yesterday_start, until=today_start, limit=1000
    )

    month_stats = archive.get_stats(group_by="model", since=month_start)
    month_cost = sum((row.total_cost_usd for row in month_stats), 0.0)

    if not yesterday_jobs and month_cost == 0:
        return "📊 Вчера: нет активности."

    yesterday_cost = sum(j.total_cost_usd for j in yesterday_jobs)
    month_ratio_pct = (
        int(100 * month_cost / limits.max_cost_per_month_usd)
        if limits.max_cost_per_month_usd > 0
        else 0
    )

    lines = [
        f"📊 Вчера: {len(yesterday_jobs)} "
        f"{_plural_job(len(yesterday_jobs))}, ${yesterday_cost:.2f}",
        f"📈 Месяц: ${month_cost:.2f} / "
        f"${limits.max_cost_per_month_usd:.0f} лимит ({month_ratio_pct}%)",
    ]

    if month_stats:
        top = max(month_stats, key=lambda r: r.total_cost_usd)
        top_pct = (
            int(100 * top.total_cost_usd / month_cost) if month_cost else 0
        )
        lines.append(
            f"🥇 Дороже всего: {top.key} — ${top.total_cost_usd:.2f} "
            f"({top_pct}%)"
        )

    # Flag any truncated-judge runs from yesterday so Boris sees them without
    # grepping the archive.
    truncated = [j for j in yesterday_jobs if j.judge_truncated]
    if truncated:
        lines.append(
            f"⚠️  Обрезанных синтезов вчера: {len(truncated)} "
            f"(см. {', '.join(f'#{j.job_id:04d}' for j in truncated[:5])})"
        )

    return "\n".join(lines)


def _plural_job(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "дискуссия"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "дискуссии"
    return "дискуссий"
