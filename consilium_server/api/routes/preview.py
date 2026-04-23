"""
`POST /preview` — dry-run of /jobs. Returns the same cost/duration estimates
without scheduling anything. Same error semantics (402 / 422 / 404).

Used by the Telegram bot to show the user a preview *before* confirming
the debate, without burning a job_id or state slot.
"""
from __future__ import annotations

from fastapi import APIRouter

from consilium_server.api.auth import AuthDep
from consilium_server.api.models import SubmitJobRequest
from consilium_server.api.routes.jobs import _prepare_submission

router = APIRouter(tags=["preview"])


@router.post("/preview")
async def preview_job(req: SubmitJobRequest, _: AuthDep) -> dict:
    # force=False for preview — cost guard is exactly what the client
    # wants to see in the preview. (If they want to bypass, they'll set
    # force=True on the real /jobs submission.)
    _, _, preview, warnings = _prepare_submission(req)
    return {
        "estimated_cost_usd": preview.estimated_cost_usd,
        "estimated_duration_seconds": preview.estimated_duration_seconds,
        "warnings": warnings,
    }
