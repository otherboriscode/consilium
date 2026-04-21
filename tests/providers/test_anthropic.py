import pytest
import respx
from consilium.providers.anthropic import AnthropicProvider
from consilium.providers.base import Message


@pytest.mark.asyncio
async def test_basic_call():
    provider = AnthropicProvider(api_key="sk-test-key")

    with respx.mock(base_url="https://api.anthropic.com") as mock:
        mock.post("/v1/messages").respond(
            200,
            json={
                "content": [{"type": "text", "text": "Hello from Claude"}],
                "model": "claude-opus-4-7",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 42,
                    "output_tokens": 7,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            },
        )

        result = await provider.call(
            model="claude-opus-4-7",
            system="You are helpful.",
            messages=[Message(role="user", content="Hi")],
            max_tokens=100,
        )

    assert result.text == "Hello from Claude"
    assert result.usage.input_tokens == 42
    assert result.usage.output_tokens == 7
    assert result.model == "claude-opus-4-7"
