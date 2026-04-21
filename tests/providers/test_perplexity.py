import json as _json

import pytest
import respx
from consilium.providers.base import Message
from consilium.providers.perplexity import PerplexityProvider


@pytest.mark.asyncio
async def test_perplexity_basic_call_with_citations():
    provider = PerplexityProvider(api_key="pplx-test")
    with respx.mock(base_url="https://api.perplexity.ai") as mock:
        route = mock.post("/chat/completions").respond(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Paris is the capital of France.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "model": "sonar-deep-research",
                "usage": {"prompt_tokens": 15, "completion_tokens": 7},
                "citations": [
                    "https://en.wikipedia.org/wiki/Paris",
                    "https://france.fr",
                ],
            },
        )

        result = await provider.call(
            model="perplexity/sonar-deep-research",
            system="You are a research assistant.",
            messages=[Message(role="user", content="What is the capital of France?")],
            max_tokens=100,
        )

    assert result.text == "Paris is the capital of France."
    assert result.usage.input_tokens == 15
    assert result.usage.output_tokens == 7
    assert result.citations == [
        "https://en.wikipedia.org/wiki/Paris",
        "https://france.fr",
    ]

    # Provider must strip the "perplexity/" prefix before calling the real API.
    parsed = _json.loads(route.calls[0].request.content)
    assert parsed["model"] == "sonar-deep-research"
