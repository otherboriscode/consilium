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
