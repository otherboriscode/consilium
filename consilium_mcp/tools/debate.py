"""
Debate lifecycle MCP tools.

Tools:
  consilium_preview   — dry-run, returns cost + per-participant fit
  consilium_start     — submit job, returns job_id (async — pair with _wait)
  consilium_status    — poll status of one job
  consilium_wait      — block on SSE until done, save markdown, return TL;DR
  consilium_cancel    — cancel an active job

`context_files` parameter (paths on the local filesystem where Claude
Code runs) is uploaded as an ephemeral pack `_eph_{ms}`. It's cleaned
up in `consilium_wait` after the job finishes (or on failure via
try/finally in the handler).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from consilium_client import (
    ConsiliumClient,
    CostDenied,
    JobNotFound,
    JobStatus,
    NetworkError,
)
from consilium_mcp.registry import Registry, ToolSpec

_EPHEMERAL_PREFIX = "_eph_"


# ---------- schema snippets ----------


_SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "template": {"type": "string", "default": "product_concept"},
        "pack": {"type": "string"},
        "context_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Absolute local file paths to bundle as an ephemeral pack."
            ),
        },
        "rounds": {"type": "integer", "minimum": 1, "maximum": 4},
        "project": {"type": "string"},
        "force": {"type": "boolean", "default": False},
    },
    "required": ["topic"],
}


# ---------- helpers ----------


async def _upload_ephemeral_pack(
    client: ConsiliumClient, paths: list[str]
) -> str:
    """Read local files and POST them as a pack. Returns the pack name."""
    payload: list[tuple[str, bytes]] = []
    for p_str in paths:
        p = Path(p_str).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Not a file: {p}")
        payload.append((p.name, p.read_bytes()))
    name = f"{_EPHEMERAL_PREFIX}{int(time.time() * 1000)}"
    await client.create_pack(name, files=payload)
    return name


def _slugify(text: str, max_len: int = 40) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w\-а-яё]", "", text, flags=re.UNICODE)
    return text[:max_len] or "debate"


def _extract_tldr(md: str) -> str:
    tldr_re = re.compile(r"^#+\s*TL;DR\s*$", re.IGNORECASE | re.MULTILINE)
    h1_re = re.compile(r"^#\s+.+", re.MULTILINE)
    m = tldr_re.search(md)
    if not m:
        return ""
    tail = md[m.end():]
    next_h = h1_re.search(tail)
    section = tail[: next_h.start()] if next_h else tail
    return section.strip()[:2000]


def _resolve_output_path(job_id: int, topic: str, save_to: str | None) -> Path:
    if save_to:
        return Path(save_to).expanduser()
    return Path.cwd() / "consilium" / f"{job_id:04d}-{_slugify(topic)}.md"


def _friendly_progress(event: dict) -> str:
    """Translate a raw SSE event into a one-line user-facing message."""
    kind = event.get("kind", "")
    round_idx = event.get("round_index")
    role = event.get("role_slug") or "?"
    if kind == "round_started":
        return f"Раунд {round_idx} пошёл"
    if kind == "participant_completed":
        return f"{role} ответил (раунд {round_idx})"
    if kind == "participant_failed":
        return f"{role}: {event.get('error') or event.get('message') or 'ошибка'}"
    if kind == "round_completed":
        return f"Раунд {round_idx} завершён"
    if kind == "judge_started":
        return "Судья синтезирует"
    if kind == "judge_completed":
        return "Судья готов"
    if kind == "done":
        return f"Готово: {event.get('message', '')}"
    if kind == "error":
        return f"Ошибка: {event.get('message', '')}"
    return kind or "(событие)"


# ---------- tool handlers ----------


def register(registry: Registry, *, client_factory) -> None:
    async def _preview(args: dict, **_) -> dict:
        async with client_factory() as client:
            pack = args.get("pack")
            try:
                if args.get("context_files"):
                    pack = await _upload_ephemeral_pack(
                        client, args["context_files"]
                    )
                pv = await client.preview_job(
                    topic=args["topic"],
                    template=args.get("template", "product_concept"),
                    pack=pack,
                    rounds=args.get("rounds"),
                    project=args.get("project"),
                    force=bool(args.get("force", False)),
                )
            finally:
                if pack and pack.startswith(_EPHEMERAL_PREFIX):
                    # preview doesn't actually run the debate, so we can
                    # drop the ephemeral pack immediately.
                    try:
                        await client.delete_pack(pack)
                    except Exception:  # noqa: BLE001
                        pass

        return {
            "estimated_cost_usd": pv.estimated_cost_usd,
            "estimated_duration_seconds": pv.estimated_duration_seconds,
            "context_tokens": pv.context_tokens,
            "template": pv.template,
            "rounds": pv.rounds,
            "participants": [
                {
                    "role": p.role,
                    "model": p.model,
                    "mode": p.mode,
                    "fit": p.fit,
                }
                for p in pv.participants
            ],
            "judge_model": pv.judge_model,
            "allowed": pv.allowed,
            "violations": pv.violations,
            "violation_messages": pv.violation_messages,
            "warnings": pv.warnings,
        }

    async def _start(args: dict, **_) -> dict:
        async with client_factory() as client:
            pack = args.get("pack")
            if args.get("context_files"):
                pack = await _upload_ephemeral_pack(
                    client, args["context_files"]
                )
            try:
                submit = await client.submit_job(
                    topic=args["topic"],
                    template=args.get("template", "product_concept"),
                    pack=pack,
                    rounds=args.get("rounds"),
                    project=args.get("project"),
                    force=bool(args.get("force", False)),
                )
            except CostDenied as e:
                # Leave ephemeral pack orphaned on denial — cleanup is
                # best-effort and the next _start or _preview will dispose.
                return {
                    "error": "cost_denied",
                    "violations": e.violations,
                    "messages": e.messages,
                    "estimated_cost_usd": e.estimate,
                }
        return {
            "job_id": submit.job_id,
            "status": submit.status,
            "estimated_cost_usd": submit.estimated_cost_usd,
            "estimated_duration_seconds": submit.estimated_duration_seconds,
            "warnings": submit.warnings,
            "ephemeral_pack": pack if pack and pack.startswith(_EPHEMERAL_PREFIX) else None,
        }

    async def _status(args: dict, **_) -> dict:
        async with client_factory() as client:
            s = await client.get_status(int(args["job_id"]))
        return {
            "job_id": s.job_id,
            "status": s.status,
            "rounds_completed": s.rounds_completed,
            "rounds_total": s.rounds_total,
            "current_cost_usd": s.current_cost_usd,
            "estimated_cost_usd": s.estimated_cost_usd,
            "template": s.template,
            "topic": s.topic,
            "project": s.project,
            "error": s.error,
        }

    async def _cancel(args: dict, **_) -> dict:
        async with client_factory() as client:
            try:
                await client.cancel_job(int(args["job_id"]))
            except JobNotFound as e:
                return {"error": "not_found", "message": str(e)}
        return {"cancelled": True, "job_id": int(args["job_id"])}

    async def _wait(args: dict, *, progress=None, **_) -> dict:
        """Block on a running debate until done; report progress to client."""
        job_id = int(args["job_id"])
        save_to = args.get("save_to")
        ephemeral_pack = args.get("ephemeral_pack")

        async def _report(p: float, total: float | None, msg: str) -> None:
            if progress is not None:
                try:
                    await progress(p, total, msg)
                except Exception:  # noqa: BLE001
                    # Progress is best-effort — never let a notification
                    # failure kill the tool call.
                    pass

        async with client_factory() as client:
            rounds_total = 1
            try:
                first_status = await client.get_status(job_id)
                rounds_total = max(1, first_status.rounds_total)
            except JobNotFound:
                pass

            terminal: dict = {}
            try:
                async for ev in client.stream_events(job_id):
                    kind = ev.get("kind", "")
                    msg = _friendly_progress(ev)
                    if kind == "round_completed":
                        idx = int(ev.get("round_index", 0)) + 1
                        pct = min(95, int(100 * idx / (rounds_total + 1)))
                        await _report(pct, 100, msg)
                    elif kind == "judge_started":
                        await _report(90, 100, msg)
                    elif kind in ("done", "judge_completed"):
                        await _report(100, 100, msg)
                        terminal = ev
                        break
                    elif kind == "error":
                        await _report(100, 100, msg)
                        terminal = ev
                        break
                    else:
                        # mid-round events — small bump so the UI ticks
                        await _report(0, 100, msg)
            except (JobNotFound, NetworkError):
                # Race: stream closed before we subscribed, or transient
                # net hiccup. Fall through to archive.
                pass

            # Pre-bind so the JobNotFound branch leaves a sane sentinel
            # for the cost_usd lookup at the end (R1 from Phase 8 review).
            status: JobStatus | None = None
            topic = ""
            try:
                status = await client.get_status(job_id)
                topic = status.topic
            except JobNotFound:
                pass

            if terminal.get("kind") == "error":
                return {
                    "error": "job_failed",
                    "message": terminal.get("message", ""),
                }

            try:
                md = await client.get_archive_md(job_id)
            except JobNotFound:
                return {
                    "error": "markdown_missing",
                    "message": f"Job {job_id} not in archive",
                }

            out_path = _resolve_output_path(job_id, topic or "debate", save_to)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md, encoding="utf-8")

            # Ephemeral pack cleanup — best-effort.
            if ephemeral_pack and str(ephemeral_pack).startswith(
                _EPHEMERAL_PREFIX
            ):
                try:
                    await client.delete_pack(ephemeral_pack)
                except Exception:  # noqa: BLE001
                    pass

            return {
                "md_path": str(out_path),
                "tldr": _extract_tldr(md),
                "cost_usd": status.current_cost_usd if status else None,
            }

    registry.add(
        ToolSpec(
            name="consilium_preview",
            description=(
                "Dry-run a Consilium debate — returns estimated cost, "
                "duration, per-participant fit, and cost-guard verdict "
                "without starting anything."
            ),
            input_schema=_SUBMIT_SCHEMA,
            handler=_preview,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_start",
            description=(
                "Submit a Consilium debate and return job_id. Pair with "
                "consilium_wait to block on completion. If context_files "
                "is provided, they're uploaded as an ephemeral pack."
            ),
            input_schema=_SUBMIT_SCHEMA,
            handler=_start,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_status",
            description="Current status of one debate.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
            handler=_status,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_cancel",
            description="Cancel an in-flight debate.",
            input_schema={
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
            handler=_cancel,
        )
    )
    registry.add(
        ToolSpec(
            name="consilium_wait",
            description=(
                "Block on a running debate until it finishes, then "
                "download the markdown transcript and save it locally. "
                "Returns the save path, TL;DR, and final cost."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "save_to": {
                        "type": "string",
                        "description": (
                            "Local path to save the markdown. Defaults "
                            "to ./consilium/{id}-{slug}.md."
                        ),
                    },
                    "ephemeral_pack": {
                        "type": "string",
                        "description": (
                            "If the debate was started with context_files, "
                            "pass the ephemeral_pack name from "
                            "consilium_start so it can be cleaned up."
                        ),
                    },
                },
                "required": ["job_id"],
            },
            handler=_wait,
        )
    )
