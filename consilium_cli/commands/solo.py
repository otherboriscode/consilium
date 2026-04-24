"""
`consilium solo <topic>` — baseline один Opus без дискуссии.

Тонкая обёртка над `debate -t solo`: прокидывает фиксированный
template, передаёт остальные аргументы как есть.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from consilium_cli.commands.debate import run as _debate_run


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", nargs="?", help="Тема для анализа")
    parser.add_argument("--project", help="Группировка для архива")
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Только preview, ничего не запускать",
    )
    parser.add_argument(
        "--output-dir",
        default=Path("./consilium"),
        type=Path,
        help="Куда сохранить итоговый markdown (по умолчанию ./consilium/)",
    )
    # Fixed values not exposed as flags — this command is intentionally
    # minimal.  Injected via set_defaults so `debate._run_async` sees them.
    parser.set_defaults(
        func=_run,
        template="solo",
        pack=None,
        context=None,
        rounds=None,
        force=False,
    )


def _run(args: argparse.Namespace) -> int:
    return _debate_run(args)
