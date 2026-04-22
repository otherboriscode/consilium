"""
Context-fit decision per participant:

- "full"    — full context_block fits in the model's window with room for
              system prompt, output budget, and round overhead.
- "summary" — context doesn't fit, but a fixed-size auto-summary does.
- "exclude" — even the summary doesn't fit; the participant won't get context.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from consilium.model_specs import get_context_window
from consilium.models import ParticipantConfig

FitKind = Literal["full", "summary", "exclude"]

# Reserve this fraction of the window for round-growing artifacts
# (transcripts from previous rounds + user-message prompt).
_ROUND_OVERHEAD_RATIO = 0.10


@dataclass(frozen=True)
class FitDecision:
    kind: FitKind
    reason: str = ""
    summary_target_tokens: int | None = None


def compute_fit(
    *,
    participant: ParticipantConfig,
    context_tokens: int,
    system_prompt_tokens: int,
    summary_target_tokens: int = 30_000,
) -> FitDecision:
    """Return the fit decision for this participant and a given context size."""
    window = get_context_window(participant.model)
    overhead = int(window * _ROUND_OVERHEAD_RATIO)

    needed_full = (
        context_tokens + system_prompt_tokens + participant.max_tokens + overhead
    )
    if needed_full <= window:
        return FitDecision(kind="full")

    needed_summary = (
        summary_target_tokens + system_prompt_tokens + participant.max_tokens + overhead
    )
    if needed_summary <= window:
        return FitDecision(
            kind="summary",
            reason=(
                f"context {context_tokens} exceeds {window}; using "
                f"{summary_target_tokens}-token summary"
            ),
            summary_target_tokens=summary_target_tokens,
        )

    return FitDecision(
        kind="exclude",
        reason=(
            f"even {summary_target_tokens}-token summary doesn't fit {window}"
        ),
    )
