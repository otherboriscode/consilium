from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token pricing in USD. Verified 2026-04-21."""

    input: float
    output: float
    cache_write: float | None = None
    cache_read: float | None = None


# Sources (verified 2026-04-21):
# - Anthropic: https://platform.claude.com/docs/en/docs/about-claude/pricing
# - OpenRouter: https://openrouter.ai/api/v1/models (live price feed)
# - Perplexity: https://docs.perplexity.ai/guides/pricing
# Cache write values for Anthropic are 5-minute ephemeral TTL (1.25x base input).
# Цены обновлять при изменении провайдерами.
MODEL_PRICING: dict[str, ModelPricing] = {
    # Anthropic direct
    "claude-opus-4-7": ModelPricing(input=5.0, output=25.0, cache_write=6.25, cache_read=0.5),
    "claude-haiku-4-5": ModelPricing(input=1.0, output=5.0, cache_write=1.25, cache_read=0.1),
    # OpenRouter
    "openai/gpt-5": ModelPricing(input=1.25, output=10.0, cache_read=0.125),
    "openai/o3-pro": ModelPricing(input=20.0, output=80.0),
    "google/gemini-2.5-pro": ModelPricing(
        input=1.25, output=10.0, cache_write=0.375, cache_read=0.125
    ),
    "deepseek/deepseek-r1": ModelPricing(input=0.70, output=2.50),
    "x-ai/grok-4": ModelPricing(input=3.0, output=15.0, cache_read=0.75),
    # Perplexity (sonar-deep-research has extra per-request and per-citation fees
    # that are not modeled here — see docs link above).
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
