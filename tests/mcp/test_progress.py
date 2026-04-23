"""
Tests for MCP progress notifications.

The progress_fn callback is injected by `server.call_tool`. Here we
call the `consilium_wait` handler directly with a recording progress
function and check it emits the right bumps.
"""
from __future__ import annotations

import pytest

from consilium_client import ClientConfig, JobStatus
from consilium_mcp.server import build_server


class _FakeClient:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.md = "# TL;DR\nshort\n\n# Next\nx"
        self.rounds_total = 2

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def get_status(self, job_id):
        return JobStatus(
            job_id=job_id,
            status="running",
            rounds_completed=0,
            rounds_total=self.rounds_total,
            current_cost_usd=0.0,
            estimated_cost_usd=1.0,
            template="quick_check",
            topic="topic",
            project=None,
            error=None,
        )

    async def stream_events(self, job_id):
        for ev in self.events:
            yield ev

    async def get_archive_md(self, job_id):
        return self.md

    async def delete_pack(self, name):
        pass


@pytest.fixture
def fake_config():
    return ClientConfig(api_base="http://x", token="t", timeout_seconds=5)


@pytest.fixture
def fake_client():
    return _FakeClient()


@pytest.fixture
def wrapper(fake_config, fake_client):
    return build_server(
        config=fake_config, client_factory=lambda: fake_client
    )


async def test_wait_reports_progress_for_rounds(wrapper, fake_client, tmp_path):
    fake_client.rounds_total = 2
    fake_client.events = [
        {"kind": "round_started", "round_index": 0},
        {"kind": "participant_completed", "role_slug": "a", "round_index": 0},
        {"kind": "round_completed", "round_index": 0},
        {"kind": "round_completed", "round_index": 1},
        {"kind": "judge_started"},
        {"kind": "done", "message": "ok"},
    ]
    emitted: list[tuple[float, float | None, str]] = []

    async def _progress(progress, total, message):
        emitted.append((progress, total, message))

    spec = wrapper.registry.get("consilium_wait")
    await spec.handler(
        {"job_id": 1, "save_to": str(tmp_path / "x.md")},
        progress=_progress,
    )
    # At least: two round_completed bumps, one judge_started, one terminal.
    # All with total=100.
    assert any(p == 100 for p, _, _ in emitted)
    assert all(t == 100 for _, t, _ in emitted)
    # round_completed → "Раунд N завершён"
    assert any("Раунд" in m for _, _, m in emitted)
    # terminal event
    assert any("Готово" in m or "Ошибка" in m for _, _, m in emitted)


async def test_wait_without_progress_callback_still_works(
    wrapper, fake_client, tmp_path
):
    """Handler should accept progress=None without blowing up — that's the
    default when no client-side progressToken is sent."""
    fake_client.events = [{"kind": "done", "message": "ok"}]
    spec = wrapper.registry.get("consilium_wait")
    result = await spec.handler(
        {"job_id": 1, "save_to": str(tmp_path / "x.md")}
    )
    assert "md_path" in result


async def test_wait_swallows_progress_errors(wrapper, fake_client, tmp_path):
    """Progress is best-effort: a raising callback must not fail the tool."""
    fake_client.events = [
        {"kind": "round_completed", "round_index": 0},
        {"kind": "done", "message": "ok"},
    ]

    async def _bad_progress(progress, total, message):
        raise RuntimeError("fake failure in progress")

    spec = wrapper.registry.get("consilium_wait")
    result = await spec.handler(
        {"job_id": 1, "save_to": str(tmp_path / "x.md")},
        progress=_bad_progress,
    )
    assert "md_path" in result
