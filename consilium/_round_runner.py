"""
Выполнение одного раунда: параллельный вызов всех участников с таймаутом и
ловлей `ProviderError`. Приватный модуль — используется только оркестратором.
"""
from __future__ import annotations

import asyncio

from consilium._progress import ProgressCallback, safe_progress
from consilium.cost import estimate_cost
from consilium.models import ParticipantConfig, ProgressEvent, RoundMessage
from consilium.prompts import build_round_user_message
from consilium.providers.base import CallUsage, Message, ProviderError
from consilium.providers.registry import ProviderRegistry


async def _call_one_participant(
    *,
    participant: ParticipantConfig,
    topic: str,
    round_index: int,
    total_rounds: int,
    transcript_so_far: str,
    registry: ProviderRegistry,
    progress: ProgressCallback | None = None,
    per_participant_system: dict[str, tuple[str, str | None]] | None = None,
) -> RoundMessage:
    # Resolve effective system + any pre-assigned error (e.g. excluded_by_fit).
    system_text, pre_error = (
        per_participant_system.get(participant.role, (participant.system_prompt, None))
        if per_participant_system is not None
        else (participant.system_prompt, None)
    )
    if pre_error == "excluded_by_fit":
        msg = RoundMessage(
            round_index=round_index,
            role_slug=participant.role,
            text=None,
            error="excluded_by_fit",
            usage=CallUsage(input_tokens=0, output_tokens=0),
            duration_seconds=0.0,
            cost_usd=0.0,
        )
        await safe_progress(
            progress,
            ProgressEvent(
                kind="participant_failed",
                round_index=round_index,
                role_slug=participant.role,
                error="excluded_by_fit",
            ),
        )
        return msg

    user_msg_text = build_round_user_message(
        topic=topic,
        round_index=round_index,
        transcript_so_far=transcript_so_far,
        participant=participant,
        total_rounds=total_rounds,
    )
    provider = registry.get_provider(participant.model)
    try:
        result = await asyncio.wait_for(
            provider.call(
                model=participant.model,
                system=system_text,
                messages=[Message(role="user", content=user_msg_text)],
                max_tokens=participant.max_tokens,
                deep=participant.deep,
                timeout_seconds=participant.timeout_seconds,
            ),
            timeout=participant.timeout_seconds,
        )
        cost = estimate_cost(
            model=participant.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_read_tokens=result.usage.cache_read_tokens,
            cache_write_tokens=result.usage.cache_write_tokens,
        )

        # Empty output: reasoning burned the whole budget, no visible text.
        if not result.text.strip():
            msg = RoundMessage(
                round_index=round_index,
                role_slug=participant.role,
                text=None,
                error="empty_output",
                usage=result.usage,
                duration_seconds=result.duration_seconds,
                cost_usd=cost,
            )
            await safe_progress(
                progress,
                ProgressEvent(
                    kind="participant_failed",
                    round_index=round_index,
                    role_slug=participant.role,
                    error="empty_output",
                ),
            )
            return msg

        # Truncated output: text present but provider hit max_tokens.
        if result.finish_reason in ("length", "max_tokens"):
            msg = RoundMessage(
                round_index=round_index,
                role_slug=participant.role,
                text=result.text,
                error="truncated",
                usage=result.usage,
                duration_seconds=result.duration_seconds,
                cost_usd=cost,
            )
            await safe_progress(
                progress,
                ProgressEvent(
                    kind="participant_completed",
                    round_index=round_index,
                    role_slug=participant.role,
                    error="truncated",
                ),
            )
            return msg

        msg = RoundMessage(
            round_index=round_index,
            role_slug=participant.role,
            text=result.text,
            error=None,
            usage=result.usage,
            duration_seconds=result.duration_seconds,
            cost_usd=cost,
        )
        await safe_progress(
            progress,
            ProgressEvent(
                kind="participant_completed",
                round_index=round_index,
                role_slug=participant.role,
            ),
        )
        return msg
    except asyncio.TimeoutError:
        msg = RoundMessage(
            round_index=round_index,
            role_slug=participant.role,
            text=None,
            error="timeout",
            usage=CallUsage(input_tokens=0, output_tokens=0),
            duration_seconds=participant.timeout_seconds,
            cost_usd=0.0,
        )
        await safe_progress(
            progress,
            ProgressEvent(
                kind="participant_failed",
                round_index=round_index,
                role_slug=participant.role,
                error="timeout",
            ),
        )
        return msg
    except ProviderError as e:
        msg = RoundMessage(
            round_index=round_index,
            role_slug=participant.role,
            text=None,
            error=e.kind,
            usage=CallUsage(input_tokens=0, output_tokens=0),
            duration_seconds=0.0,
            cost_usd=0.0,
        )
        await safe_progress(
            progress,
            ProgressEvent(
                kind="participant_failed",
                round_index=round_index,
                role_slug=participant.role,
                error=e.kind,
            ),
        )
        return msg


async def run_round(
    *,
    participants: list[ParticipantConfig],
    topic: str,
    round_index: int,
    total_rounds: int,
    transcript_so_far: str,
    registry: ProviderRegistry,
    progress: ProgressCallback | None = None,
    per_participant_system: dict[str, tuple[str, str | None]] | None = None,
) -> list[RoundMessage]:
    """Run all participants in parallel for one round. Preserves input order."""
    coros = [
        _call_one_participant(
            participant=p,
            topic=topic,
            round_index=round_index,
            total_rounds=total_rounds,
            transcript_so_far=transcript_so_far,
            registry=registry,
            progress=progress,
            per_participant_system=per_participant_system,
        )
        for p in participants
    ]
    return list(await asyncio.gather(*coros))
