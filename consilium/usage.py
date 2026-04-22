"""
Aggregation of current spend from the archive: today, this month, per-model.
Consumed by the pre-flight permission check and by the budget CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from consilium.archive import Archive


@dataclass(frozen=True)
class CurrentUsage:
    today_usd: float
    month_usd: float
    jobs_today: int
    jobs_this_month: int
    by_model: dict[str, float]  # per-model spend for the current month


def compute_usage(
    archive: Archive, *, now: datetime | None = None
) -> CurrentUsage:
    """Aggregate current usage from the archive.

    - `today` — since 00:00 UTC of the current day
    - `this_month` — since 1st of the current month UTC
    """
    if now is None:
        now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    month_jobs = archive.list_jobs(since=month_start, limit=10_000)
    today_usd = 0.0
    jobs_today = 0
    month_usd = 0.0

    for summary in month_jobs:
        month_usd += summary.total_cost_usd
        # summary.started_at is an ISO string — compare lexicographically.
        if summary.started_at >= day_start.isoformat():
            today_usd += summary.total_cost_usd
            jobs_today += 1

    stats = archive.get_stats(group_by="model", since=month_start)
    by_model = {
        row.key: row.total_cost_usd
        for row in stats
        if row.key is not None
    }

    return CurrentUsage(
        today_usd=today_usd,
        month_usd=month_usd,
        jobs_today=jobs_today,
        jobs_this_month=len(month_jobs),
        by_model=by_model,
    )
