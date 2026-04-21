import pytest
from consilium.cost import estimate_cost, MODEL_PRICING


def test_pricing_contains_all_default_models():
    expected = {
        "claude-opus-4-7",
        "claude-haiku-4-5",
        "openai/gpt-5",
        "openai/o3-pro",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-r1",
        "x-ai/grok-4",
        "perplexity/sonar-deep-research",
    }
    assert expected.issubset(MODEL_PRICING.keys())


def test_estimate_cost_basic():
    # 10K input + 1K output for claude-opus-4-7 @ $5/M input, $25/M output
    cost = estimate_cost(
        model="claude-opus-4-7",
        input_tokens=10_000,
        output_tokens=1_000,
    )
    # 10K × $5/M = $0.05 + 1K × $25/M = $0.025
    assert cost == pytest.approx(0.05 + 0.025, rel=1e-3)


def test_estimate_cost_with_cache_read():
    # Cache read tokens billed at 10% of input price (Anthropic)
    cost = estimate_cost(
        model="claude-opus-4-7",
        input_tokens=0,
        output_tokens=1_000,
        cache_read_tokens=10_000,
    )
    # 10K cache read @ $0.50/M = $0.005 + 1K output @ $25/M = $0.025
    assert cost == pytest.approx(0.005 + 0.025, rel=1e-3)


def test_estimate_cost_unknown_model_raises():
    with pytest.raises(KeyError):
        estimate_cost(model="nonexistent-model", input_tokens=100, output_tokens=100)
