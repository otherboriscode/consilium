"""`consilium packs` — populated in Task 8.5."""
from __future__ import annotations

import argparse


def register(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(func=_stub)


def _stub(_args: argparse.Namespace) -> int:
    print("consilium packs — not yet implemented", flush=True)
    return 0
