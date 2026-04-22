from consilium.context.fit import FitDecision, compute_fit
from consilium.models import ParticipantConfig


def _p(model: str, max_tokens: int = 3500) -> ParticipantConfig:
    return ParticipantConfig(
        model=model,
        role="r",
        system_prompt="s",
        max_tokens=max_tokens,
    )


def test_fit_full_when_context_fits_comfortably():
    # Opus 4.7 has 1M window — 50K context fits with loads of room.
    decision = compute_fit(
        participant=_p("claude-opus-4-7"),
        context_tokens=50_000,
        system_prompt_tokens=1000,
    )
    assert decision.kind == "full"


def test_fit_exclude_when_even_summary_doesnt_fit():
    # Deepseek-r1 128K window. If the requested summary budget is too big,
    # exclude kicks in.
    decision = compute_fit(
        participant=_p("deepseek/deepseek-r1"),
        context_tokens=200_000,
        system_prompt_tokens=1000,
        summary_target_tokens=120_000,  # intentionally too big to fit after overhead
    )
    assert decision.kind == "exclude"
    assert decision.reason


def test_fit_summary_when_context_overflows_but_summary_fits():
    # Deepseek-r1 128K. 150K context overflows; default 30K summary fits.
    decision = compute_fit(
        participant=_p("deepseek/deepseek-r1"),
        context_tokens=150_000,
        system_prompt_tokens=1000,
        summary_target_tokens=30_000,
    )
    assert decision.kind == "summary"
    assert decision.summary_target_tokens == 30_000


def test_fit_decision_is_frozen():
    decision = compute_fit(
        participant=_p("claude-opus-4-7"),
        context_tokens=10_000,
        system_prompt_tokens=1_000,
    )
    assert isinstance(decision, FitDecision)
    # frozen dataclass — assignment raises
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.kind = "exclude"  # type: ignore[misc]
