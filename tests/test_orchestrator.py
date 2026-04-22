import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from consilium.models import JobConfig, JudgeConfig, ParticipantConfig
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
    text: str = "reply"
    usage_in: int = 100
    usage_out: int = 50
    raise_exc: Exception | None = None
    delay: float = 0.0


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
        if self._b.delay:
            await asyncio.sleep(self._b.delay)
        if self._b.raise_exc is not None:
            raise self._b.raise_exc
        return CallResult(
            text=self._b.text,
            usage=CallUsage(input_tokens=self._b.usage_in, output_tokens=self._b.usage_out),
            model=model,
            finish_reason="stop",
            duration_seconds=self._b.delay,
        )


class _FakeRegistry:
    def __init__(self, mapping: dict[str, BaseProvider]) -> None:
        self._m = mapping

    def get_provider(self, model: str) -> BaseProvider:
        return self._m[model]


def _cfg(*, rounds: int = 2, include_devil: bool = False) -> JobConfig:
    participants = [
        ParticipantConfig(model="claude-haiku-4-5", role="architect", system_prompt="s"),
        ParticipantConfig(model="openai/gpt-5", role="marketer", system_prompt="s"),
        ParticipantConfig(model="google/gemini-2.5-pro", role="analyst", system_prompt="s"),
    ]
    if include_devil:
        participants.append(
            ParticipantConfig(model="x-ai/grok-4", role="devil_advocate", system_prompt="s")
        )
    return JobConfig(
        topic="topic",
        participants=participants,
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=rounds,
    )


def _happy_registry() -> _FakeRegistry:
    return _FakeRegistry(
        {
            "claude-haiku-4-5": _FakeProvider(Behavior(text=FIXTURE_JUDGE)),
            "openai/gpt-5": _FakeProvider(Behavior(text="marketer answer")),
            "google/gemini-2.5-pro": _FakeProvider(Behavior(text="analyst answer")),
            "x-ai/grok-4": _FakeProvider(Behavior(text="devil answer")),
        }
    )


@pytest.mark.asyncio
async def test_run_debate_happy_path():
    cfg = _cfg(rounds=2)
    # Use a dedicated haiku provider for the judge that returns the fixture, and a
    # different "participant haiku" — BUT in our default setup architect uses haiku.
    # To keep it simple, reuse a single haiku-mock that returns FIXTURE_JUDGE for all
    # calls; participants won't parse their own text, they just quote it back.
    registry = _happy_registry()
    result = await run_debate(cfg, registry, job_id=1)  # type: ignore[arg-type]
    assert result.job_id == 1
    assert len(result.messages) == 3 * 2  # 3 participants × 2 rounds
    assert all(m.text for m in result.messages)
    assert result.judge is not None
    assert result.judge.tldr
    assert result.total_cost_usd > 0
    # cost breakdown sums to total (within float epsilon)
    assert sum(result.cost_breakdown.values()) == pytest.approx(result.total_cost_usd)


@pytest.mark.asyncio
async def test_run_debate_three_rounds():
    cfg = _cfg(rounds=3)
    result = await run_debate(cfg, _happy_registry(), job_id=2)  # type: ignore[arg-type]
    assert len(result.messages) == 3 * 3  # 3 participants × 3 rounds
    assert {m.round_index for m in result.messages} == {0, 1, 2}


@pytest.mark.asyncio
async def test_run_debate_participant_failure_does_not_stop_discussion():
    cfg = _cfg(rounds=2)
    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": _FakeProvider(Behavior(text=FIXTURE_JUDGE)),
            "openai/gpt-5": _FakeProvider(
                Behavior(
                    raise_exc=ProviderError(
                        kind="http_5xx",
                        provider="openrouter",
                        model="openai/gpt-5",
                        status_code=503,
                        message="down",
                    )
                )
            ),
            "google/gemini-2.5-pro": _FakeProvider(Behavior(text="analyst answer")),
        }
    )
    result = await run_debate(cfg, registry, job_id=3)  # type: ignore[arg-type]
    # 3 participants × 2 rounds — marketer fails both, others succeed
    assert len(result.messages) == 6
    marketer_msgs = [m for m in result.messages if m.role_slug == "marketer"]
    assert len(marketer_msgs) == 2
    assert all(m.text is None and m.error == "http_5xx" for m in marketer_msgs)
    # Architect succeeded both rounds
    architect_msgs = [m for m in result.messages if m.role_slug == "architect"]
    assert all(m.text for m in architect_msgs)


