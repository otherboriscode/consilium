#!/usr/bin/env python
"""
CLI для запуска дебатов. Поддерживает:
  - шаблон (--template),
  - готовый контекст-пак (--pack) или ad-hoc список файлов (--context),
  - подтверждение через preview, --yes пропускает,
  - инкрементальный job_id с file-lock.

Результат сохраняется в `./consilium/<id>-<slug>.md` в текущем CWD.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# Make `scripts.` imports work when run as `python scripts/run_debate.py`.
sys.path.insert(0, str(Path(__file__).parent.parent))

from consilium.archive import Archive  # noqa: E402
from consilium.context.assembly import assemble_context_block  # noqa: E402
from consilium.context.pack import load_pack  # noqa: E402
from consilium.context.preprocessors import preprocess_file  # noqa: E402
from consilium.models import ProgressEvent  # noqa: E402
from consilium.orchestrator import run_debate  # noqa: E402
from consilium.preview import build_preview  # noqa: E402
from consilium.providers.registry import ProviderRegistry  # noqa: E402
from consilium.templates import load_template  # noqa: E402
from consilium.transcript import format_full_markdown  # noqa: E402
from scripts._jobid import next_job_id  # noqa: E402


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(topic: str, *, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", topic.lower()).strip("-")
    return slug[:max_len] or "debate"


async def _print_progress(event: ProgressEvent) -> None:
    match event.kind:
        case "round_started":
            print(f"[round {event.round_index}] starting...", file=sys.stderr, flush=True)
        case "participant_completed":
            suffix = f" ({event.error})" if event.error else ""
            print(
                f"[round {event.round_index}] ✓ {event.role_slug}{suffix}",
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Consilium debate.")
    parser.add_argument("topic", help="Тема дискуссии (в кавычках).")
    parser.add_argument(
        "--template", default="product_concept", help="Имя YAML-шаблона."
    )
    parser.add_argument(
        "--pack", default=None, help="Имя контекст-пака (загружается из ~/.local/share/consilium/packs/)."
    )
    parser.add_argument(
        "--context",
        nargs="+",
        default=None,
        help="Ad-hoc список файлов для контекста (MD/TXT/DOCX/PDF).",
    )
    parser.add_argument(
        "--rounds", type=int, default=None, help="Переопределить количество раундов."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Пропустить preview-подтверждение."
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Тег проекта (используется для stats --by-project).",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Не сохранять в архив — только локальный файл.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Дополнительно сохранить копию в ./consilium/ рядом с текущим каталогом.",
    )
    return parser.parse_args()


def _load_context_block(args: argparse.Namespace) -> str | None:
    if args.pack and args.context:
        print("error: use either --pack or --context, not both", file=sys.stderr)
        sys.exit(2)
    if args.pack:
        pack = load_pack(args.pack)
        if pack.has_stale_files:
            print(
                f"warning: pack {args.pack!r} has stale files (edited after creation)",
                file=sys.stderr,
            )
        return assemble_context_block(pack.files)
    if args.context:
        files = [preprocess_file(Path(p)) for p in args.context]
        return assemble_context_block(files)
    return None


async def main() -> None:
    args = _parse_args()
    missing = [
        k
        for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "PERPLEXITY_API_KEY")
        if not os.environ.get(k)
    ]
    if missing:
        print(f"Missing env vars: {missing}", file=sys.stderr)
        sys.exit(2)

    template = load_template(args.template)
    config = template.build_config(topic=args.topic)
    if args.rounds is not None:
        config = config.model_copy(update={"rounds": args.rounds})
    if args.project is not None:
        config = config.model_copy(update={"project": args.project})

    context_block = _load_context_block(args)
    if context_block is not None:
        config = config.model_copy(update={"context_block": context_block})

    preview = build_preview(config, context_block=context_block)
    print(preview.text, file=sys.stderr)

    if not args.yes:
        print("", file=sys.stderr)
        try:
            answer = input("Запускать? [Y/n]: ").strip().lower()
        except EOFError:
            answer = "n"
        if answer and answer not in ("y", "yes", "да", "д"):
            print("Отменено.", file=sys.stderr)
            sys.exit(0)

    registry = ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key=os.environ["PERPLEXITY_API_KEY"],
    )

    job_id = next_job_id()
    result = await run_debate(config, registry, job_id=job_id, progress=_print_progress)

    print(
        f"\nDone. Duration: {result.duration_seconds:.1f}s, "
        f"cost: ${result.total_cost_usd:.4f}",
        file=sys.stderr,
    )

    out_paths: list[Path] = []
    if not args.no_archive:
        archive = Archive()
        saved = archive.save_job(result)
        out_paths.append(saved.md_path)

    # Local copy: always if --no-archive (there'd be no other output otherwise),
    # or on explicit --local.
    if args.no_archive or args.local:
        local_dir = Path.cwd() / "consilium"
        local_dir.mkdir(exist_ok=True)
        local_path = local_dir / f"{job_id:04d}-{_slugify(args.topic)}.md"
        local_path.write_text(format_full_markdown(result), encoding="utf-8")
        out_paths.append(local_path)

    for p in out_paths:
        print(f"Transcript: {p}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
