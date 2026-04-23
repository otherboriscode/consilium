"""
API request/response models.

Intentionally separate from `consilium.models` — those are internal; these
are the over-the-wire contract with clients (Telegram bot / MCP / anything
else). Changes here are breaking for clients; changes in internal models
aren't.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

JobStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled"
]

ProgressKind = Literal[
    "round_started",
    "participant_completed",
    "participant_failed",
    "round_completed",
    "judge_started",
    "judge_completed",
    "judge_failed",
    "done",
    "error",
]


class SubmitJobRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=4000)
    template: str = Field(default="product_concept", min_length=1)
    context_block: str | None = None
    pack: str | None = None  # named context pack
    rounds: int | None = Field(default=None, ge=1, le=4)
    project: str | None = None
    force: bool = False  # bypass soft-caps (not hard-stop)

    @model_validator(mode="after")
    def _context_xor_pack(self) -> SubmitJobRequest:
        if self.context_block is not None and self.pack is not None:
            raise ValueError(
                "Specify either `pack` or `context_block`, not both"
            )
        return self


class SubmitJobResponse(BaseModel):
    job_id: int
    status: Literal["queued", "running"]
    estimated_cost_usd: float
    estimated_duration_seconds: float
    warnings: list[str] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: int
    status: JobStatus
    rounds_completed: int
    rounds_total: int
    started_at: str
    completed_at: str | None = None
    estimated_cost_usd: float
    current_cost_usd: float
    template: str
    project: str | None = None
    topic: str = ""
    error: str | None = None


class ProgressEvent(BaseModel):
    kind: ProgressKind
    round_index: int | None = None
    role_slug: str | None = None
    message: str
    timestamp: str


class JobListItem(BaseModel):
    job_id: int
    status: JobStatus
    topic: str
    template: str
    project: str | None = None
    started_at: str
    cost_usd: float
    duration_seconds: float | None = None


class ParticipantPreview(BaseModel):
    """Per-participant preview row — used by the Telegram bot to render the
    'hey, here's what will run' confirmation."""

    role: str
    model: str
    mode: Literal["fast", "deep"]
    fit: Literal["full", "summary", "exclude"]
    estimated_cost_usd: float = 0.0  # per-participant split is follow-up work


class PreviewJobResponse(BaseModel):
    """Dry-run response: same pre-flight as POST /jobs, but nothing is
    scheduled and cost-cap violations come back as body fields instead of
    402 — the client (bot FSM) decides whether to show `force` or cancel."""

    estimated_cost_usd: float
    estimated_duration_seconds: float
    context_tokens: int
    template: str
    rounds: int
    participants: list[ParticipantPreview]
    judge_model: str
    allowed: bool
    violations: list[str] = Field(default_factory=list)
    violation_messages: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
