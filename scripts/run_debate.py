#!/usr/bin/env python
"""
Минимальный CLI для ручного smoke-теста дебатов. Не пакетная команда —
запускается как `python scripts/run_debate.py "тема"` из корня репо.

Печатает прогресс в stderr, сохраняет полный markdown дебатов в `./debate-<id>.md`.
Требует в env: ANTHROPIC_API_KEY, OPENROUTER_API_KEY, PERPLEXITY_API_KEY.
"""
from __future__ import annotations

import asyncio
import os
import sys

from consilium.default_council import build_default_council
from consilium.models import ProgressEvent
from consilium.orchestrator import run_debate
from consilium.providers.registry import ProviderRegistry
from consilium.transcript import format_full_markdown


async def _print_progress(event: ProgressEvent) -> None:
    match event.kind:
        case "round_started":
            print(f"[round {event.round_index}] starting...", file=sys.stderr, flush=True)
        case "participant_completed":
            print(
                f"[round {event.round_index}] ✓ {event.role_slug}",
                file=sys.stderr,
                flush=True,
            )
        case "participant_failed":
            print(
                f"[round {event.round_index}] ✗ {event.role_slug}: {event.error}",
                file=sys.stderr,
                flush=True,
            )
        case "round_completed":
            print(f"[round {event.round_index}] done", file=sys.stderr, flush=True)
        case "judge_started":
            print("[judge] starting...", file=sys.stderr, flush=True)
        case "judge_completed":
            suffix = f" (parse: {event.error})" if event.error else ""
            print(f"[judge] done{suffix}", file=sys.stderr, flush=True)
        case "judge_failed":
            print(f"[judge] failed: {event.error}", file=sys.stderr, flush=True)


async def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/run_debate.py '<тема>'", file=sys.stderr)
        sys.exit(1)
    topic = sys.argv[1]

    missing = [
        k
        for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "PERPLEXITY_API_KEY")
        if not os.environ.get(k)
    ]
    if missing:
        print(f"Missing env vars: {missing}", file=sys.stderr)
        sys.exit(2)

    registry = ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key=os.environ["PERPLEXITY_API_KEY"],
    )
    config = build_default_council(topic=topic)
    result = await run_debate(
        config, registry, job_id=1, progress=_print_progress
    )

    out_path = f"./debate-{result.job_id}.md"
    with open(out_path, "w") as f:
        f.write(format_full_markdown(result))
    print(
        f"\nDone. Duration: {result.duration_seconds:.1f}s, "
        f"cost: ${result.total_cost_usd:.4f}",
        file=sys.stderr,
    )
    print(f"Transcript: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
