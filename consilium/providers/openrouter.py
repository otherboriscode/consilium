from __future__ import annotations

import time

import httpx

from .base import BaseProvider, CallResult, CallUsage, Message, wrap_http_error


class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    _base_url = "https://openrouter.ai"

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
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://consilium.local",
            "X-Title": "Consilium",
        }
        body: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                *[{"role": m.role, "content": m.content} for m in messages],
            ],
        }
        if deep:
            # OpenAI o-series: reasoning_effort. Other providers ignore unknown params.
            body["reasoning_effort"] = "high"

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=timeout_seconds
            ) as client:
                r = await client.post(
                    "/api/v1/chat/completions", headers=headers, json=body
                )
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as exc:
            raise wrap_http_error(exc, provider=self.name, model=model) from exc
        duration = time.monotonic() - t0

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return CallResult(
            text=choice["message"]["content"] or "",
            usage=CallUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cache_read_tokens=usage.get("prompt_tokens_details", {}).get(
                    "cached_tokens", 0
                ),
            ),
            model=data.get("model", model),
            finish_reason=choice.get("finish_reason", "unknown"),
            duration_seconds=duration,
        )
