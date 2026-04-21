from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token pricing in USD. Verified 2026-04."""

    input: float
    output: float
    cache_write: float | None = None
    cache_read: float | None = None


# Source: https://docs.anthropic.com/en/docs/about-claude/pricing
# https://openrouter.ai/docs/models
# https://docs.perplexity.ai/guides/pricing
# Цены обновлять при изменении провайдерами.
MODEL_PRICING: dict[str, ModelPricing] = {
    # Anthropic direct
    "claude-opus-4-7": ModelPricing(input=15.0, output=75.0, cache_write=18.75, cache_read=1.5),
    "claude-haiku-4-5": ModelPricing(input=1.0, output=5.0, cache_write=1.25, cache_read=0.1),
    # OpenRouter
    "openai/gpt-5": ModelPricing(input=5.0, output=20.0),
    "openai/o3-pro": ModelPricing(input=60.0, output=240.0),
    "google/gemini-2.5-pro": ModelPricing(input=1.25, output=10.0),
    "deepseek/deepseek-r1": ModelPricing(input=0.55, output=2.19),
    "x-ai/grok-4": ModelPricing(input=5.0, output=15.0),
    # Perplexity
    "perplexity/sonar-deep-research": ModelPricing(input=2.0, output=8.0),
}


def estimate_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Return USD cost estimate. Raises KeyError for unknown model."""
    pricing = MODEL_PRICING[model]

    cost = 0.0
    cost += (input_tokens / 1_000_000) * pricing.input
    cost += (output_tokens / 1_000_000) * pricing.output
    if cache_read_tokens and pricing.cache_read is not None:
        cost += (cache_read_tokens / 1_000_000) * pricing.cache_read
    if cache_write_tokens and pricing.cache_write is not None:
        cost += (cache_write_tokens / 1_000_000) * pricing.cache_write
    return cost
