import os

import pytest

from consilium.providers.base import Message
from consilium.providers.registry import ProviderRegistry

pytestmark = pytest.mark.integration


@pytest.fixture
def registry() -> ProviderRegistry:
    keys = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "PERPLEXITY_API_KEY")
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"Missing env: {missing}")
    return ProviderRegistry(
        anthropic_key=os.environ["ANTHROPIC_API_KEY"],
        openrouter_key=os.environ["OPENROUTER_API_KEY"],
        perplexity_key=os.environ["PERPLEXITY_API_KEY"],
    )


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-7",
        "claude-haiku-4-5",
        "openai/gpt-5",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-r1",
        "x-ai/grok-4",
    ],
)
async def test_real_api_smoke(registry: ProviderRegistry, model: str):
    provider = registry.get_provider(model)
    result = await provider.call(
        model=model,
        system="You are a helpful assistant. Answer in exactly one sentence.",
        messages=[Message(role="user", content="What is 2+2?")],
        max_tokens=50,
    )
    assert result.text.strip()
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0
    print(
        f"{model}: {result.text!r} "
        f"({result.usage.input_tokens}\u2192{result.usage.output_tokens})"
    )
