"""Live-валидация Фазы 3: контекст-пак реально долетает до всех участников.

Проверка не «модель упомянула маркер в ответе» (flaky), а прямая — каждый
system-prompt, переданный в `provider.call()`, содержит все 8 якорей из
контекст-пака. Это доказывает, что injection работает end-to-end на реальных
моделях, не только на моках.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from consilium.context.assembly import assemble_context_block
from consilium.context.pack import create_pack
from consilium.orchestrator import run_debate
from consilium.providers.base import BaseProvider, CallResult, Message
from consilium.providers.registry import ProviderRegistry
from consilium.templates import load_template

pytestmark = pytest.mark.integration

FIX = Path(__file__).parent / "fixtures" / "tanaa_synthetic"

_ANCHORS = [
    "ANCHOR_PIDJENG_CANYON_12HA",
    "ANCHOR_TARGET_UHNW_3M2",
    "ANCHOR_STATUS_6OF8",
    "ANCHOR_UBUD_PREMIUM_18PCT",
    "ANCHOR_COMO_BAMBU",
    "ANCHOR_BANJAR_90D",
    "ANCHOR_BRAND_SILENCE",
    "ANCHOR_BRAND_NO_WALKIN",
]


class _SpyProvider(BaseProvider):
    """Wraps a real provider and records every `system` string sent to it."""

    name = "spy"

    def __init__(
        self, inner: BaseProvider, capture: list[tuple[str, str]]
    ) -> None:
        self._inner = inner
        self._capture = capture

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
        self._capture.append((model, system))
        return await self._inner.call(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            deep=deep,
            cache_last_system_block=cache_last_system_block,
            timeout_seconds=timeout_seconds,
        )


class _SpyRegistry:
    """Registry wrapper that returns spy-wrapped providers."""

    def __init__(self, inner: ProviderRegistry) -> None:
        self._inner = inner
        self.captured: list[tuple[str, str]] = []

    def get_provider(self, model: str) -> BaseProvider:
        return _SpyProvider(self._inner.get_provider(model), self.captured)


@pytest.mark.asyncio
async def test_context_anchors_reach_all_participants(tmp_path):
    for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        if not os.environ.get(key):
            pytest.skip(f"Missing env: {key}")

    pack = create_pack(
        name="tanaa_test",
        files=[FIX / "brief.md", FIX / "market.md", FIX / "brand.md"],
        root=tmp_path / "packs",
    )
    context_block = assemble_context_block(pack.files)

    # Sanity: anchors present in the assembled context block itself.
    for anchor in _ANCHORS:
        assert anchor in context_block, f"Fixture missing anchor {anchor}"

    template = load_template("product_concept")
    config = template.build_config(
        topic="Какой должна быть коммерческая инфраструктура в Tanaa Artasawa?"
    )
    config = config.model_copy(
        update={"context_block": context_block, "rounds": 1}
    )

    real_registry = ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key="unused",
    )
    spy = _SpyRegistry(real_registry)

    result = await run_debate(config, spy, job_id=9998)  # type: ignore[arg-type]

    # With 5 participants × 1 round + 1 judge = 6 captured calls.
    assert len(spy.captured) >= 6, (
        f"Expected >= 6 provider calls, got {len(spy.captured)}"
    )

    # Separate participant calls (have context) from judge call (plain system).
    judge_model = config.judge.model
    participant_calls = [
        (model, system)
        for model, system in spy.captured
        if model != judge_model
    ]
    # 5 participants × 1 round = 5
    assert len(participant_calls) == 5, (
        f"Expected 5 participant calls, got {len(participant_calls)} "
        f"(models: {[m for m, _ in participant_calls]})"
    )

    # Every participant's system prompt must embed ALL anchors.
    for idx, (model, system) in enumerate(participant_calls):
        missing = [a for a in _ANCHORS if a not in system]
        assert not missing, (
            f"Participant #{idx} ({model}) missing anchors: {missing}"
        )

    # Cost ceiling — full product_concept with 1 round + tiny context.
    assert result.total_cost_usd < 1.50, (
        f"Cost ${result.total_cost_usd:.3f} above $1.50 guard"
    )

    print(
        f"\n✓ context landed: {len(_ANCHORS)} anchors × "
        f"{len(participant_calls)} participants"
    )
    print(
        f"  cost: ${result.total_cost_usd:.3f}, "
        f"duration: {result.duration_seconds:.1f}s"
    )
