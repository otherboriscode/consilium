"""
Preview перед запуском дискуссии: участники, режимы, fit-per-participant,
оценка стоимости и длительности. Показывается пользователю в CLI/Telegram до
подтверждения запуска.
"""
from __future__ import annotations

from dataclasses import dataclass

from consilium.context.fit import compute_fit
from consilium.cost import estimate_cost
from consilium.models import JobConfig
from consilium.tokens import count_tokens


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
    """Render a human-readable preview with a rough cost + duration estimate."""
    ctx_tokens = count_tokens(context_block) if context_block else 0

    lines: list[str] = []
    topic_preview = config.topic if len(config.topic) <= 80 else config.topic[:77] + "..."
    lines.append(f"🎯 Тема: {topic_preview}")
    lines.append(f"📋 Шаблон: {config.template_name}")
    if context_block:
        lines.append(f"📎 Контекст: {ctx_tokens:,} токенов")
    lines.append("")
    lines.append("Состав консилиума:")

    total_cost = 0.0
    for p in config.participants:
        fit_str = ""
        if context_block:
            decision = compute_fit(
                participant=p,
                context_tokens=ctx_tokens,
                system_prompt_tokens=count_tokens(p.system_prompt),
            )
            fit_str = f" [fit: {decision.kind}]"

        mode = "🧠Deep" if p.deep else "⚡Fast"
        sp_tok = count_tokens(p.system_prompt)
        cost = estimate_cost(
            model=p.model,
            input_tokens=(ctx_tokens + sp_tok) * config.rounds,
            output_tokens=p.max_tokens * config.rounds,
        )
        total_cost += cost
        lines.append(
            f"  ✅ {p.role:18} {p.model:32} {mode}{fit_str}  ~${cost:.2f}"
        )

    judge_cost = estimate_cost(
        model=config.judge.model,
        input_tokens=20_000,  # rough transcript estimate
        output_tokens=config.judge.max_tokens,
    )
    total_cost += judge_cost
    lines.append(f"  ⚖️  Судья: {config.judge.model:30}   ~${judge_cost:.2f}")

    # Rough duration: base + per-round + judge synthesis.
    duration_s = 60 + config.rounds * 45 + 30
    lines.append("")
    lines.append(f"⏱  Оценка времени: ~{duration_s // 60} мин")
    lines.append(f"💰 Оценка стоимости: ${total_cost:.2f}")

    return PreviewInfo(
        text="\n".join(lines),
        estimated_cost_usd=total_cost,
        estimated_duration_seconds=float(duration_s),
    )
