import pytest
from consilium.cost import MODEL_PRICING
from consilium.model_specs import MODEL_CONTEXT_WINDOWS, get_context_window


def test_every_priced_model_has_context_window():
    for model in MODEL_PRICING:
        assert model in MODEL_CONTEXT_WINDOWS, f"Model {model!r} missing context_window"


def test_known_windows_match_docs():
    # Verify against https://docs.anthropic.com + openrouter.ai + perplexity docs 2026-04
    assert MODEL_CONTEXT_WINDOWS["claude-opus-4-7"] >= 200_000
    assert MODEL_CONTEXT_WINDOWS["google/gemini-2.5-pro"] >= 1_000_000
    assert MODEL_CONTEXT_WINDOWS["deepseek/deepseek-r1"] >= 128_000
    assert (
        MODEL_CONTEXT_WINDOWS["deepseek/deepseek-r1"]
        < MODEL_CONTEXT_WINDOWS["claude-opus-4-7"]
    )


def test_get_context_window_unknown_model_raises():
    with pytest.raises(KeyError):
        get_context_window("some-unknown-model")
