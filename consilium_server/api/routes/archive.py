"""
Read-only archive endpoints: search, load, markdown, stats, roi.
Thin wrappers around consilium.archive.Archive.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from consilium.archive import Archive
from consilium_server.api.auth import AuthDep
from consilium_server.api.models import JobListItem

router = APIRouter(prefix="/archive", tags=["archive"])


def _archive() -> Archive:
    # Archive() reads CONSILIUM_DATA_DIR itself and appends `/archive` the
    # same way the CLI does, so server + CLI agree on one db path.
    return Archive()


def _summary_to_list_item(s) -> JobListItem:
    return JobListItem(
        job_id=s.job_id,
        status="completed",
        topic=s.topic,
        template=s.template_name,
        project=s.project,
        started_at=s.started_at,
        cost_usd=s.total_cost_usd,
        duration_seconds=s.duration_seconds,
    )


@router.get("/search", response_model=list[JobListItem])
async def search(q: str, _: AuthDep, limit: int = 20) -> list[JobListItem]:
    rows = _archive().search(q, limit=limit)
    return [_summary_to_list_item(r) for r in rows]


@router.get("/stats/by-model")
async def stats_by_model(_: AuthDep) -> list[dict]:
    rows = _archive().get_stats(group_by="model")
    return [asdict(r) for r in rows]


@router.get("/stats/by-template")
async def stats_by_template(_: AuthDep) -> list[dict]:
    rows = _archive().get_stats(group_by="template")
    return [asdict(r) for r in rows]


@router.get("/stats/by-project")
async def stats_by_project(_: AuthDep) -> list[dict]:
    rows = _archive().get_stats(group_by="project")
    return [asdict(r) for r in rows]


@router.get("/stats/roi")
async def roi_stats(_: AuthDep) -> list[dict]:
    return [asdict(r) for r in _archive().get_roi_stats()]


@router.get("/{job_id}")
async def get_archived_job(job_id: int, _: AuthDep) -> dict:
    try:
        result = _archive().load_job(job_id)
    except KeyError as e:
        raise HTTPException(
            status_code=404, detail=f"Job {job_id} not in archive"
        ) from e
    return result.model_dump(mode="json")


@router.get("/{job_id}/md", response_class=PlainTextResponse)
async def get_markdown(job_id: int, _: AuthDep) -> PlainTextResponse:
    archive = _archive()
    with archive._connect() as conn:  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT md_path FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Job {job_id} not in archive"
        )
    md_path = archive.root / row["md_path"]
    if not md_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"Job {job_id} markdown file missing"
        )
    return PlainTextResponse(md_path.read_text(encoding="utf-8"))
