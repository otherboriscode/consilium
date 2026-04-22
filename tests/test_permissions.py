from consilium.limits import DEFAULT_LIMITS
from consilium.permissions import check_permissions
from consilium.usage import CurrentUsage


def _zero_usage():
    return CurrentUsage(
        today_usd=0.0,
        month_usd=0.0,
        jobs_today=0,
        jobs_this_month=0,
        by_model={},
    )


def _usage(today=0.0, month=0.0):
    return CurrentUsage(
        today_usd=today,
        month_usd=month,
        jobs_today=0,
        jobs_this_month=0,
        by_model={},
    )


def test_small_estimate_under_all_limits_is_allowed():
    r = check_permissions(
        estimate_usd=1.0, usage=_zero_usage(), limits=DEFAULT_LIMITS
    )
    assert r.allowed is True
    assert r.violations == []
    assert r.warnings == []


def test_estimate_above_per_job_cap_is_denied():
    r = check_permissions(
        estimate_usd=40.0, usage=_zero_usage(), limits=DEFAULT_LIMITS
    )
    assert r.allowed is False
    assert any(v.kind == "per_job_cap_exceeded" for v in r.violations)


def test_monthly_cap_reached_denies_run():
    r = check_permissions(
        estimate_usd=5.0, usage=_usage(month=299.0), limits=DEFAULT_LIMITS
    )
    assert r.allowed is False
    assert any(v.kind == "monthly_cap_exceeded" for v in r.violations)


def test_hard_stop_reached_denies_run_unconditionally():
    r = check_permissions(
        estimate_usd=0.01, usage=_usage(month=500.0), limits=DEFAULT_LIMITS
    )
    assert r.allowed is False
    assert any(v.kind == "hard_stop_reached" for v in r.violations)


def test_warning_at_50_percent_threshold():
    r = check_permissions(
        estimate_usd=5.0, usage=_usage(month=150.0), limits=DEFAULT_LIMITS
    )
    assert r.allowed is True
    # Highest crossed threshold should be 50% (not 80/95 yet)
    assert any(abs(w.threshold - 0.5) < 1e-6 for w in r.warnings)


def test_warning_at_80_and_95_percent():
    r80 = check_permissions(
        estimate_usd=1.0, usage=_usage(month=240.0), limits=DEFAULT_LIMITS
    )
    r95 = check_permissions(
        estimate_usd=1.0, usage=_usage(month=285.0), limits=DEFAULT_LIMITS
    )
    assert any(abs(w.threshold - 0.8) < 1e-6 for w in r80.warnings)
    assert any(abs(w.threshold - 0.95) < 1e-6 for w in r95.warnings)


def test_daily_cap_exceeded():
    r = check_permissions(
        estimate_usd=5.0,
        usage=_usage(today=48.0, month=200.0),
        limits=DEFAULT_LIMITS,
    )
    assert r.allowed is False
    assert any(v.kind == "daily_cap_exceeded" for v in r.violations)


def test_force_bypasses_soft_caps_not_hard_stop():
    over_monthly = _usage(month=310.0)
    over_hard = _usage(month=510.0)

    r_over_monthly = check_permissions(
        estimate_usd=1.0, usage=over_monthly, limits=DEFAULT_LIMITS, force=True
    )
    r_over_hard = check_permissions(
        estimate_usd=1.0, usage=over_hard, limits=DEFAULT_LIMITS, force=True
    )
    assert r_over_monthly.allowed is True
    assert r_over_hard.allowed is False
    assert any(v.kind == "hard_stop_reached" for v in r_over_hard.violations)


def test_multiple_violations_are_collected():
    """Both per-job and monthly can fail simultaneously."""
    r = check_permissions(
        estimate_usd=40.0, usage=_usage(month=290.0), limits=DEFAULT_LIMITS
    )
    kinds = {v.kind for v in r.violations}
    assert "per_job_cap_exceeded" in kinds
    assert "monthly_cap_exceeded" in kinds
