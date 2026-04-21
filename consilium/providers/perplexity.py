from __future__ import annotations

import time

import httpx

from .base import BaseProvider, CallResult, CallUsage, Message

_MODEL_PREFIX = "perplexity/"


class PerplexityProvider(BaseProvider):
    name = "perplexity"
    _base_url = "https://api.perplexity.ai"

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
        # Registry passes full name like "perplexity/sonar-deep-research";
        # Perplexity API expects the short form.
        api_model = model.removeprefix(_MODEL_PREFIX)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": api_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                *[{"role": m.role, "content": m.content} for m in messages],
            ],
        }

        t0 = time.monotonic()
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout_seconds
        ) as client:
            r = await client.post("/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        duration = time.monotonic() - t0

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return CallResult(
            text=choice["message"]["content"] or "",
            usage=CallUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            ),
            model=data.get("model", api_model),
            finish_reason=choice.get("finish_reason", "unknown"),
            duration_seconds=duration,
            citations=list(data.get("citations", [])),
        )
