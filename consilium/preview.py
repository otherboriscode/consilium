"""
Preview перед запуском дискуссии: участники, режимы, fit-per-participant,
оценка стоимости и длительности. Показывается пользователю в CLI/Telegram до
подтверждения запуска.

Стоимость считается по fit-решению:
- full: полный context_block × rounds идёт в input
- summary: вместо полного — summary_target, плюс один вызов Haiku на каждый
  уникальный summary_target (кешируется в оркестраторе)
- exclude: стоимость участника = 0
"""
from __future__ import annotations

from dataclasses import dataclass

from consilium.context.fit import compute_fit
from consilium.cost import estimate_cost
from consilium.models import JobConfig
from consilium.tokens import count_tokens

_SUMMARIZER_MODEL = "claude-haiku-4-5"


@dataclass
class PreviewInfo:
    text: str
    estimated_cost_usd: float
    estimated_duration_seconds: float


def build_preview(
    config: JobConfig,
    *,
    context_block: str | None = None,
) -> PreviewInfo:
    """Render a human-readable preview with a fit-aware cost estimate."""
    ctx_tokens = count_tokens(context_block) if context_block else 0

    lines: list[str] = []
    topic_preview = (
        config.topic if len(config.topic) <= 80 else config.topic[:77] + "..."
    )
    lines.append(f"🎯 Тема: {topic_preview}")
    lines.append(f"📋 Шаблон: {config.template_name}")
    if context_block:
        lines.append(f"📎 Контекст: {ctx_tokens:,} токенов")
    lines.append("")
    lines.append("Состав консилиума:")

    total_cost = 0.0
    unique_summary_targets: set[int] = set()

    for p in config.participants:
        fit_str = ""
        effective_ctx_tokens = ctx_tokens
        is_excluded = False

        if context_block:
            decision = compute_fit(
                participant=p,
                context_tokens=ctx_tokens,
                system_prompt_tokens=count_tokens(p.system_prompt),
            )
            if decision.kind == "full":
                fit_str = " [fit: full]"
            elif decision.kind == "summary":
                target = decision.summary_target_tokens or 30_000
                unique_summary_targets.add(target)
                effective_ctx_tokens = target
                fit_str = f" [fit: summary {target // 1000}K]"
            else:  # exclude
                is_excluded = True
                fit_str = " [fit: EXCLUDED]"
                effective_ctx_tokens = 0

        mode = "🧠Deep" if p.deep else "⚡Fast"
        if is_excluded:
            cost = 0.0
        else:
            sp_tok = count_tokens(p.system_prompt)
            cost = estimate_cost(
                model=p.model,
                input_tokens=(effective_ctx_tokens + sp_tok) * config.rounds,
                output_tokens=p.max_tokens * config.rounds,
            )
        total_cost += cost
        lines.append(
            f"  ✅ {p.role:18} {p.model:32} {mode}{fit_str}  ~${cost:.2f}"
        )

    # Judge
    judge_cost = estimate_cost(
        model=config.judge.model,
        input_tokens=20_000,  # rough transcript estimate
        output_tokens=config.judge.max_tokens,
    )
    total_cost += judge_cost
    lines.append(f"  ⚖️  Судья: {config.judge.model:30}   ~${judge_cost:.2f}")

    # Haiku compression: one call per unique summary target, shared across
    # participants that need it (mirrors orchestrator.summary_cache).
    if unique_summary_targets:
        summary_cost = 0.0
        for target in unique_summary_targets:
            summary_cost += estimate_cost(
                model=_SUMMARIZER_MODEL,
                input_tokens=ctx_tokens,
                output_tokens=int(target * 1.2),
            )
        total_cost += summary_cost
        buckets = len(unique_summary_targets)
        lines.append(
            f"  📦 Сжатие контекста (Haiku × {buckets} "
            f"{'бакет' if buckets == 1 else 'бакета'}): ~${summary_cost:.3f}"
        )

    # Rough duration estimate.
    duration_s = 60 + config.rounds * 45 + 30
    lines.append("")
    lines.append(f"⏱  Оценка времени: ~{duration_s // 60} мин")
    lines.append(f"💰 Оценка стоимости: ${total_cost:.2f}")

    return PreviewInfo(
        text="\n".join(lines),
        estimated_cost_usd=total_cost,
        estimated_duration_seconds=float(duration_s),
    )
