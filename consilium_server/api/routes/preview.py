"""
`POST /preview` — dry-run of /jobs.

Runs the same pre-flight as `POST /jobs` (template resolve → context load →
structural validation → cost estimate → permission check) but never
schedules a job. No `job_id` is burned and no `ServerState` slot is
consumed.

Response shape (`PreviewJobResponse`):
  - cost + duration estimates
  - context_tokens (how many tokens the assembled context block weighs)
  - per-participant `fit` (full / summary / exclude)
  - `allowed` + `violations[]` for cost-cap preflight

Error semantics intentionally diverge from `/jobs`:
  - 404 / 422 — same (unknown template/pack, structural violation)
  - 402 — NEVER returned; cost-cap violations are delivered as
    `allowed=false` in the body so the bot FSM can offer force-or-cancel
    without re-submitting.
"""
from __future__ import annotations

from fastapi import APIRouter

from consilium.context.fit import compute_fit
from consilium.tokens import count_tokens
from consilium_server.api.auth import AuthDep
from consilium_server.api.models import (
    ParticipantPreview,
    PreviewJobResponse,
    SubmitJobRequest,
)
from consilium_server.api.routes.jobs import _prepare_submission

router = APIRouter(tags=["preview"])


@router.post("/preview", response_model=PreviewJobResponse)
async def preview_job(req: SubmitJobRequest, _: AuthDep) -> PreviewJobResponse:
    config, context_block, preview, perm = _prepare_submission(req)

    ctx_tokens = count_tokens(context_block) if context_block else 0

    participants: list[ParticipantPreview] = []
    for p in config.participants:
        fit_kind: str = "full"
        if context_block:
            decision = compute_fit(
                participant=p,
                context_tokens=ctx_tokens,
                system_prompt_tokens=count_tokens(p.system_prompt),
            )
            fit_kind = decision.kind
        participants.append(
            ParticipantPreview(
                role=p.role,
                model=p.model,
                mode="deep" if p.deep else "fast",
                fit=fit_kind,  # type: ignore[arg-type]
                estimated_cost_usd=0.0,  # per-participant split is follow-up
            )
        )

    return PreviewJobResponse(
        estimated_cost_usd=preview.estimated_cost_usd,
        estimated_duration_seconds=preview.estimated_duration_seconds,
        context_tokens=ctx_tokens,
        template=config.template_name,
        rounds=config.rounds,
        participants=participants,
        judge_model=config.judge.model,
        allowed=perm.allowed,
        violations=[v.kind for v in perm.violations],
        violation_messages=[v.message for v in perm.violations],
        warnings=[w.message for w in perm.warnings],
    )
