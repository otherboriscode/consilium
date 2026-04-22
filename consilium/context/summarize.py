"""
Auto-summarization of context for participants whose window can't fit the full
pack. Uses Haiku (cheap) with a target token budget.
"""
from __future__ import annotations

from consilium.providers.base import Message
from consilium.providers.registry import ProviderRegistry

_SUMMARY_SYSTEM_TEMPLATE = """\
Ты — сжиматель контекста для мульти-LLM консилиума. Получаешь корпус документов
с заголовками '# File: <имя>'. Возвращаешь СЖАТУЮ версию, где:
- каждый файл представлен своим заголовком '# File: <имя>'
- под ним — основные тезисы, ключевые цифры, определения, без воды
- сохраняется структурная логика документа
- целевой размер: {target_tokens} токенов ±10%
- если документ полностью незначим — укажи это явно: 'Нерелевантно для темы.'
Отвечай строго по-русски."""


async def summarize_context(
    *,
    full_text: str,
    target_tokens: int,
    registry: ProviderRegistry,
    summarizer_model: str = "claude-haiku-4-5",
) -> str:
    """Summarize `full_text` to approximately `target_tokens` tokens via Haiku."""
    provider = registry.get_provider(summarizer_model)
    result = await provider.call(
        model=summarizer_model,
        system=_SUMMARY_SYSTEM_TEMPLATE.format(target_tokens=target_tokens),
        messages=[Message(role="user", content=full_text)],
        max_tokens=int(target_tokens * 1.2),
    )
    return result.text
