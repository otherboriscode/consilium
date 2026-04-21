from __future__ import annotations

from consilium.cost import MODEL_PRICING

from .anthropic import AnthropicProvider
from .base import BaseProvider
from .openrouter import OpenRouterProvider
from .perplexity import PerplexityProvider


class ProviderRegistry:
    """Maps a model identifier to the provider that serves it."""

    def __init__(
        self,
        *,
        anthropic_key: str,
        openrouter_key: str,
        perplexity_key: str,
    ) -> None:
        self._anthropic = AnthropicProvider(api_key=anthropic_key)
        self._openrouter = OpenRouterProvider(api_key=openrouter_key)
        self._perplexity = PerplexityProvider(api_key=perplexity_key)

    def get_provider(self, model: str) -> BaseProvider:
        if model not in MODEL_PRICING:
            raise KeyError(f"Model '{model}' not registered in MODEL_PRICING")
        if model.startswith("claude-"):
            return self._anthropic
        if model.startswith("perplexity/"):
            return self._perplexity
        if "/" in model:
            # OpenRouter serves the long-tail: openai/, google/, deepseek/, x-ai/, etc.
            return self._openrouter
        raise KeyError(f"Unknown model: {model}")
