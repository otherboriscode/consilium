"""
Главная точка входа: `run_debate(config, registry, job_id)` → `JobResult`.

Линейный async-цикл: раунд 0, раунд 1, ..., раунд N-1, затем судья. Все участники
внутри раунда — параллельно. Ошибки изолированы на уровне участника (`RoundMessage`
с `error`), на уровне судьи (`result.judge = None`), не ломают дискуссию целиком.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone

from consilium._judge_runner import run_judge
from consilium._progress import ProgressCallback, safe_progress
from consilium._round_runner import run_round
from consilium.models import JobConfig, JobResult, ProgressEvent, RoundMessage
from consilium.providers.registry import ProviderRegistry
from consilium.transcript import build_transcript_for_next_round


async def run_debate(
    config: JobConfig,
    registry: ProviderRegistry,
    *,
    job_id: int,
    progress: ProgressCallback | None = None,
) -> JobResult:
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

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
        model = next(p.model for p in config.participants if p.role == m.role_slug)
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
