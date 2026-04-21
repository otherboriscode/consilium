from __future__ import annotations

import time

import httpx

from .base import BaseProvider, CallResult, CallUsage, Message


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    _base_url = "https://api.anthropic.com"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def call(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        max_tokens: int,
        temperature: float = 0.7,
        deep: bool = False,
        cache_last_system_block: bool = True,
        timeout_seconds: float = 300.0,
    ) -> CallResult:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31,extended-cache-ttl-2025-04-11",
            "content-type": "application/json",
        }
        system_blocks: list[dict] = [{"type": "text", "text": system}]
        if cache_last_system_block:
            system_blocks[-1]["cache_control"] = {"type": "ephemeral"}  # 5-min TTL

        body: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_blocks,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if deep:
            body["thinking"] = {"type": "enabled", "budget_tokens": 16_000}
            body["temperature"] = 1.0  # Anthropic requires temp=1 with thinking

        t0 = time.monotonic()
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout_seconds
        ) as client:
            r = await client.post("/v1/messages", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        duration = time.monotonic() - t0

        text = "".join(
            block["text"] for block in data["content"] if block.get("type") == "text"
        )
        usage = data.get("usage", {})

        return CallResult(
            text=text,
            usage=CallUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
            ),
            model=data["model"],
            finish_reason=data.get("stop_reason", "unknown"),
            duration_seconds=duration,
        )
