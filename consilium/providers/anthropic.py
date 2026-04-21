from __future__ import annotations

import time

import httpx

from .base import BaseProvider, CallResult, CallUsage, Message, wrap_http_error


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

        # Claude 4.x deprecated explicit temperature outside thinking mode — the API
        # rejects it with 400. `temperature` stays in the signature for BaseProvider
        # parity (OpenRouter/Perplexity still use it) but is intentionally ignored here.
        body: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if deep:
            body["thinking"] = {"type": "enabled", "budget_tokens": 16_000}

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=timeout_seconds
            ) as client:
                r = await client.post("/v1/messages", headers=headers, json=body)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as exc:
            raise wrap_http_error(exc, provider=self.name, model=model) from exc
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