@pytest.mark.asyncio
async def test_run_debate_judge_failure_sets_judge_none():
    cfg = _cfg(rounds=1)
    # Haiku fails (used for both architect AND judge). To isolate the judge failure,
    # make architect use a different model.
    cfg = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="architect", system_prompt="s"),
            ParticipantConfig(model="google/gemini-2.5-pro", role="marketer", system_prompt="s"),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=1,
    )
    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": _FakeProvider(
                Behavior(
                    raise_exc=ProviderError(
                        kind="http_5xx",
                        provider="anthropic",
                        model="claude-haiku-4-5",
                        status_code=503,
                        message="down",
                    )
                )
            ),
            "openai/gpt-5": _FakeProvider(Behavior(text="a")),
            "google/gemini-2.5-pro": _FakeProvider(Behavior(text="m")),
        }
    )
    result = await run_debate(cfg, registry, job_id=4)  # type: ignore[arg-type]
    assert result.judge is None
    # Judge cost is zero, but participants did spend
    assert "claude-haiku-4-5" not in result.cost_breakdown
    assert result.total_cost_usd > 0


@pytest.mark.asyncio
async def test_run_debate_round_1_sees_round_0_transcript():
    """Invariant: a participant in Round 1 receives the full Round 0 transcript
    (including failed participants marked as не ответил) via the user message."""
    cfg = _cfg(rounds=2)
    # Capture the user messages sent in round 1 by making a spy provider.
    seen: list[str] = []

    class SpyProvider(BaseProvider):
        name = "spy"

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
            seen.append(messages[-1].content)
            return CallResult(
                text=f"{model} answer",
                usage=CallUsage(input_tokens=100, output_tokens=50),
                model=model,
                finish_reason="stop",
                duration_seconds=0.0,
            )

    spy = SpyProvider()
    judge = _FakeProvider(Behavior(text=FIXTURE_JUDGE))
    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": judge,
            "openai/gpt-5": spy,
            "google/gemini-2.5-pro": spy,
        }
    )
    await run_debate(cfg, registry, job_id=5)  # type: ignore[arg-type]
    # seen now contains: 2 round-0 msgs (gpt-5, gemini) + 2 round-1 msgs + 1 judge msg.
    # round-1 messages should include "Раунд 1" marker and the previous transcript.
    round_1_messages = [s for s in seen if "Раунд 1" in s]
    assert len(round_1_messages) >= 1
    # The transcript embedded in round-1 messages should carry round-0 headers.
    assert all("# Раунд 0" in s for s in round_1_messages)


@pytest.mark.asyncio
async def test_orchestrator_propagates_judge_truncated():
    """judge_truncated flag makes it into the final JobResult."""
    class _TruncJudge(BaseProvider):
        name = "trunc_judge"
        async def call(self, **kwargs):
            return CallResult(
                text=FIXTURE_JUDGE,
                usage=CallUsage(input_tokens=500, output_tokens=8000),
                model=kwargs["model"],
                finish_reason="length",
                duration_seconds=0.0,
            )

    cfg = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="a", system_prompt="s"),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=1,
    )
    registry = _FakeRegistry(
        {
            "claude-haiku-4-5": _TruncJudge(),
            "openai/gpt-5": _FakeProvider(Behavior(text="A")),
        }
    )
    result = await run_debate(cfg, registry, job_id=99)  # type: ignore[arg-type]
    assert result.judge is not None
    assert result.judge_truncated is True


@pytest.mark.asyncio
async def test_orchestrator_skips_unknown_role_in_cost_breakdown(caplog):
    """If a RoundMessage somehow has a role_slug not in config.participants,
    the orchestrator logs a warning and skips it instead of crashing."""
    import logging
    caplog.set_level(logging.WARNING)

    cfg = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="a", system_prompt="s"),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=1,
    )
    # Force a mismatch by spying and returning a message with unknown role.
    from consilium.models import RoundMessage as _RM
    from consilium.providers.base import CallUsage as _CU

    class _BrokenRegistry:
        def __init__(self, inner):
            self._inner = inner
        def get_provider(self, model):
            return self._inner.get_provider(model)

    inner = _FakeRegistry(
        {
            "claude-haiku-4-5": _FakeProvider(Behavior(text=FIXTURE_JUDGE)),
            "openai/gpt-5": _FakeProvider(Behavior(text="A")),
        }
    )

    # Monkey-patch run_round to return a message with role_slug='ghost'.
    import consilium.orchestrator as orch

    async def _fake_run_round(**kwargs):
        return [
            _RM(
                round_index=kwargs["round_index"],
                role_slug="ghost",  # not in config.participants
                text="haunted",
                error=None,
                usage=_CU(input_tokens=10, output_tokens=5),
                duration_seconds=0.1,
                cost_usd=0.01,
            )
        ]

    orig_run_round = orch.run_round
    orch.run_round = _fake_run_round
    try:
        result = await run_debate(cfg, inner, job_id=7)  # type: ignore[arg-type]
    finally:
        orch.run_round = orig_run_round

    assert any("ghost" in rec.message for rec in caplog.records)
    # Cost breakdown has no entry for 'ghost' — only judge.
    assert "ghost" not in result.cost_breakdown


