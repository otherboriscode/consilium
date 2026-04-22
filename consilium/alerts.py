"""
Threshold-based alert detector with persistent dedup state.

Intended usage (Phase 7 Telegram bot, Phase 9 cron):
  alerts = detect_alerts(archive=A, limits=L, state_file=PATH)
  for a in alerts:
      send_to_telegram(a.message)

The state file stores the highest fired threshold so far in the current
month so we don't spam the user every time they exceed the same bar. The
state resets implicitly when `total < previously_fired` (e.g. after a new
month).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from consilium.archive import Archive
from consilium.limits import Limits


@dataclass(frozen=True)
class Alert:
    threshold: float  # e.g. 0.5 / 0.8 / 0.95
    month_cost_usd: float
    monthly_cap_usd: float
    message: str


def _read_state(state_file: Path) -> float:
    if not state_file.is_file():
        return 0.0
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return float(data.get("last_fired", 0.0))
    except (json.JSONDecodeError, ValueError, OSError):
        return 0.0


def _write_state(state_file: Path, last_fired: float) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"last_fired": last_fired}), encoding="utf-8"
    )


def detect_alerts(
    *,
    archive: Archive,
    limits: Limits,
    state_file: Path,
    now: datetime | None = None,
    mark: bool = True,
) -> list[Alert]:
    """Fire an alert for the highest still-un-fired threshold crossed by the
    current month's spend.

    `mark=False` — dry-run: return what would fire without updating the state
    file. Useful for `scripts/budget.py alerts` read-only preview.
    """
    now = now or datetime.now(timezone.utc)
    month_start = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    stats = archive.get_stats(group_by="model", since=month_start)
    month_cost = sum((row.total_cost_usd for row in stats), 0.0)

    if limits.max_cost_per_month_usd <= 0:
        return []
    ratio = month_cost / limits.max_cost_per_month_usd

    last_fired = _read_state(state_file)
    # If we rolled over to a new month (spend dropped below last fired
    # threshold fraction), reset the state automatically.
    if ratio < last_fired:
        last_fired = 0.0

    # Highest threshold below-or-equal current ratio AND above last_fired.
    candidates = [
        t for t in sorted(limits.alert_thresholds)
        if t <= ratio and t > last_fired
    ]
    if not candidates:
        return []
    fired = max(candidates)

    alert = Alert(
        threshold=fired,
        month_cost_usd=month_cost,
        monthly_cap_usd=limits.max_cost_per_month_usd,
        message=(
            f"⚠️ Достигнут порог {int(fired * 100)}% месячного лимита: "
            f"${month_cost:.2f} / ${limits.max_cost_per_month_usd:.0f}."
        ),
    )
    if mark:
        _write_state(state_file, fired)
    return [alert]
