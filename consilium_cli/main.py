"""
`consilium` CLI entry point.

Dispatches to subcommand modules in `consilium_cli.commands`. Also allows
the ergonomic shortcut `consilium "тема"` → `consilium debate "тема"`
without forcing Boris to type the subcommand every time.
"""
from __future__ import annotations

import argparse
import sys

from consilium_cli import __version__
from consilium_cli.commands import (
    archive as archive_cmd,
    budget as budget_cmd,
    debate as debate_cmd,
    devil as devil_cmd,
    jobs as jobs_cmd,
    packs as packs_cmd,
    solo as solo_cmd,
    templates as templates_cmd,
)

_SUBCOMMANDS = (
    "debate", "solo", "devil",
    "jobs", "archive", "packs", "budget", "templates",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="consilium",
        description="Consilium CLI — multi-LLM council for concept work",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"consilium {__version__}",
    )
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="<command>"
    )
    debate_cmd.register(
        sub.add_parser("debate", help="Запустить новую дискуссию")
    )
    solo_cmd.register(
        sub.add_parser("solo", help="Один Opus, без дискуссии (baseline)")
    )
    devil_cmd.register(
        sub.add_parser(
            "devil",
            help="Opus спорит сам с собой — дешёвый эрзац-консилиум",
        )
    )
    jobs_cmd.register(
        sub.add_parser("jobs", help="Активные и недавние дискуссии")
    )
    archive_cmd.register(
        sub.add_parser("archive", help="Архив — поиск и просмотр")
    )
    packs_cmd.register(sub.add_parser("packs", help="Контекст-паки"))
    budget_cmd.register(sub.add_parser("budget", help="Расходы и лимиты"))
    templates_cmd.register(
        sub.add_parser("templates", help="Доступные шаблоны")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    # Ergonomic shortcut: `consilium "тема"` → `consilium debate "тема"`.
    # If the first arg isn't a known subcommand or a top-level flag, assume
    # it's a debate topic.
    if args and not args[0].startswith("-") and args[0] not in _SUBCOMMANDS:
        args = ["debate"] + args

    parser = _build_parser()
    parsed = parser.parse_args(args)
    rc: int = parsed.func(parsed)
    return rc


if __name__ == "__main__":
    sys.exit(main())
