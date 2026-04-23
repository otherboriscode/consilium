"""
`consilium archive` — search / list / show / get / stats / roi.

    consilium archive search "query"
    consilium archive list --project tanaa --limit 30
    consilium archive show 42                 # full md to stdout
    consilium archive get 42                  # save to ./consilium/0042.md
    consilium archive get 42 /tmp/x.md        # save to given path
    consilium archive stats --by model|template|project
    consilium archive roi
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
from consilium_cli.progress import slugify


def register(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="<action>")

    s = sub.add_parser("search", help="FTS-поиск по архиву")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=_run_search)

    lst = sub.add_parser("list", help="Список завершённых из архива")
    lst.add_argument("--project")
    lst.add_argument("--limit", type=int, default=30)
    lst.set_defaults(func=_run_list)

    show = sub.add_parser("show", help="Вывести стенограмму в stdout")
    show.add_argument("job_id", type=int)
    show.set_defaults(func=_run_show)

    get = sub.add_parser("get", help="Скачать стенограмму в файл")
    get.add_argument("job_id", type=int)
    get.add_argument("path", nargs="?", help="Куда сохранить (.md)")
    get.set_defaults(func=_run_get)

    stats = sub.add_parser("stats", help="Агрегаты по архиву")
    stats.add_argument(
        "--by",
        choices=("model", "template", "project"),
        default="model",
    )
    stats.set_defaults(func=_run_stats)

    roi = sub.add_parser("roi", help="ROI: стоимость vs глубина выводов")
    roi.set_defaults(func=_run_roi)


def _run_search(args: argparse.Namespace) -> int:
    return asyncio.run(_search_async(args))


def _run_list(args: argparse.Namespace) -> int:
    return asyncio.run(_list_async(args))


def _run_show(args: argparse.Namespace) -> int:
    return asyncio.run(_show_async(args))


def _run_get(args: argparse.Namespace) -> int:
    return asyncio.run(_get_async(args))


def _run_stats(args: argparse.Namespace) -> int:
    return asyncio.run(_stats_async(args))


def _run_roi(args: argparse.Namespace) -> int:
    return asyncio.run(_roi_async(args))


def _client_from_config() -> ConsiliumClient:
    cfg = load_config()
    return ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    )


async def _search_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            items = await client.search_archive(args.query, limit=args.limit)
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    if not items:
        print("(ничего не найдено)")
        return 0
    for it in items:
        print(
            f"#{it['job_id']:4d}  {it['template']:15s}  "
            f"${it.get('cost_usd', 0):.2f}  {it.get('topic', '')[:100]}"
        )
    return 0


async def _list_async(args: argparse.Namespace) -> int:
    # Reuse /jobs with project filter — it merges active + archive.
    async with _client_from_config() as client:
        try:
            items = await client.list_jobs(
                project=args.project, limit=args.limit
            )
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    for it in items:
        print(
            f"#{it['job_id']:4d}  {it['status']:10s}  "
            f"{it['template']:15s}  ${it.get('cost_usd', 0):.2f}  "
            f"{(it.get('topic') or '')[:80]}"
        )
    return 0


async def _show_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            md = await client.get_archive_md(args.job_id)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    sys.stdout.write(md)
    if not md.endswith("\n"):
        sys.stdout.write("\n")
    return 0


async def _get_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            md = await client.get_archive_md(args.job_id)
        except JobNotFound as e:
            print(f"⚠️  {e}", file=sys.stderr)
            return 2
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    if args.path:
        out = Path(args.path)
    else:
        out = Path("./consilium") / f"{args.job_id:04d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"✓ {out}")
    return 0


async def _stats_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            rows = await client.archive_stats(group_by=args.by)
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    if not rows:
        print("(архив пуст)")
        return 0
    print(f"--- by {args.by} ---")
    for r in rows:
        key = r.get(args.by) or r.get("key") or "?"
        n = r.get("n") or r.get("count") or 0
        cost = r.get("total_cost_usd") or r.get("cost") or 0
        print(f"{str(key):30s}  n={n:3d}  $total={cost:.2f}")
    return 0


async def _roi_async(args: argparse.Namespace) -> int:
    async with _client_from_config() as client:
        try:
            rows = await client.archive_roi()
        except NetworkError as e:
            print(f"🛜  {e}", file=sys.stderr)
            return 2
    if not rows:
        print("(недостаточно данных для ROI)")
        return 0
    for r in rows:
        # ROI row schema is defined by Archive.get_roi_stats — just dump keys.
        line = "  ".join(f"{k}={v}" for k, v in r.items())
        print(line)
    return 0


# exported for test_debate import-cycle sanity; not used from register().
_slug = slugify
