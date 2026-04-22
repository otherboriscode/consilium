from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from consilium.providers.base import CallUsage

ErrorKind = Literal[
    "timeout",
    "http_4xx",
    "http_5xx",
    "network",
    "content_policy",
    "other",
    "empty_output",
    "truncated",
    "excluded_by_fit",
]


class ParticipantConfig(BaseModel):
    model: str
    role: str = Field(..., min_length=1, max_length=50)
    system_prompt: str = Field(..., min_length=1)
    deep: bool = False
    # Reasoning models (gpt-5, gemini-2.5-pro, deepseek-r1, grok-4) burn hidden
    # tokens on thinking before visible output. 2500 is a sane default for
    # non-reasoning Claude models; reasoning roles should be overridden per
    # participant (see default_council.py).
    max_tokens: int = Field(default=2500, ge=100, le=16_000)
    timeout_seconds: float = Field(default=300.0, ge=10, le=10_800)


class JudgeConfig(BaseModel):
    model: str
    system_prompt: str = Field(..., min_length=1)
    # Judge emits a structured markdown with 7 sections plus per-participant
    # attribution — 4000 is not enough in practice and leads to mid-section
    # truncation. 8000 is the safe floor.
    max_tokens: int = Field(default=8000, ge=500, le=16_000)
    timeout_seconds: float = Field(default=600.0, ge=10, le=10_800)


class JobConfig(BaseModel):
    topic: str = Field(..., min_length=1)
    participants: list[ParticipantConfig] = Field(..., min_length=1, max_length=10)
    judge: JudgeConfig
    rounds: int = Field(default=2, ge=1, le=4)
    template_name: str = "default"
    template_version: str = "1.0"
    # Optional user-supplied project tag. Used by the archive layer to group
    # runs in stats (`stats --by-project`). No validation — user decides the
    # grouping granularity.
    project: str | None = None
    # Optional shared context injected into each participant's system prompt.
    # None = no context. String = raw assembled context block (see
    # consilium.context.assembly.assemble_context_block).
    context_block: str | None = None

    @model_validator(mode="after")
    def _roles_unique(self) -> JobConfig:
        slugs = [p.role for p in self.participants]
        if len(slugs) != len(set(slugs)):
            raise ValueError(f"Duplicate role slugs in participants: {slugs}")
        return self


class RoundMessage(BaseModel):
    round_index: int = Field(..., ge=0, le=4)
    role_slug: str
    text: str | None
    error: ErrorKind | None = None
    usage: CallUsage
    duration_seconds: float
    cost_usd: float

    @model_validator(mode="after")
    def _valid_state(self) -> RoundMessage:
        # Valid states:
        #   - text present, no error (normal success)
        #   - no text, error present (failure: timeout, empty_output, http_*, ...)
        #   - text present AND error="truncated" (partial success — we keep
        #     whatever the model did emit before hitting max_tokens)
        if self.text is None and self.error is None:
            raise ValueError("RoundMessage must have text or error (or both)")
        return self

    model_config = {"arbitrary_types_allowed": True}


class JudgeOutput(BaseModel):
    raw_markdown: str
    tldr: str
    consensus: list[str]
    disagreements: list[str]
    unique_contributions: dict[str, str]
    blind_spots: list[str]
    recommendation: str
    scores: dict[str, int]

    @field_validator("scores")
    @classmethod
    def _clamp_scores(cls, v: dict[str, int]) -> dict[str, int]:
        import logging as _logging

        result: dict[str, int] = {}
        for role, score in v.items():
            clamped = max(0, min(3, score))
            if clamped != score:
                _logging.getLogger(__name__).warning(
                    "score %d for %r out of [0, 3], clamping to %d",
                    score,
                    role,
                    clamped,
                )
            result[role] = clamped
        return result


ProgressKind = Literal[
    "round_started",
    "participant_completed",
    "participant_failed",
    "round_completed",
    "judge_started",
    "judge_completed",
    "judge_failed",
]


class ProgressEvent(BaseModel):
    kind: ProgressKind
    round_index: int | None = None
    role_slug: str | None = None
    error: str | None = None


class JobResult(BaseModel):
    job_id: int
    config: JobConfig
    messages: list[RoundMessage]
    judge: JudgeOutput | None  # None if judge failed
    judge_truncated: bool = False  # True if judge hit max_tokens mid-output
    duration_seconds: float
    total_cost_usd: float
    cost_breakdown: dict[str, float]
    started_at: datetime
    completed_at: datetime

    model_config = {"arbitrary_types_allowed": True}
