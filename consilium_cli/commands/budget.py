"""
`consilium budget` — costs and limits snapshot.

    consilium budget usage
    consilium budget limits
    consilium budget daily        # markdown summary to stdout
    consilium budget alerts
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from consilium_client import ConsiliumClient, NetworkError, load_config


def register(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="<action>")
    sub.add_parser("usage", help="Сколько потрачено сегодня и в этом месяце").set_defaults(
        func=_run_usage
    )
    sub.add_parser("limits", help="Текущие лимиты").set_defaults(func=_run_limits)
    sub.add_parser("daily", help="Markdown-сводка за сегодня").set_defaults(
        func=_run_daily
    )
    sub.add_parser(
        "alerts", help="Какие пороги (50/80/95%) сработали"
    ).set_defaults(func=_run_alerts)


def _client_from_config() -> ConsiliumClient:
    cfg = load_config()
    return ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    )


def _run_usage(args):
    return asyncio.run(_usage_async())


def _run_limits(args):
    return asyncio.run(_limits_async())


def _run_daily(args):
    return asyncio.run(_daily_async())


def _run_alerts(args):
    return asyncio.run(_alerts_async())


async def _usage_async() -> int:
    async with _client_from_config() as client:
        try:
            u = await client.get_usage()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(f"Today:        ${u.get('today_usd', 0):.2f}  ({u.get('jobs_today', 0)} jobs)")
    print(
        f"This month:   ${u.get('month_usd', 0):.2f}  "
        f"({u.get('jobs_this_month', 0)} jobs)"
    )
    by_model = u.get("by_model") or {}
    if by_model:
        print("By model:")
        for m, cost in sorted(by_model.items(), key=lambda x: -x[1]):
            print(f"  {m:30s}  ${cost:.2f}")
    return 0


async def _limits_async() -> int:
    async with _client_from_config() as client:
        try:
            lim = await client.get_limits()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    for k, v in lim.items():
        print(f"{k:40s}  {v}")
    return 0


async def _daily_async() -> int:
    async with _client_from_config() as client:
        try:
            md = await client.get_daily_summary()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    sys.stdout.write(md)
    if not md.endswith("\n"):
        sys.stdout.write("\n")
    return 0


async def _alerts_async() -> int:
    async with _client_from_config() as client:
        try:
            data = await client.get_alerts()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    fired = data.get("fired", [])
    if not fired:
        print("Нет активных алертов.")
        return 0
    for a in fired:
        print(
            f"⚠️  {a.get('threshold', '?')}%: ${a.get('month_cost_usd', 0):.2f} "
            f"из ${a.get('monthly_cap_usd', 0):.2f}"
        )
        if a.get("message"):
            print(f"   {a['message']}")
    return 0
