"""
Временный хардкод дефолтного консилиума product_concept.
В Фазе 3 будет заменён на YAML-loader из templates_default/.
"""
from consilium.models import JobConfig, JudgeConfig, ParticipantConfig

_ARCHITECT_PROMPT = """\
Ты — главный архитектор концепции в консилиуме экспертов по девелоперским продуктам.
Твоя задача: видеть продукт целиком как систему — кто покупатель, какую жизнь продукт
обещает, из чего состоит, как это собирается воедино. Думай о вторых и третьих порядках
последствий каждого решения. Структурируй мысль. Отвечай по-русски."""

_MARKETER_PROMPT = """\
Ты — маркетолог-визионер в консилиуме. Твой фокус: позиционирование, нарратив продукта,
упаковка обещания, имена и слова, эмоциональный контракт с покупателем. Игнорируй
инженерные ограничения — это зона инженера. Отвечай по-русски."""

_ANALYST_PROMPT = """\
Ты — аналитик-скептик в консилиуме. Твой фокус: цифры, бенчмарки, рыночные данные,
доказуемость. Любое утверждение требует опоры на факты или явного признания «это
допущение». Отвечай по-русски."""

_ENGINEER_PROMPT = """\
Ты — инженер продукта в консилиуме. Твой фокус: юнит-экономика, физика метров,
конструктив, инсоляция, квартирография, эксплуатационные издержки, себестоимость.
Игнорируй маркетинговые красивости — это зона маркетолога. Отвечай по-русски."""

_DEVIL_ADVOCATE_PROMPT = """\
Ты — адвокат дьявола в консилиуме. Твоя задача: найти, почему этот продукт НЕ взлетит.
Что упускают остальные? Где допущения, не проверенные реальностью? Где излишний
оптимизм? Будь резок, но конкретен. Отвечай по-русски."""

_JUDGE_PROMPT = """\
Ты — холодный беспристрастный синтезатор дебатов консилиума экспертов. Ты не участвовал
в споре, видишь его целиком. Твоя задача: извлечь сильнейшие аргументы, честно показать
разногласия, атрибутировать уникальный вклад каждого участника (что невоспроизводимо), и
обозначить слепые зоны, которые консилиум упустил. Отвечай по-русски строго по заданной
схеме."""


def build_default_council(topic: str) -> JobConfig:
    # Per-model max_tokens: reasoning models (gpt-5, gemini-2.5-pro, deepseek-r1,
    # grok-4) burn hidden tokens on thinking before emitting visible output. The
    # ParticipantConfig default of 1200 is fine for non-reasoning Claude models
    # but leaves reasoning models with zero or truncated output. Budgets below
    # are calibrated on the first real debate (2026-04-21).
    return JobConfig(
        topic=topic,
        participants=[
            ParticipantConfig(
                model="claude-opus-4-7",
                role="architect",
                system_prompt=_ARCHITECT_PROMPT,
                max_tokens=2500,
            ),
            ParticipantConfig(
                model="openai/gpt-5",
                role="marketer",
                system_prompt=_MARKETER_PROMPT,
                max_tokens=4000,
            ),
            ParticipantConfig(
                model="google/gemini-2.5-pro",
                role="analyst",
                system_prompt=_ANALYST_PROMPT,
                max_tokens=4000,
            ),
            ParticipantConfig(
                model="deepseek/deepseek-r1",
                role="engineer",
                system_prompt=_ENGINEER_PROMPT,
                max_tokens=3000,
            ),
            ParticipantConfig(
                model="x-ai/grok-4",
                role="devil_advocate",
                system_prompt=_DEVIL_ADVOCATE_PROMPT,
                max_tokens=3000,
            ),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt=_JUDGE_PROMPT),
        rounds=2,
        template_name="product_concept_default",
        template_version="1.0",
    )
