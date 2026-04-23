"""
`consilium templates` — list/show available YAML templates.

    consilium templates list
    consilium templates show product_concept
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
    sub = parser.add_subparsers(dest="action", required=True, metavar="<action>")
    sub.add_parser("list", help="Имена всех шаблонов").set_defaults(func=_run_list)
    s = sub.add_parser("show", help="Детали шаблона — роли, модели, судья")
    s.add_argument("name")
    s.set_defaults(func=_run_show)


def _client_from_config() -> ConsiliumClient:
    cfg = load_config()
    return ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    )


def _run_list(args):
    return asyncio.run(_list_async())


def _run_show(args):
    return asyncio.run(_show_async(args))


async def _list_async() -> int:
    async with _client_from_config() as client:
        try:
            names = await client.list_templates()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    for n in names:
        print(n)
    return 0


async def _show_async(args) -> int:
    async with _client_from_config() as client:
        try:
            t = await client.show_template(args.name)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(f"Template: {t.get('name', args.name)}")
    print(f"Title:    {t.get('title', '')}")
    if t.get("description"):
        print(f"Desc:     {t['description']}")
    print(f"Rounds:   {t.get('rounds', '?')}")
    print(f"Version:  {t.get('version', '?')}")
    print("Participants:")
    for p in t.get("participants", []):
        mode = "deep" if p.get("deep") else "fast"
        print(f"  • {p['role']:20s} {p['model']}  ({mode})")
    judge = t.get("judge") or {}
    if judge:
        print(f"Judge:    {judge.get('model', '?')}")
    return 0
