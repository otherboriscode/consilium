import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from consilium.models import JobConfig, JudgeConfig, ParticipantConfig, ProgressEvent
from consilium.orchestrator import run_debate
from consilium.providers.base import (
    BaseProvider,
    CallResult,
    CallUsage,
    Message,
    ProviderError,
)


FIXTURE_JUDGE = (Path(__file__).parent / "fixtures" / "judge_output_sample.md").read_text()


@dataclass
class Behavior:
    text: str = "ok"
    raise_exc: Exception | None = None


class _FakeProvider(BaseProvider):
    name = "fake"

    def __init__(self, behavior: Behavior) -> None:
        self._b = behavior

    async def call(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        deep: bool = False,
        cache_last_system_block: bool = True,
        timeout_seconds: float = 300.0,
    ) -> CallResult:
        if self._b.raise_exc is not None:
            raise self._b.raise_exc
        return CallResult(
            text=self._b.text,
            usage=CallUsage(input_tokens=100, output_tokens=50),
            model=model,
            finish_reason="stop",
            duration_seconds=0.0,
        )


class _FakeRegistry:
    def __init__(self, mapping: dict[str, BaseProvider]) -> None:
        self._m = mapping

    def get_provider(self, model: str) -> BaseProvider:
        return self._m[model]


def _basic_cfg(rounds: int = 1) -> JobConfig:
    return JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="a", system_prompt="s"),
            ParticipantConfig(model="google/gemini-2.5-pro", role="b", system_prompt="s"),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=rounds,
    )


@pytest.mark.asyncio
async def test_progress_emits_all_event_kinds_in_happy_path():
    events: list[ProgressEvent] = []

    async def record(e: ProgressEvent) -> None:
        events.append(e)

    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": _FakeProvider(Behavior(text=FIXTURE_JUDGE)),
            "openai/gpt-5": _FakeProvider(Behavior(text="A")),
            "google/gemini-2.5-pro": _FakeProvider(Behavior(text="B")),
        }
    )
    await run_debate(_basic_cfg(rounds=2), registry, job_id=1, progress=record)  # type: ignore[arg-type]

    kinds = [e.kind for e in events]
    # Expected sequence: for each of 2 rounds → round_started, 2×participant_completed,
    # round_completed. Then judge_started → judge_completed.
    assert kinds.count("round_started") == 2
    assert kinds.count("round_completed") == 2
    assert kinds.count("participant_completed") == 4  # 2 participants × 2 rounds
    assert kinds.count("judge_started") == 1
    assert kinds.count("judge_completed") == 1
    assert kinds.count("participant_failed") == 0
    assert kinds.count("judge_failed") == 0

    # First event must be round_started with round_index=0
    assert events[0].kind == "round_started" and events[0].round_index == 0
    # Last event must be judge_completed
    assert events[-1].kind == "judge_completed"


@pytest.mark.asyncio
async def test_progress_emits_participant_failed_on_provider_error():
    events: list[ProgressEvent] = []

    async def record(e: ProgressEvent) -> None:
        events.append(e)

    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": _FakeProvider(Behavior(text=FIXTURE_JUDGE)),
            "openai/gpt-5": _FakeProvider(
                Behavior(
                    raise_exc=ProviderError(
                        kind="http_4xx",
                        provider="openrouter",
                        model="openai/gpt-5",
                        status_code=400,
                        message="bad",
                    )
                )
            ),
            "google/gemini-2.5-pro": _FakeProvider(Behavior(text="B")),
        }
    )
    await run_debate(_basic_cfg(rounds=1), registry, job_id=2, progress=record)  # type: ignore[arg-type]

    failures = [e for e in events if e.kind == "participant_failed"]
    assert len(failures) == 1
    assert failures[0].role_slug == "a"
    assert failures[0].error == "http_4xx"


@pytest.mark.asyncio
async def test_progress_emits_judge_failed_on_judge_timeout():
    events: list[ProgressEvent] = []

    async def record(e: ProgressEvent) -> None:
        events.append(e)

    class HangingProvider(BaseProvider):
        name = "hanging"

        async def call(self, **kwargs) -> CallResult:
            await asyncio.sleep(60.0)
            raise AssertionError("should have timed out")

    cfg = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="a", system_prompt="s"),
        ],
        judge=JudgeConfig.model_construct(
            model="claude-haiku-4-5",
            system_prompt="j",
            max_tokens=500,
            timeout_seconds=0.1,
        ),
        rounds=1,
    )
    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": HangingProvider(),
            "openai/gpt-5": _FakeProvider(Behavior(text="A")),
        }
    )
    result = await run_debate(cfg, registry, job_id=3, progress=record)  # type: ignore[arg-type]
    assert result.judge is None
    judge_failed = [e for e in events if e.kind == "judge_failed"]
    assert len(judge_failed) == 1
    assert judge_failed[0].error == "timeout"
