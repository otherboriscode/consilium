"""
In-memory server state: active jobs + SSE subscribers.

`ServerState` is a process-local singleton: one per running `uvicorn`
instance. If the process dies, active jobs are lost (by design — Archive
persists only completed debates). Concurrency and per-job rate-limits
keep the server from being dog-piled by a misbehaving client.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from consilium_server.api.models import JobStatus, ProgressEvent


class ConcurrencyLimitExceeded(Exception):
    """Too many in-flight jobs already."""


class RateLimitExceeded(Exception):
    """Submitted too soon after the previous job finished."""


@dataclass
class JobHandle:
    job_id: int
    task: asyncio.Task | None  # filled in immediately after create_task
    started_at: float = 0.0  # time.monotonic() at start
    started_at_iso: str = ""  # UTC ISO-8601 timestamp
    status: JobStatus = "running"
    rounds_total: int = 2
    rounds_completed: int = 0
    estimated_cost_usd: float = 0.0
    current_cost_usd: float = 0.0
    topic: str = ""
    template: str = ""
    project: str | None = None
    error: str | None = None
    completed_at_iso: str | None = None


class ServerState:
    """Process-local registry of in-flight jobs and SSE subscribers."""

    def __init__(
        self, *, max_concurrent: int = 3, min_seconds_between: int = 30
    ) -> None:
        self._jobs: dict[int, JobHandle] = {}
        self._subscribers: dict[int, list[asyncio.Queue[ProgressEvent | None]]] = {}
        self._last_finish_at: float = 0.0
        self._max_concurrent = max_concurrent
        self._min_seconds_between = min_seconds_between

    # --- registration -------------------------------------------------

    def register(self, job: JobHandle) -> None:
        if len(self._jobs) >= self._max_concurrent:
            raise ConcurrencyLimitExceeded(
                f"{len(self._jobs)} active jobs (limit {self._max_concurrent})"
            )
        elapsed = time.monotonic() - self._last_finish_at
        if (
            self._last_finish_at > 0
            and elapsed < self._min_seconds_between
        ):
            raise RateLimitExceeded(
                f"only {elapsed:.0f}s since last job "
                f"(min {self._min_seconds_between}s)"
            )
        self._jobs[job.job_id] = job
        self._subscribers.setdefault(job.job_id, [])

    def unregister(self, job_id: int) -> None:
        """Remove a job and notify SSE subscribers that the stream is done."""
        self._jobs.pop(job_id, None)
        for q in self._subscribers.pop(job_id, []):
            try:
                q.put_nowait(None)  # sentinel: stream end
            except asyncio.QueueFull:
                pass
        self._last_finish_at = time.monotonic()

    # --- queries ------------------------------------------------------

    def get(self, job_id: int) -> JobHandle | None:
        return self._jobs.get(job_id)

    def active_ids(self) -> list[int]:
        return list(self._jobs)

    def all_active(self) -> list[JobHandle]:
        return list(self._jobs.values())

    # --- SSE subscription --------------------------------------------

    def subscribe_events(
        self, job_id: int
    ) -> asyncio.Queue[ProgressEvent | None]:
        q: asyncio.Queue[ProgressEvent | None] = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    async def publish_event(self, job_id: int, event: ProgressEvent) -> None:
        for q in self._subscribers.get(job_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow subscriber — drop the event rather than stall the job.
                pass


# Process-local singleton (reset for tests via reset_state_for_tests).
_state: ServerState | None = None


def get_state() -> ServerState:
    global _state
    if _state is None:
        _state = ServerState()
    return _state


def reset_state_for_tests(**kwargs) -> None:
    """Drop and recreate the singleton. Test-only."""
    global _state
    _state = ServerState(**kwargs) if kwargs else None
