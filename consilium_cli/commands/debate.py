"""
`consilium debate <topic>` — the workhorse.

Flow:
  1. Resolve config (env or ~/.config/consilium/client.yaml)
  2. If `--context <files>`, upload them as an ephemeral pack
  3. `client.preview_job()` → render preview to stdout
  4. If `--preview` — stop here; otherwise prompt [Y/n] unless `--yes`
  5. `client.submit_job()` → get job_id
  6. Subscribe SSE, render each event as one stdout line
  7. On `done`, download markdown, save to `./consilium/{id}-{slug}.md`
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from consilium_client import (
    ConsiliumClient,
    CostDenied,
    JobNotFound,
    NetworkError,
    load_config,
)
from consilium_cli.progress import extract_tldr, render_event, slugify


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", nargs="?", help="Тема дискуссии")
    parser.add_argument(
        "-t",
        "--template",
        default="product_concept",
        help="YAML-шаблон (по умолчанию product_concept)",
    )
    parser.add_argument("--pack", help="Имя уже существующего контекст-пака")
    parser.add_argument(
        "--context",
        nargs="+",
        metavar="FILE",
        help="Файлы для контекста (создаст ephemeral pack, удалит после)",
    )
    parser.add_argument("--rounds", type=int, help="Количество раундов (1-4)")
    parser.add_argument("--project", help="Группировка для архива")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Обход soft-caps (per-job/day/month). Hard-stop всё равно блокирует.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Только preview, ничего не запускать",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--output-dir",
        default="./consilium",
        type=Path,
        help="Куда сохранить итоговый markdown (по умолчанию ./consilium/)",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    if not args.topic:
        print("Нужна тема: consilium \"тема дискуссии\"", file=sys.stderr)
        return 2
    return asyncio.run(_run_async(args))


def _print_preview(pv) -> None:
    """Human-readable preview dump to stdout."""
    print("\n--- Preview ---")
    print(f"Template:       {pv.template}")
    print(f"Rounds:         {pv.rounds}")
    print(f"Judge:          {pv.judge_model}")
    print(f"Cost estimate:  ~${pv.estimated_cost_usd:.2f}")
    mins = int(pv.estimated_duration_seconds // 60)
    print(f"Duration:       ~{mins} min")
    if pv.context_tokens:
        print(f"Context:        ~{pv.context_tokens:,} tokens")
    print("Participants:")
    for p in pv.participants:
        fit_note = "" if p.fit == "full" else f"  [{p.fit}]"
        print(f"  • {p.role:20s} {p.model}  ({p.mode}){fit_note}")
    if pv.warnings:
        print("Warnings:")
        for w in pv.warnings:
            print(f"  ⚠ {w}")
    if not pv.allowed:
        print("Violations (blocks submit, use --force to bypass soft-caps):")
        for m in pv.violation_messages:
            print(f"  ⛔ {m}")


async def _upload_ephemeral_pack(
    client: ConsiliumClient, files: list[str]
) -> str:
    """Read local files and POST them as a pack. Returns the pack name so
    caller can pass it to submit_job and delete it afterwards."""
    import time

    payload: list[tuple[str, bytes]] = []
    for path_str in files:
        p = Path(path_str).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Not a file: {p}")
        payload.append((p.name, p.read_bytes()))
    name = f"_eph_{int(time.time() * 1000)}"
    await client.create_pack(name, files=payload)
    return name


async def _run_async(args: argparse.Namespace) -> int:
    try:
        cfg = load_config()
    except ValueError as e:
        print(f"⚠️  {e}", file=sys.stderr)
        return 2

    async with ConsiliumClient(
        base_url=cfg.api_base, token=cfg.token, timeout=cfg.timeout_seconds
    ) as client:
        ephemeral_pack: str | None = None
        pack_name: str | None = args.pack
        try:
            if args.context:
                try:
                    ephemeral_pack = await _upload_ephemeral_pack(
                        client, args.context
                    )
                except FileNotFoundError as e:
                    print(f"⚠️  {e}", file=sys.stderr)
                    return 2
                pack_name = ephemeral_pack

            # 1. Preview
            try:
                pv = await client.preview_job(
                    topic=args.topic,
                    template=args.template,
                    pack=pack_name,
                    rounds=args.rounds,
                    project=args.project,
                    force=args.force,
                )
            except JobNotFound as e:
                print(f"⚠️  {e}", file=sys.stderr)
                return 2
            except NetworkError as e:
                print(
                    f"🛜  Не могу достучаться до API: {e}", file=sys.stderr
                )
                return 2

            _print_preview(pv)
            if args.preview:
                return 0

            if not pv.allowed:
                print(
                    "\n⛔ Запуск заблокирован cost-guard'ом. "
                    "Добавь --force чтобы обойти soft-caps (не hard-stop).",
                    file=sys.stderr,
                )
                return 3

            if not args.yes:
                try:
                    answer = input("\nЗапускать? [Y/n]: ").strip().lower()
                except EOFError:
                    answer = "n"
                if answer and not answer.startswith("y"):
                    print("Отменено.")
                    return 0

            # 2. Submit
            try:
                submit = await client.submit_job(
                    topic=args.topic,
                    template=args.template,
                    pack=pack_name,
                    rounds=args.rounds,
                    project=args.project,
                    force=args.force,
                )
            except CostDenied as e:
                print(f"⛔ Cost guard: {', '.join(e.messages)}", file=sys.stderr)
                return 3

            print(
                f"\n🚀 Job #{submit.job_id} запущен. "
                f"Оценка: ~${submit.estimated_cost_usd:.2f}"
            )

            # 3. Stream progress
            terminal: dict = {}
            try:
                async for event in client.stream_events(submit.job_id):
                    render_event(event)
                    if event.get("kind") in ("done", "error"):
                        terminal = event
                        break
            except JobNotFound:
                # Race: stream closed before we subscribed — fall back to archive.
                pass

            # 4. Save result
            if terminal.get("kind") == "error":
                print(
                    f"\n❌ Ошибка: {terminal.get('message', '')}",
                    file=sys.stderr,
                )
                return 1

            try:
                md = await client.get_archive_md(submit.job_id)
            except JobNotFound:
                print(
                    f"\n⚠️  #{submit.job_id} завершилась, но markdown не в архиве",
                    file=sys.stderr,
                )
                return 1

            out_dir: Path = args.output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = (
                out_dir / f"{submit.job_id:04d}-{slugify(args.topic)}.md"
            )
            out_path.write_text(md, encoding="utf-8")
            print(f"\n✅ Результат: {out_path}")

            tldr = extract_tldr(md)
            if tldr:
                print("\n--- TL;DR ---")
                print(tldr)
            return 0
        finally:
            # Clean up ephemeral pack no matter what
            if ephemeral_pack is not None:
                try:
                    await client.delete_pack(ephemeral_pack)
                except Exception:
                    pass
