"""
`consilium jobs` — list active + recent. Subcommands:

    consilium jobs                      # list
    consilium jobs --project tanaa
    consilium jobs status 42
    consilium jobs cancel 42
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from consilium_client import (
    ConsiliumClient,
    JobNotFound,
    NetworkError,
    load_config,
)


def register(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", metavar="<action>")

    list_p = sub.add_parser("list", help="Список активных + недавних (default)")
    list_p.add_argument("--project", help="Фильтр по project")
    list_p.add_argument("--limit", type=int, default=20)
    list_p.set_defaults(func=_run_list)

    status_p = sub.add_parser("status", help="Детали одной дискуссии")
    status_p.add_argument("job_id", type=int)
    status_p.set_defaults(func=_run_status)

    cancel_p = sub.add_parser("cancel", help="Отменить активную дискуссию")
    cancel_p.add_argument("job_id", type=int)
    cancel_p.set_defaults(func=_run_cancel)

    # `consilium jobs` with no action → list
    parser.add_argument("--project", dest="_top_project", help=argparse.SUPPRESS)
    parser.add_argument(
        "--limit", dest="_top_limit", type=int, default=None, help=argparse.SUPPRESS
    )
    parser.set_defaults(func=_dispatch_list_default)


def _dispatch_list_default(args: argparse.Namespace) -> int:
    """Called when no action was given — fall through to list."""
    if args.action is None:
        args.project = getattr(args, "_top_project", None)
        args.limit = getattr(args, "_top_limit", None) or 20
        return _run_list(args)
    return args.func(args)


def _run_list(args: argparse.Namespace) -> int:
    return asyncio.run(_list_async(args))


def _run_status(args: argparse.Namespace) -> int:
    return asyncio.run(_status_async(args))


def _run_cancel(args: argparse.Namespace) -> int:
    return asyncio.run(_cancel_async(args))


async def _list_async(args: argparse.Namespace) -> int:
    cfg = load_config()
    async with ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    ) as client:
        try:
            items = await client.list_jobs(
                project=args.project, limit=args.limit
            )
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    if not items:
        print("(пусто)")
        return 0
    # Text-table layout — no Rich dependency for this simple view.
    headers = ("id", "status", "template", "project", "cost", "topic")
    print("  ".join(f"{h:10s}" for h in headers[:5]) + "  topic")
    for item in items:
        job_id = item.get("job_id", "?")
        status = item.get("status", "?")
        tpl = item.get("template", "?")
        proj = item.get("project") or "-"
        cost = item.get("cost_usd") or 0.0
        topic = (item.get("topic") or "")[:80]
        print(
            f"{str(job_id):10s}  {status:10s}  {tpl:10s}  "
            f"{proj[:10]:10s}  ${cost:<9.2f}{topic}"
        )
    return 0


async def _status_async(args: argparse.Namespace) -> int:
    cfg = load_config()
    async with ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    ) as client:
        try:
            s = await client.get_status(args.job_id)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(f"Job #{s.job_id}")
    print(f"  status:         {s.status}")
    print(f"  rounds:         {s.rounds_completed}/{s.rounds_total}")
    print(f"  template:       {s.template}")
    print(f"  project:        {s.project or '-'}")
    print(f"  topic:          {s.topic}")
    print(
        f"  cost:           ${s.current_cost_usd:.4f} "
        f"(оценка ${s.estimated_cost_usd:.2f})"
    )
    if s.error:
        print(f"  error:          {s.error}")
    return 0


async def _cancel_async(args: argparse.Namespace) -> int:
    cfg = load_config()
    async with ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    ) as client:
        try:
            await client.cancel_job(args.job_id)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(f"✓ Job #{args.job_id} cancelled")
    return 0
