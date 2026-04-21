from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from consilium.providers.base import CallUsage

ErrorKind = Literal[
    "timeout", "http_4xx", "http_5xx", "network", "content_policy", "other"
]


class ParticipantConfig(BaseModel):
    model: str
    role: str = Field(..., min_length=1, max_length=50)
    system_prompt: str = Field(..., min_length=1)
    deep: bool = False
    max_tokens: int = Field(default=1200, ge=100, le=16_000)
    timeout_seconds: float = Field(default=300.0, ge=10, le=10_800)


class JudgeConfig(BaseModel):
    model: str
    system_prompt: str = Field(..., min_length=1)
    max_tokens: int = Field(default=4000, ge=500, le=16_000)
    timeout_seconds: float = Field(default=600.0, ge=10, le=10_800)


class JobConfig(BaseModel):
    topic: str = Field(..., min_length=1)
    participants: list[ParticipantConfig] = Field(..., min_length=1, max_length=10)
    judge: JudgeConfig
    rounds: int = Field(default=2, ge=1, le=4)
    template_name: str = "default"
    template_version: str = "1.0"

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
    def _text_xor_error(self) -> RoundMessage:
        if (self.text is None) == (self.error is None):
            raise ValueError("RoundMessage must have exactly one of text or error")
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
    duration_seconds: float
    total_cost_usd: float
    cost_breakdown: dict[str, float]
    started_at: datetime
    completed_at: datetime

    model_config = {"arbitrary_types_allowed": True}
