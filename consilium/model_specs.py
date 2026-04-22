"""
Context-window limits per model (input tokens).
Verify against provider docs when pricing is updated.
"""

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Anthropic — verified 2026-04
    "claude-opus-4-7": 1_000_000,  # 1M context window (GA for 4.7)
    "claude-haiku-4-5": 200_000,
    # OpenRouter → OpenAI
    "openai/gpt-5": 400_000,
    "openai/o3-pro": 200_000,
    # OpenRouter → Google
    "google/gemini-2.5-pro": 2_000_000,
    # OpenRouter → DeepSeek
    "deepseek/deepseek-r1": 128_000,  # narrowest — triggers summary/exclude
    # OpenRouter → xAI
    "x-ai/grok-4": 256_000,
    # Perplexity
    "perplexity/sonar-deep-research": 200_000,
}


def get_context_window(model: str) -> int:
    """Return max input tokens for the model. Raises KeyError for unknown models."""
    return MODEL_CONTEXT_WINDOWS[model]
