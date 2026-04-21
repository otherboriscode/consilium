from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


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
