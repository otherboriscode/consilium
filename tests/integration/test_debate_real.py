"""End-to-end mini-debate on real APIs. Uses the 3 cheapest reasoning models for
1 round — bounds cost at ~$0.10 per run. Skipped when keys are missing.
"""
import os

import pytest

from consilium.models import JobConfig, JudgeConfig, ParticipantConfig
from consilium.orchestrator import run_debate
from consilium.providers.registry import ProviderRegistry

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_mini_debate():
    for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        if not os.environ.get(key):
            pytest.skip(f"Missing env: {key}")

    registry = ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key="unused",
    )
    config = JobConfig(
        topic="Назови три важных фактора успеха кофейни в центре города",
        participants=[
            ParticipantConfig(
                model="claude-haiku-4-5",
                role="pragmatist",
                system_prompt="Ты прагматик. Отвечай кратко, ~200 слов.",
                max_tokens=500,
            ),
            ParticipantConfig(
                model="google/gemini-2.5-pro",
                role="analyst",
                system_prompt="Ты аналитик. Опирайся на цифры. ~200 слов.",
                max_tokens=500,
            ),
            ParticipantConfig(
                model="deepseek/deepseek-r1",
                role="skeptic",
                system_prompt="Ты скептик. Ищи слабости. ~200 слов.",
                max_tokens=500,
            ),
        ],
        judge=JudgeConfig(
            model="claude-haiku-4-5",
            system_prompt="Ты синтезатор. Отвечай по схеме.",
            max_tokens=2000,
        ),
        rounds=1,
    )
    result = await run_debate(config, registry, job_id=1)
    assert len(result.messages) == 3
    assert all(m.text or m.error for m in result.messages)
    assert result.judge is not None
    assert result.judge.tldr
    assert result.total_cost_usd < 0.50, (
        f"cost ${result.total_cost_usd:.4f} exceeded $0.50 guard"
    )
    print(f"\n=== DEBATE DONE ===\nCost: ${result.total_cost_usd:.4f}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"TL;DR: {result.judge.tldr[:200]}")
