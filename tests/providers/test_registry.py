import pytest
from consilium.providers.registry import ProviderRegistry


def test_registry_resolves_anthropic_models():
    registry = ProviderRegistry(anthropic_key="a", openrouter_key="b", perplexity_key="c")
    provider = registry.get_provider("claude-opus-4-7")
    assert provider.name == "anthropic"


def test_registry_resolves_openrouter_models():
    registry = ProviderRegistry(anthropic_key="a", openrouter_key="b", perplexity_key="c")
    assert registry.get_provider("openai/gpt-5").name == "openrouter"
    assert registry.get_provider("deepseek/deepseek-r1").name == "openrouter"


def test_registry_resolves_perplexity():
    registry = ProviderRegistry(anthropic_key="a", openrouter_key="b", perplexity_key="c")
    assert registry.get_provider("perplexity/sonar-deep-research").name == "perplexity"


def test_registry_unknown_model_raises():
    registry = ProviderRegistry(anthropic_key="a", openrouter_key="b", perplexity_key="c")
    with pytest.raises(KeyError):
        registry.get_provider("unknown-model-x")
