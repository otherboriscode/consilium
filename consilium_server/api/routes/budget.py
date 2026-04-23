"""
Budget endpoints — thin wrappers over consilium.limits/usage/alerts/summary.
Mirrors `scripts/budget.py` CLI so clients can consume the same data.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from consilium.alerts import detect_alerts
from consilium.archive import Archive
from consilium.daily_summary import build_daily_summary
from consilium.limits import load_limits
from consilium.usage import compute_usage
from consilium_server.api.auth import AuthDep

router = APIRouter(prefix="/budget", tags=["budget"])


def _alerts_state_file() -> Path:
    base = Path(
        os.environ.get(
            "CONSILIUM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "consilium"),
        )
    )
    return base / "alerts_state.json"


@router.get("/usage")
async def usage(_: AuthDep) -> dict:
    u = compute_usage(Archive())
    return {
        "today_usd": u.today_usd,
        "month_usd": u.month_usd,
        "jobs_today": u.jobs_today,
        "jobs_this_month": u.jobs_this_month,
        "by_model": u.by_model,
    }


@router.get("/limits")
async def limits(_: AuthDep) -> dict:
    return load_limits().model_dump()


@router.get("/daily")
async def daily(_: AuthDep) -> dict:
    summary = build_daily_summary(archive=Archive(), limits=load_limits())
    return {"summary_markdown": summary}


@router.get("/alerts")
async def alerts(_: AuthDep, mark: bool = False) -> dict:
    fired = detect_alerts(
        archive=Archive(),
        limits=load_limits(),
        state_file=_alerts_state_file(),
        mark=mark,
    )
    return {
        "fired": [
            {
                "threshold": a.threshold,
                "month_cost_usd": a.month_cost_usd,
                "monthly_cap_usd": a.monthly_cap_usd,
                "message": a.message,
            }
            for a in fired
        ]
    }
