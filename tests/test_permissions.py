from consilium.limits import DEFAULT_LIMITS, Limits
from consilium.models import JobConfig, JudgeConfig, ParticipantConfig
from consilium.permissions import check_permissions, validate_config
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


# ---------- validate_config tests ----------


def _cfg(*, rounds=2, max_tokens=3500, context=None):
    return JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(
                model="claude-opus-4-7",
                role="architect",
                system_prompt="s",
                max_tokens=max_tokens,
            ),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=rounds,
        context_block=context,
    )


def test_validate_config_allows_defaults():
    r = validate_config(_cfg(), limits=DEFAULT_LIMITS)
    assert r.allowed is True
    assert r.violations == []


def test_validate_config_rejects_too_many_rounds():
    r = validate_config(_cfg(rounds=4), limits=DEFAULT_LIMITS)
    assert r.allowed is True  # 4 is exactly max
    # Can't test rounds>4 because JobConfig validates rounds<=4; simulate via
    # lowered limit instead.
    tight = Limits(max_rounds=1)
    r2 = validate_config(_cfg(rounds=2), limits=tight)
    assert r2.allowed is False
    assert any(v.kind == "rounds_too_many" for v in r2.violations)


def test_validate_config_rejects_huge_max_tokens():
    tight = Limits(max_tokens_per_response=1000)
    r = validate_config(_cfg(max_tokens=5000), limits=tight)
    assert r.allowed is False
    assert any(v.kind == "max_tokens_too_high" for v in r.violations)


def test_validate_config_rejects_huge_context():
    tight = Limits(max_context_tokens=1000)
    huge_context = "word " * 5000  # ~5000 tokens, well over 1000
    r = validate_config(_cfg(context=huge_context), limits=tight)
    assert r.allowed is False
    assert any(v.kind == "context_too_large" for v in r.violations)


def test_validate_config_no_context_is_ok():
    r = validate_config(_cfg(context=None), limits=DEFAULT_LIMITS)
    assert r.allowed is True
