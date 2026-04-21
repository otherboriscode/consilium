from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import httpx

ErrorKind = Literal[
    "timeout", "http_4xx", "http_5xx", "network", "content_policy", "other"
]


class ProviderError(Exception):
    """Normalized provider failure. Raised by every BaseProvider on non-success."""

    def __init__(
        self,
        *,
        kind: ErrorKind,
        provider: str,
        model: str,
        status_code: int | None = None,
        message: str = "",
        original: Exception | None = None,
    ) -> None:
        self.kind = kind
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.message = message
        self.original = original
        super().__init__(f"{provider}:{model} failed ({kind}): {message}")


def wrap_http_error(
    exc: BaseException, *, provider: str, model: str
) -> ProviderError:
    """Map an httpx exception into a normalized ProviderError."""
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(
            kind="timeout",
            provider=provider,
            model=model,
            message=str(exc),
            original=exc,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        try:
            body = exc.response.json()
            err = body.get("error", {}) if isinstance(body, dict) else {}
        except ValueError:
            err = {}
        if err.get("type") == "content_policy":
            return ProviderError(
                kind="content_policy",
                provider=provider,
                model=model,
                status_code=status,
                message=err.get("message", str(exc)),
                original=exc,
            )
        kind: ErrorKind = "http_4xx" if 400 <= status < 500 else "http_5xx"
        return ProviderError(
            kind=kind,
            provider=provider,
            model=model,
            status_code=status,
            message=err.get("message", str(exc)),
            original=exc,
        )
    if isinstance(exc, httpx.NetworkError):
        return ProviderError(
            kind="network",
            provider=provider,
            model=model,
            message=str(exc),
            original=exc,
        )
    return ProviderError(
        kind="other",
        provider=provider,
        model=model,
        message=str(exc),
        original=exc,
    )


@dataclass
class CallUsage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0


@dataclass
class CallResult:
    text: str
    usage: CallUsage
    model: str
    finish_reason: str
    duration_seconds: float
    citations: list[str] = field(default_factory=list)


Role = Literal["system", "user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    name: str

    @abstractmethod
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
        """Execute a single LLM call. Raises on provider error."""
        ...
