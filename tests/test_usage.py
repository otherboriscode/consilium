from datetime import datetime, timedelta, timezone

import pytest

from consilium.archive import Archive
from consilium.usage import CurrentUsage, compute_usage
from tests.test_archive_save import make_result


def test_compute_usage_empty_archive(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    usage = compute_usage(
        archive, now=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)
    )
    assert isinstance(usage, CurrentUsage)
    assert usage.today_usd == 0.0
    assert usage.month_usd == 0.0
    assert usage.jobs_today == 0
    assert usage.jobs_this_month == 0
    assert usage.by_model == {}


def _job_at(job_id: int, when: datetime, *, cost: float = 0.020):
    r = make_result(job_id=job_id)
    # make_result default total_cost_usd=0.020; override if needed via breakdown.
    scale = cost / 0.020 if cost != 0.020 else 1.0
    return r.model_copy(
        update={
            "started_at": when,
            "completed_at": when + timedelta(seconds=5),
            "total_cost_usd": cost,
            "cost_breakdown": {
                k: v * scale for k, v in r.cost_breakdown.items()
            },
        }
    )


def test_usage_sums_today_and_month(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Two jobs today, one yesterday in the same month.
    archive.save_job(_job_at(1, day_start + timedelta(hours=2), cost=0.030))
    archive.save_job(_job_at(2, day_start + timedelta(hours=3), cost=0.050))
    archive.save_job(_job_at(3, day_start - timedelta(days=1), cost=0.020))

    usage = compute_usage(archive, now=now)
    assert usage.jobs_today == 2
    assert usage.today_usd == pytest.approx(0.08, rel=1e-3)
    assert usage.jobs_this_month == 3
    assert usage.month_usd == pytest.approx(0.10, rel=1e-3)


def test_usage_month_boundary(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.save_job(_job_at(1, datetime(2026, 3, 31, 23, 0, tzinfo=timezone.utc), cost=0.05))
    archive.save_job(_job_at(2, datetime(2026, 4, 1, 0, 30, tzinfo=timezone.utc), cost=0.07))
    usage = compute_usage(
        archive, now=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
    )
    assert usage.month_usd == pytest.approx(0.07, rel=1e-3)
    assert usage.jobs_this_month == 1


def test_usage_breakdown_by_model(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.save_job(make_result(job_id=1))
    usage = compute_usage(archive, now=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc))
    # make_result has cost_breakdown {opus: 0.015, haiku: 0.005}
    assert "claude-opus-4-7" in usage.by_model
    assert usage.by_model["claude-opus-4-7"] == pytest.approx(0.015, rel=1e-3)
    assert usage.by_model["claude-haiku-4-5"] == pytest.approx(0.005, rel=1e-3)
