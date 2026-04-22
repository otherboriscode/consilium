"""
Ограничения на расходы и структурные параметры дискуссий.

Проверяются в pre-flight перед запуском каждой дискуссии:
 - денежные (per-job / per-day / per-month / hard-stop)
 - структурные (max_rounds, max_tokens_per_response, max_context_tokens)

Hard-stop блокирует запуск даже с `--force`. Остальные soft-caps обходятся
явным `--force` для осознанного одноразового пересечения лимита.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class Limits(BaseModel):
    """Guard rails per-spending + per-structure. Loaded from YAML + env."""

    # Денежные лимиты
    max_cost_per_job_usd: float = Field(default=25.0, gt=0)
    max_cost_per_day_usd: float = Field(default=50.0, gt=0)
    max_cost_per_month_usd: float = Field(default=300.0, gt=0)
    hard_stop_per_month_usd: float = Field(default=500.0, gt=0)

    # Структурные лимиты
    max_rounds: int = Field(default=4, ge=1)
    max_tokens_per_response: int = Field(default=16_000, ge=100)
    max_context_tokens: int = Field(default=800_000, ge=1000)

    # Пороги алертов как доли от max_cost_per_month_usd.
    alert_thresholds: list[float] = Field(default_factory=lambda: [0.5, 0.8, 0.95])

    @model_validator(mode="after")
    def _hard_stop_geq_monthly(self) -> Limits:
        if self.hard_stop_per_month_usd < self.max_cost_per_month_usd:
            raise ValueError(
                f"hard_stop_per_month_usd ({self.hard_stop_per_month_usd}) "
                f"must be >= monthly cap ({self.max_cost_per_month_usd})"
            )
        return self


DEFAULT_LIMITS = Limits()


def _default_limits_path() -> Path:
    env = os.environ.get("CONSILIUM_LIMITS_FILE")
    if env:
        return Path(env)
    return Path.home() / ".config" / "consilium" / "limits.yaml"


def load_limits(*, path: Path | None = None) -> Limits:
    """Load limits from YAML. Missing file → defaults. Partial YAML → merged
    into defaults (unspecified fields stay at their default)."""
    p = path if path is not None else _default_limits_path()
    if not p.is_file():
        return DEFAULT_LIMITS

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: limits YAML must be a mapping")

    merged = DEFAULT_LIMITS.model_dump()
    merged.update(data)
    return Limits(**merged)
