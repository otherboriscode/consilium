import pytest
from consilium.providers.base import BaseProvider, CallResult, CallUsage


def test_call_result_structure():
    result = CallResult(
        text="hello",
        usage=CallUsage(
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
            thinking_tokens=0,
        ),
        model="test-model",
        finish_reason="stop",
        duration_seconds=1.2,
    )
    assert result.text == "hello"
    assert result.usage.input_tokens == 10


def test_base_provider_is_abstract():
    with pytest.raises(TypeError):
        BaseProvider()  # type: ignore[abstract]
