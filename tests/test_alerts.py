from datetime import datetime, timedelta, timezone

import pytest

from consilium.alerts import detect_alerts
from consilium.archive import Archive
from consilium.limits import Limits
from tests.test_archive_save import make_result


def _job_with_cost(job_id: int, cost: float, when: datetime):
    r = make_result(job_id=job_id)
    scale = cost / r.total_cost_usd if r.total_cost_usd > 0 else 1.0
    return r.model_copy(
        update={
            "started_at": when,
            "completed_at": when + timedelta(seconds=1),
            "total_cost_usd": cost,
            "cost_breakdown": {
                k: v * scale for k, v in r.cost_breakdown.items()
            },
        }
    )


def _limits_with_cap(monthly: float) -> Limits:
    return Limits(
        max_cost_per_job_usd=25.0,
        max_cost_per_day_usd=50.0,
        max_cost_per_month_usd=monthly,
        hard_stop_per_month_usd=monthly * 2,
    )


def test_no_alert_below_any_threshold(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    limits = _limits_with_cap(100.0)
    # $30 / $100 = 30% — ниже 50% (first threshold).
    archive.save_job(_job_with_cost(1, 30.0, now - timedelta(hours=2)))

    alerts = detect_alerts(
        archive=archive, limits=limits, state_file=tmp_path / "s.json", now=now
    )
    assert alerts == []


def test_fires_50_percent_once(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    limits = _limits_with_cap(100.0)
    archive.save_job(_job_with_cost(1, 55.0, now - timedelta(hours=2)))

    state = tmp_path / "s.json"
    first = detect_alerts(archive=archive, limits=limits, state_file=state, now=now)
    assert len(first) == 1
    assert first[0].threshold == pytest.approx(0.5)

    # Second call with identical state → nothing new.
    second = detect_alerts(archive=archive, limits=limits, state_file=state, now=now)
    assert second == []


def test_fires_higher_threshold_when_spend_grows(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    limits = _limits_with_cap(100.0)
    # Simulate state where 50% already fired.
    state = tmp_path / "s.json"
    state.write_text('{"last_fired": 0.5}')

    # Spend jumps to 85% → should fire 0.8 (not 0.5 again, not 0.95 yet).
    archive.save_job(_job_with_cost(1, 85.0, now - timedelta(hours=1)))
    alerts = detect_alerts(archive=archive, limits=limits, state_file=state, now=now)
    assert len(alerts) == 1
    assert alerts[0].threshold == pytest.approx(0.8)


def test_dry_run_does_not_mark_state(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    limits = _limits_with_cap(100.0)
    archive.save_job(_job_with_cost(1, 55.0, now - timedelta(hours=1)))

    state = tmp_path / "s.json"
    out1 = detect_alerts(
        archive=archive, limits=limits, state_file=state, now=now, mark=False
    )
    out2 = detect_alerts(
        archive=archive, limits=limits, state_file=state, now=now, mark=False
    )
    assert len(out1) == 1
    assert len(out2) == 1  # dry-run: still fires because state unchanged


def test_state_resets_on_new_month(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    limits = _limits_with_cap(100.0)
    state = tmp_path / "s.json"
    state.write_text('{"last_fired": 0.95}')

    # In a *new* month, spend is low again — we should fire 0.5 again.
    now = datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc)
    # Save a $55 job on May 2.
    archive.save_job(_job_with_cost(1, 55.0, now - timedelta(days=1)))
    alerts = detect_alerts(archive=archive, limits=limits, state_file=state, now=now)
    assert len(alerts) == 1
    assert alerts[0].threshold == pytest.approx(0.5)
