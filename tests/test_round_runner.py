import asyncio
import time
from dataclasses import dataclass

import pytest

from consilium._round_runner import run_round
from consilium.models import ParticipantConfig
from consilium.providers.base import (
    BaseProvider,
    CallResult,
    CallUsage,
    Message,
    ProviderError,
)


@dataclass
class FakeBehavior:
    delay: float = 0.0
    text: str | None = "ok"
    usage_in: int = 10
    usage_out: int = 5
    error: ProviderError | None = None


class FakeProvider(BaseProvider):
    name = "fake"

    def __init__(self, behavior: FakeBehavior) -> None:
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
        if self._b.delay:
            await asyncio.sleep(self._b.delay)
        if self._b.error is not None:
            raise self._b.error
        assert self._b.text is not None
        return CallResult(
            text=self._b.text,
            usage=CallUsage(
                input_tokens=self._b.usage_in, output_tokens=self._b.usage_out
            ),
            model=model,
            finish_reason="stop",
            duration_seconds=self._b.delay,
        )


class FakeRegistry:
    def __init__(self, mapping: dict[str, FakeProvider]) -> None:
        self._m = mapping

    def get_provider(self, model: str) -> BaseProvider:
        return self._m[model]


def _p(role: str, model: str, *, timeout: float = 30.0) -> ParticipantConfig:
    """Helper — uses model_construct to bypass ge=10 floor when we need sub-second
    timeouts for fast tests (the production floor is appropriate for live API calls
    but unhelpful in unit tests)."""
    return ParticipantConfig.model_construct(
        model=model,
        role=role,
        system_prompt=f"You are {role}.",
        deep=False,
        max_tokens=1200,
        timeout_seconds=timeout,
    )


@pytest.mark.asyncio
async def test_round_runner_calls_all_participants_in_parallel():
    participants = [_p(f"role_{i}", f"claude-haiku-4-5") for i in range(5)]  # noqa: F541
    # Each delays 0.1s; sequential would be 0.5s, parallel ~0.1s.
    registry = FakeRegistry(
        {"claude-haiku-4-5": FakeProvider(FakeBehavior(delay=0.1, text="answer"))}
    )
    # FakeRegistry returns the SAME instance for every call; that's fine because
    # FakeProvider.call uses no per-call state that conflicts.
    t0 = time.monotonic()
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    elapsed = time.monotonic() - t0
    assert len(msgs) == 5
    assert all(m.text == "answer" for m in msgs)
    assert elapsed < 0.3, f"Expected parallel execution <0.3s, got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_round_runner_timeout_produces_error_message():
    participants = [
        _p("fast", "claude-haiku-4-5", timeout=5.0),
        _p("slow", "openai/gpt-5", timeout=0.2),
    ]
    registry = FakeRegistry(
        {
            "claude-haiku-4-5": FakeProvider(FakeBehavior(delay=0.05, text="fast")),
            "openai/gpt-5": FakeProvider(FakeBehavior(delay=2.0, text="slow")),
        }
    )
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    assert len(msgs) == 2
    fast, slow = msgs
    assert fast.text == "fast"
    assert fast.error is None
    assert slow.text is None
    assert slow.error == "timeout"


@pytest.mark.asyncio
async def test_round_runner_provider_error_produces_error_message():
    participants = [
        _p("ok", "claude-haiku-4-5"),
        _p("broken", "openai/gpt-5"),
    ]
    registry = FakeRegistry(
        {
            "claude-haiku-4-5": FakeProvider(FakeBehavior(text="ok")),
            "openai/gpt-5": FakeProvider(
                FakeBehavior(
                    error=ProviderError(
                        kind="http_5xx",
                        provider="openrouter",
                        model="openai/gpt-5",
                        status_code=503,
                        message="upstream unavailable",
                    )
                )
            ),
        }
    )
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    ok, broken = msgs
    assert ok.text == "ok"
    assert broken.text is None
    assert broken.error == "http_5xx"


@pytest.mark.asyncio
async def test_round_runner_records_cost_per_message():
    # claude-haiku-4-5: input=$1/M, output=$5/M.
    # With usage_in=10_000 and usage_out=1_000:
    #   cost = 10_000/1M * 1 + 1_000/1M * 5 = 0.01 + 0.005 = 0.015
    participants = [_p("one", "claude-haiku-4-5")]
    registry = FakeRegistry(
        {
            "claude-haiku-4-5": FakeProvider(
                FakeBehavior(text="x", usage_in=10_000, usage_out=1_000)
            )
        }
    )
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    assert msgs[0].cost_usd == pytest.approx(0.015, rel=1e-3)


@pytest.mark.asyncio
async def test_round_runner_preserves_participant_order():
    # Make "late" participant finish LAST, but expect it at index 0 (config order).
    participants = [
        _p("late_first", "claude-haiku-4-5"),
        _p("fast_second", "openai/gpt-5"),
    ]
    registry = FakeRegistry(
        {
            "claude-haiku-4-5": FakeProvider(FakeBehavior(delay=0.2, text="L")),
            "openai/gpt-5": FakeProvider(FakeBehavior(delay=0.01, text="F")),
        }
    )
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    assert [m.role_slug for m in msgs] == ["late_first", "fast_second"]


@pytest.mark.asyncio
async def test_round_runner_empty_output_returns_error():
    """Reasoning model burned its whole max_tokens budget on thinking and returned
    an empty visible string. Orchestrator must record error='empty_output' and
    still attribute the cost of the burned tokens."""
    participants = [_p("marketer", "openai/gpt-5")]
    registry = FakeRegistry(
        {
            "openai/gpt-5": FakeProvider(
                FakeBehavior(text="", usage_in=50, usage_out=4000)
            )
        }
    )
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    assert msgs[0].text is None
    assert msgs[0].error == "empty_output"
    # Cost reflects burned tokens, not zero (we paid for reasoning).
    assert msgs[0].cost_usd > 0


@pytest.mark.asyncio
async def test_round_runner_truncated_keeps_text_and_flag():
    """Provider emitted partial text and stopped at max_tokens. Keep what we got
    and flag error='truncated' so the judge and the user see it."""
    # FakeProvider default finish_reason is "stop" — we extend Behavior to set length.
    from dataclasses import replace
    base = FakeBehavior(text="partial content", usage_in=50, usage_out=1000)
    # Hack: monkey-patch the fake to set finish_reason on the returned CallResult.
    class _TruncProvider(FakeProvider):
        async def call(self, **kwargs):
            res = await super().call(**kwargs)
            from dataclasses import replace as _replace
            return _replace(res, finish_reason="length")

    participants = [_p("marketer", "openai/gpt-5")]
    registry = FakeRegistry({"openai/gpt-5": _TruncProvider(base)})
    msgs = await run_round(
        participants=participants,
        topic="t",
        round_index=0,
        total_rounds=1,
        transcript_so_far="",
        registry=registry,
    )
    assert msgs[0].text == "partial content"
    assert msgs[0].error == "truncated"
    assert msgs[0].cost_usd > 0
    _ = replace  # silence unused-import
