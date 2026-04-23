"""Inline-keyboard factories used across handlers."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Curated order that mirrors the home-grown YAML templates. Hard-coded (rather
# than fetched from API at every /new) because these are stable identifiers.
TEMPLATES = [
    "product_concept",
    "positioning",
    "pricing_strategy",
    "unit_economics",
    "brand_check",
    "quick_check",
    "book_chapter_review",
]


def template_keyboard(templates: list[str] = TEMPLATES) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t, callback_data=f"tpl:{t}")]
        for t in templates
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def context_choice_keyboard(packs: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Без контекста", callback_data="ctx:none")],
    ]
    for name in packs:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📎 {name}",
                    callback_data=f"ctx:pack:{name}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="📤 Загружу файлы", callback_data="ctx:upload"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶ Запустить", callback_data="confirm:run"),
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="confirm:cancel"
                ),
            ]
        ]
    )


def force_or_cancel_keyboard() -> InlineKeyboardMarkup:
    """Shown when cost guard denied but soft-caps can be bypassed with --force."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚠️ Всё равно запустить", callback_data="confirm:force"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:cancel"),
            ]
        ]
    )


def files_done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="files:done")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="files:cancel")],
        ]
    )