class _SpyProvider(BaseProvider):
    """Captures every system prompt passed to `call`."""
    name = "spy"

    def __init__(self) -> None:
        self.captured_systems: list[str] = []
        self.text_to_return = "ok"

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
        self.captured_systems.append(system)
        return CallResult(
            text=self.text_to_return,
            usage=CallUsage(input_tokens=100, output_tokens=50),
            model=model,
            finish_reason="stop",
            duration_seconds=0.0,
        )


@pytest.mark.asyncio
async def test_run_debate_with_context_block_injects_into_system():
    spy = _SpyProvider()
    judge_provider = _FakeProvider(Behavior(text=FIXTURE_JUDGE))
    registry = _FakeRegistry(
        {
            "openai/gpt-5": spy,
            "claude-haiku-4-5": judge_provider,
        }
    )
    config = JobConfig(
        topic="test",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="r", system_prompt="ROLE_TEXT"),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="JUDGE"),
        rounds=1,
        context_block="CONTEXT_TEXT",
    )
    await run_debate(config, registry, job_id=1)  # type: ignore[arg-type]
    # system for the participant = "CONTEXT_TEXT\n\n---\n\nROLE_TEXT"
    participant_sys = spy.captured_systems[0]
    assert participant_sys.startswith("CONTEXT_TEXT")
    assert "ROLE_TEXT" in participant_sys
    assert "---" in participant_sys


@pytest.mark.asyncio
async def test_run_debate_with_context_block_cache_hit_across_rounds():
    """System is byte-identical between rounds → cacheable."""
    spy = _SpyProvider()
    judge_provider = _FakeProvider(Behavior(text=FIXTURE_JUDGE))
    registry = _FakeRegistry(
        {
            "openai/gpt-5": spy,
            "claude-haiku-4-5": judge_provider,
        }
    )
    config = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(model="openai/gpt-5", role="r", system_prompt="RP"),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="J"),
        rounds=2,
        context_block="CTX",
    )
    await run_debate(config, registry, job_id=1)  # type: ignore[arg-type]
    # 2 rounds → 2 participant calls captured; systems must match byte-for-byte.
    assert len(spy.captured_systems) == 2
    assert spy.captured_systems[0] == spy.captured_systems[1]


@pytest.mark.asyncio
async def test_run_debate_excludes_participant_when_fit_says_exclude():
    """Context so large it can't fit even as summary → participant marked
    excluded_by_fit; no API call made for them."""
    spy = _SpyProvider()
    judge_provider = _FakeProvider(Behavior(text=FIXTURE_JUDGE))
    registry = _FakeRegistry(
        {
            "deepseek/deepseek-r1": spy,
            "claude-haiku-4-5": judge_provider,
            "claude-opus-4-7": _FakeProvider(Behavior(text="opus-ok")),
        }
    )
    # Simulate a context that can't fit even with summary via a 200K-char
    # context plus a huge summary_target embedded in the participant budget.
    huge_context = "x " * 200_000  # >200K tokens
    config = JobConfig(
        topic="t",
        participants=[
            ParticipantConfig(
                model="claude-opus-4-7",  # 1M window — will get full
                role="big",
                system_prompt="S",
            ),
            ParticipantConfig(
                model="deepseek/deepseek-r1",  # 128K window — gets summary or exclude
                role="narrow",
                system_prompt="S",
            ),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="J"),
        rounds=1,
        context_block=huge_context,
    )
    # Patch the summarizer to "fail" by returning nothing useful — but we
    # actually want to force exclude via fit, not summary. Use a tiny custom
    # monkeypatch: increase deepseek participant's max_tokens so summary can't fit.
    # Easier path: since default summary_target=30K fits, we need to override.
    # Instead, directly test the excluded path via a fake-fit stub.
    import consilium.orchestrator as orch
    from consilium.context.fit import FitDecision

    orig_compute_fit = orch.compute_fit

    def _stub_fit(*, participant, **kwargs):
        if participant.model == "deepseek/deepseek-r1":
            return FitDecision(kind="exclude", reason="stubbed")
        return orig_compute_fit(participant=participant, **kwargs)

    orch.compute_fit = _stub_fit  # type: ignore[assignment]
    try:
        result = await run_debate(config, registry, job_id=9)  # type: ignore[arg-type]
    finally:
        orch.compute_fit = orig_compute_fit  # type: ignore[assignment]

    narrow_msgs = [m for m in result.messages if m.role_slug == "narrow"]
    assert len(narrow_msgs) == 1
    assert narrow_msgs[0].error == "excluded_by_fit"
    assert narrow_msgs[0].text is None
    # Spy for deepseek was never called.
    assert len(spy.captured_systems) == 0
