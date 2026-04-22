"""
Вызов судьи, парсинг его выхода и учёт стоимости.
Приватный модуль — используется только оркестратором.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from consilium.cost import estimate_cost
from consilium.judge_parser import JudgeParseError, parse_judge_markdown
from consilium.models import JudgeConfig, JudgeOutput
from consilium.prompts import build_judge_user_message
from consilium.providers.base import Message, ProviderError
from consilium.providers.registry import ProviderRegistry


@dataclass
class JudgeRunResult:
    """Outcome of one judge call. The orchestrator consumes this and decides
    what to show in the final JobResult (output may be None if the call failed
    entirely)."""

    output: JudgeOutput | None
    cost_usd: float
    duration_seconds: float
    error: str | None = None  # "timeout" | ProviderError.kind | "parse_error"
    truncated: bool = False  # True if provider hit max_tokens mid-output


async def run_judge(
    *,
    judge_config: JudgeConfig,
    topic: str,
    full_transcript: str,
    registry: ProviderRegistry,
) -> JudgeRunResult:
    provider = registry.get_provider(judge_config.model)
    user_msg = build_judge_user_message(topic=topic, full_transcript=full_transcript)

    try:
        result = await asyncio.wait_for(
            provider.call(
                model=judge_config.model,
                system=judge_config.system_prompt,
                messages=[Message(role="user", content=user_msg)],
                max_tokens=judge_config.max_tokens,
                deep=False,
                timeout_seconds=judge_config.timeout_seconds,
            ),
            timeout=judge_config.timeout_seconds,
        )
    except asyncio.TimeoutError:
        return JudgeRunResult(
            output=None,
            cost_usd=0.0,
            duration_seconds=judge_config.timeout_seconds,
            error="timeout",
        )
    except ProviderError as e:
        return JudgeRunResult(
            output=None, cost_usd=0.0, duration_seconds=0.0, error=e.kind
        )

    cost = estimate_cost(
        model=judge_config.model,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cache_read_tokens=result.usage.cache_read_tokens,
        cache_write_tokens=result.usage.cache_write_tokens,
    )
    truncated = result.finish_reason in ("length", "max_tokens")

    try:
        output = parse_judge_markdown(result.text)
    except JudgeParseError:
        # Preserve raw markdown for the archive; flag error for the caller.
        output = JudgeOutput(
            raw_markdown=result.text,
            tldr="",
            consensus=[],
            disagreements=[],
            unique_contributions={},
            blind_spots=[],
            recommendation="",
            scores={},
        )
        return JudgeRunResult(
            output=output,
            cost_usd=cost,
            duration_seconds=result.duration_seconds,
            error="parse_error",
            truncated=truncated,
        )

    return JudgeRunResult(
        output=output,
        cost_usd=cost,
        duration_seconds=result.duration_seconds,
        error=None,
        truncated=truncated,
    )
