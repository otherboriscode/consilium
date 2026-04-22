"""
Сборка стенограммы дискуссии.

`build_transcript_for_next_round` — markdown-блок для передачи в следующий раунд.
`format_full_markdown` — финальный файл в архив с YAML-frontmatter.
"""
from __future__ import annotations

from itertools import groupby

import yaml

from consilium.models import JobResult, RoundMessage


def build_transcript_for_next_round(messages: list[RoundMessage]) -> str:
    """Сгруппированный по раундам markdown для следующего раунда или судьи."""
    if not messages:
        return ""

    # messages already arrive in (round_index, participant_order) — сохраняем.
    parts: list[str] = []
    for round_index, group in groupby(messages, key=lambda m: m.round_index):
        parts.append(f"# Раунд {round_index}\n")
        for m in group:
            parts.append(f"## {m.role_slug}\n")
            if m.text is not None:
                parts.append(m.text.rstrip() + "\n")
            else:
                parts.append(f"_[не ответил: {m.error}]_\n")
            parts.append("")  # blank line between participants
    return "\n".join(parts).rstrip() + "\n"


def format_full_markdown(result: JobResult) -> str:
    """Полный архивный файл с YAML-frontmatter."""
    frontmatter: dict = {
        "job_id": result.job_id,
        "topic": result.config.topic,
        "template_name": result.config.template_name,
        "template_version": result.config.template_version,
        "rounds": result.config.rounds,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "duration_seconds": round(result.duration_seconds, 2),
        "cost_usd": round(result.total_cost_usd, 4),
        "cost_breakdown": {k: round(v, 4) for k, v in result.cost_breakdown.items()},
        "participants": [
            {"role": p.role, "model": p.model} for p in result.config.participants
        ],
        "judge_model": result.config.judge.model,
    }
    yaml_block = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip()
    # Ensure `cost_usd: 0.15` is present literally (yaml outputs `0.15` unquoted) —
    # tests match on substring. safe_dump handles this naturally.

    body_parts = [
        f"---\n{yaml_block}\n---",
        f"# Тема\n\n{result.config.topic}",
        build_transcript_for_next_round(result.messages).rstrip(),
    ]

    if result.judge is not None:
        synthesis_parts = ["# Синтез"]
        if result.judge_truncated:
            synthesis_parts.append(
                "> ⚠️ Синтез судьи обрезан по лимиту токенов. "
                "Увеличьте `judge.max_tokens`."
            )
        synthesis_parts.append(result.judge.raw_markdown.rstrip())
        body_parts.append("\n\n".join(synthesis_parts))
    else:
        body_parts.append("# Синтез\n\n_[судья не ответил]_")

    return "\n\n".join(body_parts) + "\n"
