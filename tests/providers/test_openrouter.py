import pytest
import respx
from consilium.providers.base import Message
from consilium.providers.openrouter import OpenRouterProvider


@pytest.mark.asyncio
async def test_openrouter_basic_call():
    provider = OpenRouterProvider(api_key="or-test")
    with respx.mock(base_url="https://openrouter.ai") as mock:
        mock.post("/api/v1/chat/completions").respond(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "hi there"},
                        "finish_reason": "stop",
                    }
                ],
                "model": "openai/gpt-5",
                "usage": {"prompt_tokens": 20, "completion_tokens": 3},
            },
        )

        result = await provider.call(
            model="openai/gpt-5",
            system="sys",
            messages=[Message(role="user", content="hi")],
            max_tokens=100,
        )

    assert result.text == "hi there"
    assert result.usage.input_tokens == 20
