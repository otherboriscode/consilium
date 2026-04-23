"""
/jobs endpoints: submit, status, list, cancel. SSE stream is in a
dedicated module (routes/sse.py) to keep things readable.

Submission flow:
  1. Resolve template → JobConfig
  2. Load optional context (pack or inline)
  3. validate_config(limits)  → 422 on structural violations
  4. build_preview            → estimated cost
  5. compute_usage + check_permissions  → 402 on cost-cap violations
  6. Allocate job_id, create background task
  7. ServerState.register     → 429 on concurrency/rate
  8. Return 202 with SubmitJobResponse
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from consilium.archive import Archive
from consilium.context.assembly import assemble_context_block
from consilium.context.pack import load_pack
from consilium.limits import load_limits
from consilium.models import ProgressEvent as OrcProgressEvent
from consilium.orchestrator import run_debate
from consilium.permissions import check_permissions, validate_config
from consilium.preview import build_preview
from consilium.providers.registry import ProviderRegistry
from consilium.templates import TemplateError, load_template
from consilium.usage import compute_usage
from consilium_server.api.auth import AuthDep
from consilium_server.api.models import (
    ProgressEvent as ApiProgressEvent,
    SubmitJobRequest,
    SubmitJobResponse,
)
from consilium_server.api.state import (
    ConcurrencyLimitExceeded,
    JobHandle,
    RateLimitExceeded,
    get_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _archive_root() -> Path:
    return Path(
        os.environ.get(
            "CONSILIUM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "consilium"),
        )
    )


def _build_registry() -> ProviderRegistry:
    """Real provider registry. Overridden in tests via monkeypatch."""
    return ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key=os.environ.get("PERPLEXITY_API_KEY", "unused"),
    )


def _next_job_id() -> int:
    from scripts._jobid import next_job_id

    return next_job_id()


@router.post(
    "",
    response_model=SubmitJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_job(
    req: SubmitJobRequest, _: AuthDep
) -> SubmitJobResponse:
    # 1. Template
    try:
        template = load_template(req.template)
    except TemplateError as e:
        raise HTTPException(
            status_code=404, detail=f"Template {req.template!r}: {e}"
        ) from e

    config = template.build_config(topic=req.topic)
    if req.rounds is not None:
        config = config.model_copy(update={"rounds": req.rounds})
    if req.project:
        config = config.model_copy(update={"project": req.project})

    # 2. Context
    context_block: str | None = req.context_block
    if req.pack:
        try:
            pack = load_pack(req.pack)
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=404, detail=f"Pack {req.pack!r} not found"
            ) from e
        context_block = assemble_context_block(pack.files)
    if context_block is not None:
        config = config.model_copy(update={"context_block": context_block})

    # 3. Structural validation
    limits = load_limits()
    struct = validate_config(config, limits=limits)
    if not struct.allowed:
        raise HTTPException(
            status_code=422,
            detail={
                "violations": [v.kind for v in struct.violations],
                "messages": [v.message for v in struct.violations],
            },
        )

    # 4. Preview + cost check
    preview = build_preview(config, context_block=context_block)
    archive = Archive(root=_archive_root())
    usage = compute_usage(archive)
    perm = check_permissions(
        estimate_usd=preview.estimated_cost_usd,
        usage=usage,
        limits=limits,
        force=req.force,
    )
    if not perm.allowed:
        raise HTTPException(
            status_code=402,
            detail={
                "violations": [v.kind for v in perm.violations],
                "messages": [v.message for v in perm.violations],
                "estimated_cost_usd": preview.estimated_cost_usd,
            },
        )

    # 5. Allocate job_id and the JobHandle up front. Task is wired below.
    job_id = _next_job_id()
    started_at_iso = datetime.now(timezone.utc).isoformat()
    handle = JobHandle(
        job_id=job_id,
        task=None,
        started_at=time.monotonic(),
        started_at_iso=started_at_iso,
        rounds_total=config.rounds,
        estimated_cost_usd=preview.estimated_cost_usd,
        topic=config.topic,
        template=config.template_name,
        project=config.project,
    )

    state = get_state()

    async def _runner() -> None:
        registry = _build_registry()
        try:

            async def _progress(ev: OrcProgressEvent) -> None:
                api_ev = ApiProgressEvent(
                    kind=ev.kind,
                    round_index=ev.round_index,
                    role_slug=ev.role_slug,
                    message=ev.error or ev.kind,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                if api_ev.kind == "round_completed" and ev.round_index is not None:
                    handle.rounds_completed = ev.round_index + 1
                await state.publish_event(job_id, api_ev)

            result = await run_debate(
                config, registry, job_id=job_id, progress=_progress
            )
            handle.status = "completed"
            handle.current_cost_usd = result.total_cost_usd
            handle.completed_at_iso = datetime.now(timezone.utc).isoformat()
            archive.save_job(result)
            await state.publish_event(
                job_id,
                ApiProgressEvent(
                    kind="done",
                    message=f"cost=${result.total_cost_usd:.4f}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
            )
        except asyncio.CancelledError:
            handle.status = "cancelled"
            handle.completed_at_iso = datetime.now(timezone.utc).isoformat()
            raise
        except Exception as exc:
            logger.exception("Job %d failed", job_id)
            handle.status = "failed"
            handle.error = str(exc)
            handle.completed_at_iso = datetime.now(timezone.utc).isoformat()
            await state.publish_event(
                job_id,
                ApiProgressEvent(
                    kind="error",
                    message=str(exc),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
            )
        finally:
            state.unregister(job_id)

    task = asyncio.create_task(_runner())
    handle.task = task

    try:
        state.register(handle)
    except (ConcurrencyLimitExceeded, RateLimitExceeded) as e:
        task.cancel()
        raise HTTPException(status_code=429, detail=str(e)) from e

    return SubmitJobResponse(
        job_id=job_id,
        status="running",
        estimated_cost_usd=preview.estimated_cost_usd,
        estimated_duration_seconds=preview.estimated_duration_seconds,
        warnings=[w.message for w in perm.warnings],
    )
