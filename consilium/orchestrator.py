"""
Главная точка входа: `run_debate(config, registry, job_id)` → `JobResult`.

Линейный async-цикл: раунд 0, раунд 1, ..., раунд N-1, затем судья. Все участники
внутри раунда — параллельно. Ошибки изолированы на уровне участника (`RoundMessage`
с `error`), на уровне судьи (`result.judge = None`), не ломают дискуссию целиком.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from consilium._judge_runner import run_judge
from consilium._progress import ProgressCallback, safe_progress
from consilium._round_runner import run_round
from consilium.context.fit import compute_fit
from consilium.context.summarize import summarize_context
from consilium.models import JobConfig, JobResult, ProgressEvent, RoundMessage
from consilium.providers.registry import ProviderRegistry
from consilium.tokens import count_tokens
from consilium.transcript import build_transcript_for_next_round

logger = logging.getLogger(__name__)


async def _prepare_per_participant_system(
    config: JobConfig, registry: ProviderRegistry
) -> dict[str, tuple[str, str | None]]:
    """Return {role_slug: (effective_system_prompt, pre_error_or_None)}.

    - No context_block → each participant gets its own system_prompt as-is.
    - Context fits → context prepended to system_prompt (stable across rounds =>
      Anthropic prompt caching hits).
    - Context too large but summary fits → per-target-size summary, computed
      once and shared across participants needing the same target.
    - Even summary doesn't fit → pre_error="excluded_by_fit"; the round runner
      will skip the API call entirely.
    """
    if config.context_block is None:
        return {p.role: (p.system_prompt, None) for p in config.participants}

    ctx_tokens = count_tokens(config.context_block)
    out: dict[str, tuple[str, str | None]] = {}
    summary_cache: dict[int, str] = {}

    for p in config.participants:
        sp_tokens = count_tokens(p.system_prompt)
        decision = compute_fit(
            participant=p,
            context_tokens=ctx_tokens,
            system_prompt_tokens=sp_tokens,
        )
        if decision.kind == "full":
            system = f"{config.context_block}\n\n---\n\n{p.system_prompt}"
            out[p.role] = (system, None)
        elif decision.kind == "summary":
            target = decision.summary_target_tokens or 30_000
            if target not in summary_cache:
                summary_cache[target] = await summarize_context(
                    full_text=config.context_block,
                    target_tokens=target,
                    registry=registry,
                )
            summary = summary_cache[target]
            system = (
                "[КОНТЕКСТ СЖАТ автоматически под твоё окно]\n\n"
                f"{summary}\n\n---\n\n{p.system_prompt}"
            )
            out[p.role] = (system, None)
        else:  # exclude
            logger.warning(
                "participant %r excluded by fit: %s", p.role, decision.reason
            )
            out[p.role] = (p.system_prompt, "excluded_by_fit")
    return out


async def run_debate(
    config: JobConfig,
    registry: ProviderRegistry,
    *,
    job_id: int,
    progress: ProgressCallback | None = None,
) -> JobResult:
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    per_participant_system = await _prepare_per_participant_system(config, registry)

    all_messages: list[RoundMessage] = []
    for round_index in range(config.rounds):
        await safe_progress(
            progress,
            ProgressEvent(kind="round_started", round_index=round_index),
        )
        transcript = build_transcript_for_next_round(all_messages)
        round_messages = await run_round(
            participants=config.participants,
            topic=config.topic,
            round_index=round_index,
            total_rounds=config.rounds,
            transcript_so_far=transcript,
            registry=registry,
            progress=progress,
            per_participant_system=per_participant_system,
        )
        all_messages.extend(round_messages)
        await safe_progress(
            progress,
            ProgressEvent(kind="round_completed", round_index=round_index),
        )

    await safe_progress(progress, ProgressEvent(kind="judge_started"))
    full_transcript = build_transcript_for_next_round(all_messages)
    judge_result = await run_judge(
        judge_config=config.judge,
        topic=config.topic,
        full_transcript=full_transcript,
        registry=registry,
    )
    if judge_result.error is not None and judge_result.output is None:
        await safe_progress(
            progress, ProgressEvent(kind="judge_failed", error=judge_result.error)
        )
    else:
        await safe_progress(
            progress, ProgressEvent(kind="judge_completed", error=judge_result.error)
        )

    duration = time.monotonic() - t0
    completed_at = datetime.now(timezone.utc)

    cost_breakdown: dict[str, float] = defaultdict(float)
    for m in all_messages:
        model = next(
            (p.model for p in config.participants if p.role == m.role_slug),
            None,
        )
        if model is None:
            logger.warning(
                "role_slug %r not found in config.participants, skipping in cost_breakdown",
                m.role_slug,
            )
            continue
        cost_breakdown[model] += m.cost_usd
    if judge_result.cost_usd > 0:
        cost_breakdown[config.judge.model] += judge_result.cost_usd

    return JobResult(
        job_id=job_id,
        config=config,
        messages=all_messages,
        judge=judge_result.output,
        judge_truncated=judge_result.truncated,
        duration_seconds=duration,
        total_cost_usd=sum(cost_breakdown.values()),
        cost_breakdown=dict(cost_breakdown),
        started_at=started_at,
        completed_at=completed_at,
    )
