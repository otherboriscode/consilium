"""`consilium debate` — populated in Task 8.2."""
from __future__ import annotations

import argparse


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", nargs="?", help="Тема дискуссии")
    parser.set_defaults(func=_stub)


def _stub(_args: argparse.Namespace) -> int:
    print("consilium debate — not yet implemented", flush=True)
    return 0
