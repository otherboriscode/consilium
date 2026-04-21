import pytest
import respx
from consilium.providers.base import Message, ProviderError
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


@pytest.mark.asyncio
async def test_openrouter_raises_provider_error_on_400():
    provider = OpenRouterProvider(api_key="or-test")
    with respx.mock(base_url="https://openrouter.ai") as mock:
        mock.post("/api/v1/chat/completions").respond(
            400, json={"error": {"message": "bad request"}}
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.call(
                model="openai/gpt-5",
                system="s",
                messages=[Message(role="user", content="hi")],
                max_tokens=10,
            )
    assert exc_info.value.kind == "http_4xx"
    assert exc_info.value.status_code == 400
    assert exc_info.value.provider == "openrouter"


@pytest.mark.asyncio
async def test_openrouter_raises_provider_error_on_500():
    provider = OpenRouterProvider(api_key="or-test")
    with respx.mock(base_url="https://openrouter.ai") as mock:
        mock.post("/api/v1/chat/completions").respond(
            503, json={"error": {"message": "upstream unavailable"}}
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.call(
                model="openai/gpt-5",
                system="s",
                messages=[Message(role="user", content="hi")],
                max_tokens=10,
            )
    assert exc_info.value.kind == "http_5xx"
    assert exc_info.value.status_code == 503
