#!/usr/bin/env python
"""
CLI для мониторинга расходов и лимитов.

Subcommands:
  usage   — сегодня / месяц / разбивка по моделям
  limits  — текущие значения лимитов (из YAML или дефолтов)
  daily   — утренняя сводка (как её увидит Telegram-бот Фазы 7)
  alerts  — сработавшие пороги (read-only без --mark, чтобы не менять state)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from consilium.alerts import detect_alerts  # noqa: E402
from consilium.archive import Archive  # noqa: E402
from consilium.daily_summary import build_daily_summary  # noqa: E402
from consilium.limits import load_limits  # noqa: E402
from consilium.usage import compute_usage  # noqa: E402


def _alerts_state_file() -> Path:
    import os

    base = Path(
        os.environ.get(
            "CONSILIUM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "consilium"),
        )
    )
    return base / "alerts_state.json"


def _cmd_usage(args: argparse.Namespace) -> int:
    archive = Archive()
    limits = load_limits()
    usage = compute_usage(archive)
    pct_month = (
        int(100 * usage.month_usd / limits.max_cost_per_month_usd)
        if limits.max_cost_per_month_usd > 0
        else 0
    )
    print(f"Сегодня:  ${usage.today_usd:>7.2f}   ({usage.jobs_today} "
          f"{'job' if usage.jobs_today == 1 else 'jobs'})")
    print(
        f"Месяц:    ${usage.month_usd:>7.2f}   "
        f"({usage.jobs_this_month} jobs)   "
        f"лимит ${limits.max_cost_per_month_usd:.0f} ({pct_month}%)"
    )
    if usage.by_model:
        total = sum(usage.by_model.values())
        print()
        print("По моделям (за месяц):")
        for model, cost in sorted(usage.by_model.items(), key=lambda kv: -kv[1]):
            share = int(100 * cost / total) if total > 0 else 0
            print(f"  {model:<36} ${cost:>7.2f}   ({share}%)")
    return 0


def _cmd_limits(args: argparse.Namespace) -> int:
    lim = load_limits()
    print("Лимиты (из ~/.config/consilium/limits.yaml или дефолтов):")
    print(f"  per-job:   ${lim.max_cost_per_job_usd:.2f}")
    print(f"  per-day:   ${lim.max_cost_per_day_usd:.2f}")
    print(
        f"  per-month: ${lim.max_cost_per_month_usd:.2f}  "
        f"(hard-stop: ${lim.hard_stop_per_month_usd:.2f})"
    )
    print(f"  rounds:                 ≤ {lim.max_rounds}")
    print(f"  max_tokens_per_reply:   ≤ {lim.max_tokens_per_response:,}")
    print(f"  max_context_tokens:     ≤ {lim.max_context_tokens:,}")
    thresholds = ", ".join(f"{int(t * 100)}%" for t in lim.alert_thresholds)
    print(f"  alert thresholds:       {thresholds}")
    return 0


def _cmd_daily(args: argparse.Namespace) -> int:
    archive = Archive()
    limits = load_limits()
    print(build_daily_summary(archive=archive, limits=limits))
    return 0


def _cmd_alerts(args: argparse.Namespace) -> int:
    archive = Archive()
    limits = load_limits()
    alerts = detect_alerts(
        archive=archive,
        limits=limits,
        state_file=_alerts_state_file(),
        mark=args.mark,
    )
    if not alerts:
        print("(нет сработавших порогов)")
        return 0
    for a in alerts:
        print(a.message)
    if not args.mark:
        print("\n(read-only; используй --mark чтобы зафиксировать)")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consilium budget CLI")
    subs = parser.add_subparsers(dest="cmd", required=True)

    subs.add_parser("usage", help="Текущее потребление").set_defaults(func=_cmd_usage)
    subs.add_parser("limits", help="Текущие лимиты").set_defaults(func=_cmd_limits)
    subs.add_parser("daily", help="Утренняя сводка").set_defaults(func=_cmd_daily)

    p_alerts = subs.add_parser("alerts", help="Сработавшие пороги")
    p_alerts.add_argument(
        "--mark",
        action="store_true",
        help="Зафиксировать сработавший порог в state (избегать повтора).",
    )
    p_alerts.set_defaults(func=_cmd_alerts)

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
