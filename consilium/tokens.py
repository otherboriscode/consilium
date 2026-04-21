from __future__ import annotations

import tiktoken


def count_tokens(text: str) -> int:
    """Conservative token count via tiktoken cl100k_base — a universal approximation
    accurate within ±5% for all providers used in Consilium. Good enough for
    preview-config and budget estimates; exact accounting uses API-reported usage.
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))
