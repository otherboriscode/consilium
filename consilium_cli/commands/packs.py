"""
`consilium packs` — context-pack CRUD.

    consilium packs list
    consilium packs show tanaa
    consilium packs create tanaa ~/docs/brief.md ~/docs/market.pdf
    consilium packs delete old-pack
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from consilium_client import (
    ConsiliumClient,
    JobNotFound,
    NetworkError,
    load_config,
)


def register(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    sub.add_parser("list", help="Имена всех паков").set_defaults(func=_run_list)

    s = sub.add_parser("show", help="Детали одного пака")
    s.add_argument("name")
    s.set_defaults(func=_run_show)

    c = sub.add_parser("create", help="Создать (перезаписать) пак из файлов")
    c.add_argument("name")
    c.add_argument("files", nargs="+", metavar="FILE")
    c.set_defaults(func=_run_create)

    d = sub.add_parser("delete", help="Удалить пак")
    d.add_argument("name")
    d.set_defaults(func=_run_delete)


def _run_list(args: argparse.Namespace) -> int:
    return asyncio.run(_list_async(args))


def _run_show(args: argparse.Namespace) -> int:
    return asyncio.run(_show_async(args))


def _run_create(args: argparse.Namespace) -> int:
    return asyncio.run(_create_async(args))


def _run_delete(args: argparse.Namespace) -> int:
    return asyncio.run(_delete_async(args))


def _client_from_config() -> ConsiliumClient:
    cfg = load_config()
    return ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    )


async def _list_async(_args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            names = await client.list_packs()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    if not names:
        print("(ни одного пака)")
        return 0
    for n in names:
        print(n)
    return 0


async def _show_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            info = await client.show_pack(args.name)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(f"Pack: {info['name']}")
    print(f"Total tokens: {info.get('total_tokens', 0):,}")
    if info.get("has_stale_files"):
        print("⚠️  некоторые файлы изменились после добавления в пак")
    print("Files:")
    for f in info.get("files", []):
        print(f"  • {f['name']:40s}  {f['tokens']:>6,} tokens  ({f['type']})")
    return 0


async def _create_async(args: argparse.Namespace) -> int:
    payload: list[tuple[str, bytes]] = []
    for p_str in args.files:
        p = Path(p_str).expanduser()
        if not p.is_file():
            print(f"⚠️  не файл: {p}", file=sys.stderr)
            return 2
        payload.append((p.name, p.read_bytes()))
    async with _client_from_config() as client:
        try:
            info = await client.create_pack(args.name, files=payload)
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(
        f"✓ пак '{info.get('name', args.name)}' создан: "
        f"{len(info.get('files', payload))} файл(ов), "
        f"{info.get('total_tokens', 0):,} токенов"
    )
    return 0


async def _delete_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            await client.delete_pack(args.name)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    print(f"✓ пак '{args.name}' удалён")
    return 0
