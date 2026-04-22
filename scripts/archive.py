#!/usr/bin/env python
"""
CLI для работы с архивом дискуссий.

Subcommands:
  list      — последние прогоны (+ фильтры --project/--template --limit)
  search    — FTS5-поиск по теме/TL;DR/рекомендации/стенограмме
  stats     — агрегаты (--by-model / --by-template / --by-project)
  roi       — $ / балл вклада per-model
  show      — распечатать md-файл дискуссии

Все вывода — plain text, без rich/tabulate, чтобы CLI был portable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from consilium.archive import Archive  # noqa: E402


def _cmd_list(args: argparse.Namespace) -> int:
    archive = Archive()
    rows = archive.list_jobs(
        limit=args.limit, project=args.project, template=args.template
    )
    if not rows:
        print("(archive is empty or filters matched nothing)")
        return 0
    print(f"{'ID':>5}  {'STARTED':<26} {'TMPL':<22} {'PROJ':<15} {'DUR':>7}  {'COST':>8}  TOPIC")
    for r in rows:
        proj = r.project or "-"
        trunc_flag = "!" if r.judge_truncated else " "
        print(
            f"{r.job_id:>5}  "
            f"{r.started_at[:19]:<26} "
            f"{r.template_name[:22]:<22} "
            f"{proj[:15]:<15} "
            f"{r.duration_seconds:>6.1f}s  "
            f"${r.total_cost_usd:>6.4f}{trunc_flag} "
            f"{r.topic[:50]}"
        )
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    archive = Archive()
    rows = archive.search(args.query, limit=args.limit)
    if not rows:
        print("(no matches)")
        return 1
    for r in rows:
        proj = f" [{r.project}]" if r.project else ""
        print(
            f"#{r.job_id:04d}  {r.started_at[:10]}  {r.template_name}{proj}\n"
            f"        {r.topic}"
        )
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    archive = Archive()
    group_by: str
    if args.by_model:
        group_by = "model"
    elif args.by_template:
        group_by = "template"
    elif args.by_project:
        group_by = "project"
    else:
        print("error: choose --by-model, --by-template or --by-project", file=sys.stderr)
        return 2
    rows = archive.get_stats(group_by=group_by)  # type: ignore[arg-type]
    if not rows:
        print("(archive empty)")
        return 0
    print(f"{'KEY':<40} {'JOBS':>6} {'TOTAL COST':>12}")
    for r in rows:
        print(f"{(r.key or '-'):<40} {r.n_jobs:>6}   ${r.total_cost_usd:>8.4f}")
    return 0


def _cmd_roi(args: argparse.Namespace) -> int:
    archive = Archive()
    rows = archive.get_roi_stats()
    if not rows:
        print("(no scored participants yet)")
        return 0
    print(
        f"{'MODEL':<32} {'JOBS':>5} {'SCORE':>6} {'TOTAL COST':>12} {'$/SCORE':>10}"
    )
    for r in rows:
        cps = f"${r.cost_per_score:.4f}" if r.cost_per_score is not None else "   n/a"
        print(
            f"{r.model:<32} {r.n_jobs:>5} {r.total_score:>6}   "
            f"${r.total_cost_usd:>8.4f}  {cps:>10}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    archive = Archive()
    with archive._connect() as conn:
        row = conn.execute(
            "SELECT md_path FROM jobs WHERE job_id = ?", (args.job_id,)
        ).fetchone()
    if row is None:
        print(f"error: job {args.job_id} not found", file=sys.stderr)
        return 1
    md_path = archive.root / row["md_path"]
    if not md_path.is_file():
        print(f"error: {md_path} missing on disk", file=sys.stderr)
        return 1
    print(md_path.read_text(encoding="utf-8"))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consilium archive CLI")
    subs = parser.add_subparsers(dest="cmd", required=True)

    p_list = subs.add_parser("list", help="Показать последние прогоны")
    p_list.add_argument("--project", default=None)
    p_list.add_argument("--template", default=None)
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=_cmd_list)

    p_search = subs.add_parser("search", help="FTS-поиск по архиву")
    p_search.add_argument("query", help="Запрос. Используй * для префикса (`концепц*`).")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=_cmd_search)

    p_stats = subs.add_parser("stats", help="Агрегированная статистика")
    grp = p_stats.add_mutually_exclusive_group(required=True)
    grp.add_argument("--by-model", action="store_true")
    grp.add_argument("--by-template", action="store_true")
    grp.add_argument("--by-project", action="store_true")
    p_stats.set_defaults(func=_cmd_stats)

    p_roi = subs.add_parser("roi", help="ROI: $ / балл вклада per-model")
    p_roi.set_defaults(func=_cmd_roi)

    p_show = subs.add_parser("show", help="Распечатать md-файл дискуссии")
    p_show.add_argument("job_id", type=int)
    p_show.set_defaults(func=_cmd_show)

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
