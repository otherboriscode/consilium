from pathlib import Path

import pytest

from consilium._judge_runner import JudgeRunResult, run_judge
from consilium.models import JudgeConfig
from consilium.providers.base import BaseProvider, CallResult, CallUsage, Message, ProviderError


FIXTURE = (Path(__file__).parent / "fixtures" / "judge_output_sample.md").read_text()


class _FakeProvider(BaseProvider):
    name = "fake"

    def __init__(
        self,
        *,
        text: str | None = None,
        raise_exc: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self._text = text
        self._raise = raise_exc
        self._delay = delay

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
        import asyncio
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raise:
            raise self._raise
        assert self._text is not None
        return CallResult(
            text=self._text,
            usage=CallUsage(input_tokens=500, output_tokens=200),
            model=model,
            finish_reason="stop",
            duration_seconds=self._delay,
        )


class _FakeRegistry:
    def __init__(self, provider: BaseProvider) -> None:
        self._p = provider

    def get_provider(self, model: str) -> BaseProvider:
        return self._p


@pytest.mark.asyncio
async def test_run_judge_happy_path():
    registry = _FakeRegistry(_FakeProvider(text=FIXTURE))
    cfg = JudgeConfig(model="claude-haiku-4-5", system_prompt="j")
    res = await run_judge(
        judge_config=cfg,
        topic="T",
        full_transcript="transcript",
        registry=registry,  # type: ignore[arg-type]
    )
    assert isinstance(res, JudgeRunResult)
    assert res.output is not None
    assert res.output.tldr
    assert res.output.scores["architect"] == 3
    # claude-haiku-4-5: 500×$1/M + 200×$5/M = 0.0005 + 0.001 = 0.0015
    assert res.cost_usd == pytest.approx(0.0015, rel=1e-3)
    assert res.error is None


@pytest.mark.asyncio
async def test_run_judge_malformed_markdown_returns_output_with_raw():
    registry = _FakeRegistry(_FakeProvider(text="complete nonsense without any section headers"))
    cfg = JudgeConfig(model="claude-haiku-4-5", system_prompt="j")
    res = await run_judge(
        judge_config=cfg,
        topic="T",
        full_transcript="transcript",
        registry=registry,  # type: ignore[arg-type]
    )
    # Output is not None — we still carry raw_markdown for the archive — but structured
    # fields are empty, and error flags the parse failure.
    assert res.output is not None
    assert res.output.raw_markdown == "complete nonsense without any section headers"
    assert res.output.tldr == ""
    assert res.output.consensus == []
    assert res.output.scores == {}
    assert res.error == "parse_error"
    assert res.cost_usd > 0  # call succeeded, was billed


@pytest.mark.asyncio
async def test_run_judge_timeout_returns_none_output():
    registry = _FakeRegistry(_FakeProvider(delay=10.0, text="never gets here"))
    cfg = JudgeConfig.model_construct(
        model="claude-haiku-4-5",
        system_prompt="j",
        max_tokens=500,
        timeout_seconds=0.1,
    )
    res = await run_judge(
        judge_config=cfg,
        topic="T",
        full_transcript="transcript",
        registry=registry,  # type: ignore[arg-type]
    )
    assert res.output is None
    assert res.error == "timeout"
    assert res.cost_usd == 0.0


@pytest.mark.asyncio
async def test_run_judge_provider_error_returns_none_output():
    exc = ProviderError(
        kind="http_5xx",
        provider="anthropic",
        model="claude-haiku-4-5",
        status_code=503,
        message="down",
    )
    registry = _FakeRegistry(_FakeProvider(raise_exc=exc))
    cfg = JudgeConfig(model="claude-haiku-4-5", system_prompt="j")
    res = await run_judge(
        judge_config=cfg,
        topic="T",
        full_transcript="transcript",
        registry=registry,  # type: ignore[arg-type]
    )
    assert res.output is None
    assert res.error == "http_5xx"
    assert res.cost_usd == 0.0
