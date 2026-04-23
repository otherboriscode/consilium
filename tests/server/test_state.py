import asyncio

import pytest

from consilium_server.api.models import ProgressEvent
from consilium_server.api.state import (
    ConcurrencyLimitExceeded,
    JobHandle,
    RateLimitExceeded,
    ServerState,
)


def _handle(job_id: int) -> JobHandle:
    return JobHandle(job_id=job_id, task=None)


def test_register_and_unregister():
    state = ServerState()
    h = _handle(1)
    state.register(h)
    assert state.get(1) is h
    assert 1 in state.active_ids()
    state.unregister(1)
    assert state.get(1) is None


def test_concurrency_limit_enforced():
    state = ServerState(max_concurrent=2, min_seconds_between=0)
    state.register(_handle(1))
    state.register(_handle(2))
    with pytest.raises(ConcurrencyLimitExceeded):
        state.register(_handle(3))


def test_rate_limit_between_jobs():
    # min_seconds_between=30s; unregistering "finishes" the job then we try too soon.
    state = ServerState(max_concurrent=5, min_seconds_between=30)
    state.register(_handle(1))
    state.unregister(1)
    with pytest.raises(RateLimitExceeded):
        state.register(_handle(2))


def test_rate_limit_ignored_when_min_is_zero():
    state = ServerState(max_concurrent=5, min_seconds_between=0)
    state.register(_handle(1))
    state.unregister(1)
    state.register(_handle(2))  # must not raise


@pytest.mark.asyncio
async def test_sse_publish_delivers_to_subscribers():
    state = ServerState(min_seconds_between=0)
    state.register(_handle(1))
    sub1 = state.subscribe_events(1)
    sub2 = state.subscribe_events(1)
    event = ProgressEvent(
        kind="round_started",
        round_index=0,
        message="R0",
        timestamp="now",
    )
    await state.publish_event(1, event)
    assert sub1.qsize() == 1
    assert sub2.qsize() == 1
    got = await sub1.get()
    assert got is not None and got.kind == "round_started"


@pytest.mark.asyncio
async def test_subscribers_get_sentinel_on_unregister():
    state = ServerState(min_seconds_between=0)
    state.register(_handle(1))
    sub = state.subscribe_events(1)
    state.unregister(1)
    # sentinel None signals stream end
    got = await asyncio.wait_for(sub.get(), timeout=0.1)
    assert got is None


@pytest.mark.asyncio
async def test_slow_subscriber_drops_events_not_blocks():
    state = ServerState(min_seconds_between=0)
    state.register(_handle(1))
    sub = state.subscribe_events(1)
    # Saturate queue (maxsize=100)
    event = ProgressEvent(kind="round_started", message="x", timestamp="t")
    for _ in range(120):
        await state.publish_event(1, event)
    # Queue caps at 100; overflow silently dropped.
    assert sub.qsize() == 100
