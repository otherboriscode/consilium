"""
Pre-flight permission check для run_debate.

Сверяет оценку стоимости и текущее потребление с лимитами. Возвращает
`PermissionResult(allowed, violations, warnings)`.

- `hard_stop` блокирует всегда (даже с `force=True`).
- Остальные soft caps (per_job / daily / monthly) обходятся `force=True`.
- Warnings срабатывают на пороги `alert_thresholds` независимо от force.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from consilium.limits import Limits
from consilium.models import JobConfig
from consilium.tokens import count_tokens
from consilium.usage import CurrentUsage

ViolationKind = Literal[
    "per_job_cap_exceeded",
    "daily_cap_exceeded",
    "monthly_cap_exceeded",
    "hard_stop_reached",
    "rounds_too_many",
    "max_tokens_too_high",
    "context_too_large",
]


@dataclass(frozen=True)
class Violation:
    kind: ViolationKind
    message: str


@dataclass(frozen=True)
class Warning_:
    threshold: float  # 0.0–1.0 fraction of monthly cap
    message: str


@dataclass(frozen=True)
class PermissionResult:
    allowed: bool
    violations: list[Violation] = field(default_factory=list)
    warnings: list[Warning_] = field(default_factory=list)


def check_permissions(
    *,
    estimate_usd: float,
    usage: CurrentUsage,
    limits: Limits,
    force: bool = False,
) -> PermissionResult:
    """Decide whether a debate may launch given the estimate and current spend."""
    violations: list[Violation] = []
    warnings: list[Warning_] = []

    projected_month = usage.month_usd + estimate_usd
    projected_today = usage.today_usd + estimate_usd

    # Hard stop — non-overridable.
    if usage.month_usd >= limits.hard_stop_per_month_usd:
        violations.append(
            Violation(
                kind="hard_stop_reached",
                message=(
                    f"Hard-stop ${limits.hard_stop_per_month_usd:.0f} reached "
                    f"(месяц: ${usage.month_usd:.2f}). Ручной сброс через "
                    f"редактирование лимитов."
                ),
            )
        )
        return PermissionResult(allowed=False, violations=violations)

    if not force:
        if estimate_usd > limits.max_cost_per_job_usd:
            violations.append(
                Violation(
                    kind="per_job_cap_exceeded",
                    message=(
                        f"Оценка ${estimate_usd:.2f} выше per-job cap "
                        f"${limits.max_cost_per_job_usd:.2f}. "
                        f"Запусти с --force если это осознанно."
                    ),
                )
            )
        if projected_today > limits.max_cost_per_day_usd:
            violations.append(
                Violation(
                    kind="daily_cap_exceeded",
                    message=(
                        f"Сегодня уже ${usage.today_usd:.2f} + оценка "
                        f"${estimate_usd:.2f} > daily "
                        f"${limits.max_cost_per_day_usd:.2f}."
                    ),
                )
            )
        if projected_month > limits.max_cost_per_month_usd:
            violations.append(
                Violation(
                    kind="monthly_cap_exceeded",
                    message=(
                        f"Месяц уже ${usage.month_usd:.2f} + оценка "
                        f"${estimate_usd:.2f} > monthly "
                        f"${limits.max_cost_per_month_usd:.2f}. "
                        f"Используй --force или подними лимит."
                    ),
                )
            )

    # Warnings — independent of force.
    if limits.max_cost_per_month_usd > 0:
        month_ratio = projected_month / limits.max_cost_per_month_usd
        for threshold in sorted(limits.alert_thresholds, reverse=True):
            if month_ratio >= threshold:
                warnings.append(
                    Warning_(
                        threshold=threshold,
                        message=(
                            f"⚠️ Достигнут порог {int(threshold * 100)}% месячного "
                            f"лимита (${projected_month:.2f} из "
                            f"${limits.max_cost_per_month_usd:.0f})."
                        ),
                    )
                )
                break  # only the highest crossed threshold

    return PermissionResult(
        allowed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )


def validate_config(config: JobConfig, *, limits: Limits) -> PermissionResult:
    """Structural sanity check — rounds/max_tokens/context size. Runs BEFORE
    preview (no cost estimate needed). Catches absurd configs that would
    never have been sensible regardless of budget."""
    violations: list[Violation] = []

    if config.rounds > limits.max_rounds:
        violations.append(
            Violation(
                kind="rounds_too_many",
                message=(
                    f"rounds={config.rounds} выше max_rounds="
                    f"{limits.max_rounds}."
                ),
            )
        )

    max_mt = max(p.max_tokens for p in config.participants)
    if max_mt > limits.max_tokens_per_response:
        violations.append(
            Violation(
                kind="max_tokens_too_high",
                message=(
                    f"max_tokens={max_mt} выше max_tokens_per_response="
                    f"{limits.max_tokens_per_response}."
                ),
            )
        )

    if config.context_block is not None:
        ctx_tokens = count_tokens(config.context_block)
        if ctx_tokens > limits.max_context_tokens:
            violations.append(
                Violation(
                    kind="context_too_large",
                    message=(
                        f"context_block ≈{ctx_tokens:,} токенов превышает "
                        f"max_context_tokens={limits.max_context_tokens:,}."
                    ),
                )
            )

    return PermissionResult(allowed=len(violations) == 0, violations=violations)
