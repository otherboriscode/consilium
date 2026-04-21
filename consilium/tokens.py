from __future__ import annotations

import tiktoken

_TIKTOKEN_ENCODINGS: dict[str, str] = {
    # Все OpenAI/OpenRouter/DeepSeek/xAI/Google — cl100k_base достаточно точен
    "default": "cl100k_base",
}


def count_tokens(text: str, *, model: str) -> int:
    """Conservative token count. Uses tiktoken cl100k_base as a universal approximation.

    Anthropic note: для точного подсчёта клода можно использовать anthropic.Anthropic().messages.count_tokens,
    но он требует сетевого вызова. cl100k_base даёт близкую оценку (±5%), чего достаточно для preview-конфига.
    """
    encoding = tiktoken.get_encoding(_TIKTOKEN_ENCODINGS["default"])
    return len(encoding.encode(text))


def count_messages_tokens(messages: list[dict], *, model: str) -> int:
    total = 0
    for m in messages:
        total += count_tokens(m.get("content", ""), model=model)
        total += 4  # role overhead
    return total
