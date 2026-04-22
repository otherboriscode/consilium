from pathlib import Path

import pytest

from consilium.limits import DEFAULT_LIMITS, Limits, load_limits


def test_default_limits_are_sane():
    """Defaults come from the design doc §6."""
    assert DEFAULT_LIMITS.max_cost_per_job_usd == 25.0
    assert DEFAULT_LIMITS.max_cost_per_day_usd == 50.0
    assert DEFAULT_LIMITS.max_cost_per_month_usd == 300.0
    assert DEFAULT_LIMITS.hard_stop_per_month_usd == 500.0
    assert DEFAULT_LIMITS.max_rounds == 4
    assert DEFAULT_LIMITS.max_tokens_per_response == 16_000
    assert DEFAULT_LIMITS.max_context_tokens == 800_000


def test_load_limits_returns_defaults_when_no_file():
    limits = load_limits(path=Path("/nonexistent/limits.yaml"))
    assert limits == DEFAULT_LIMITS


def test_load_limits_merges_partial_yaml(tmp_path):
    config_file = tmp_path / "limits.yaml"
    config_file.write_text(
        "max_cost_per_job_usd: 10.0\nmax_cost_per_month_usd: 100.0\n"
    )
    limits = load_limits(path=config_file)
    assert limits.max_cost_per_job_usd == 10.0
    assert limits.max_cost_per_month_usd == 100.0
    assert limits.hard_stop_per_month_usd == DEFAULT_LIMITS.hard_stop_per_month_usd


def test_load_limits_rejects_hard_stop_below_monthly_cap(tmp_path):
    config_file = tmp_path / "limits.yaml"
    config_file.write_text(
        "max_cost_per_month_usd: 500.0\nhard_stop_per_month_usd: 300.0\n"
    )
    with pytest.raises(ValueError, match="hard_stop"):
        load_limits(path=config_file)


def test_load_limits_rejects_negative_values(tmp_path):
    config_file = tmp_path / "limits.yaml"
    config_file.write_text("max_cost_per_job_usd: -5.0\n")
    with pytest.raises(ValueError):
        load_limits(path=config_file)


def test_env_override_of_limits_file(tmp_path, monkeypatch):
    custom = tmp_path / "my-limits.yaml"
    custom.write_text("max_cost_per_job_usd: 7.0\n")
    monkeypatch.setenv("CONSILIUM_LIMITS_FILE", str(custom))
    limits = load_limits()
    assert limits.max_cost_per_job_usd == 7.0


def test_load_limits_rejects_non_mapping_yaml(tmp_path):
    config_file = tmp_path / "limits.yaml"
    config_file.write_text("- just\n- a list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_limits(path=config_file)
