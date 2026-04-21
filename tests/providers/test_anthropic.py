import json as _json

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


@pytest.mark.asyncio
async def test_extended_thinking_when_deep():
    provider = AnthropicProvider(api_key="sk-test-key")

    with respx.mock(base_url="https://api.anthropic.com") as mock:
        route = mock.post("/v1/messages").respond(
            200,
            json={
                "content": [{"type": "text", "text": "thought-through answer"}],
                "model": "claude-opus-4-7",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        )

        await provider.call(
            model="claude-opus-4-7",
            system="...",
            messages=[Message(role="user", content="hi")],
            max_tokens=2000,
            deep=True,
        )

    sent_body = route.calls[0].request.content
    parsed = _json.loads(sent_body)
    assert parsed["thinking"]["type"] == "enabled"
    assert parsed["thinking"]["budget_tokens"] >= 8_000


@pytest.mark.asyncio
async def test_system_prompt_has_cache_control_when_enabled():
    provider = AnthropicProvider(api_key="sk-test-key")

    with respx.mock(base_url="https://api.anthropic.com") as mock:
        route = mock.post("/v1/messages").respond(
            200,
            json={
                "content": [{"type": "text", "text": "x"}],
                "model": "claude-opus-4-7",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        )

        await provider.call(
            model="claude-opus-4-7",
            system="long shared context block",
            messages=[Message(role="user", content="hi")],
            max_tokens=100,
            cache_last_system_block=True,
        )

    parsed = _json.loads(route.calls[0].request.content)
    # system должна быть списком блоков с cache_control на последнем
    assert isinstance(parsed["system"], list)
    assert parsed["system"][-1]["cache_control"] == {"type": "ephemeral"}
