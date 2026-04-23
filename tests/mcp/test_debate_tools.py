"""
Tests for MCP debate lifecycle tools.

Uses an in-memory fake ConsiliumClient that the server hands tool
handlers via the client_factory injection point. This avoids hitting
the real API and lets us assert on exact argument plumbing.
"""
from __future__ import annotations

import pytest

from consilium_client import (
    ClientConfig,
    CostDenied,
    JobNotFound,
    JobStatus,
    ParticipantPreviewRow,
    PreviewResult,
    SubmitResult,
)
from consilium_mcp.server import build_server


class _FakeClient:
    """Stand-in for ConsiliumClient used by MCP tool handlers.

    Records calls so tests can assert on how tools translate arguments.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.packs_created: list[tuple[str, list]] = []
        self.packs_deleted: list[str] = []
        self.preview_return: PreviewResult | None = None
        self.submit_return: SubmitResult | None = None
        self.raise_cost_denied = False
        self._stream_events: list[dict] = []
        self.archive_md = "# TL;DR\nshort summary\n\n# Next\nmore"
        self.status_return: JobStatus | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def preview_job(self, **kwargs):
        self.calls.append(("preview_job", kwargs))
        return self.preview_return or PreviewResult(
            estimated_cost_usd=1.5,
            estimated_duration_seconds=90,
            context_tokens=123,
            template=kwargs.get("template", "quick_check"),
            rounds=kwargs.get("rounds") or 2,
            participants=[
                ParticipantPreviewRow(
                    role="architect",
                    model="claude-sonnet-4.5",
                    mode="deep",
                    fit="full",
                    estimated_cost_usd=0.0,
                )
            ],
            judge_model="claude-haiku-4.5",
            allowed=True,
            violations=[],
            violation_messages=[],
            warnings=[],
        )

    async def submit_job(self, **kwargs):
        self.calls.append(("submit_job", kwargs))
        if self.raise_cost_denied:
            raise CostDenied(
                violations=["per_job_cap_exceeded"],
                messages=["too expensive"],
                estimate=100.0,
            )
        return self.submit_return or SubmitResult(
            job_id=42,
            status="running",
            estimated_cost_usd=1.5,
            estimated_duration_seconds=90,
            warnings=[],
        )

    async def create_pack(self, name, files):
        self.packs_created.append((name, list(files)))
        return {"name": name, "files": [f[0] for f in files], "total_tokens": 10}

    async def delete_pack(self, name):
        self.packs_deleted.append(name)

    async def cancel_job(self, job_id):
        self.calls.append(("cancel_job", {"job_id": job_id}))

    async def get_status(self, job_id):
        if getattr(self, "raise_status_not_found", False):
            raise JobNotFound(f"Job {job_id} not found")
        return self.status_return or JobStatus(
            job_id=job_id,
            status="completed",
            rounds_completed=2,
            rounds_total=2,
            current_cost_usd=1.45,
            estimated_cost_usd=1.5,
            template="quick_check",
            topic="test topic",
            project=None,
            error=None,
        )

    async def stream_events(self, job_id):
        for ev in self._stream_events:
            yield ev

    async def get_archive_md(self, job_id):
        return self.archive_md


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


def test_all_debate_tools_registered(wrapper):
    names = {t.name for t in wrapper.registry.tools}
    assert {
        "consilium_preview",
        "consilium_start",
        "consilium_status",
        "consilium_wait",
        "consilium_cancel",
    }.issubset(names)


async def test_preview_tool_returns_shape(wrapper, fake_client):
    spec = wrapper.registry.get("consilium_preview")
    result = await spec.handler({"topic": "t", "template": "quick_check"})
    assert result["allowed"] is True
    assert result["estimated_cost_usd"] == 1.5
    assert result["participants"][0]["role"] == "architect"


async def test_preview_uploads_and_cleans_ephemeral_pack(
    wrapper, fake_client, tmp_path
):
    brief = tmp_path / "b.md"
    brief.write_text("ctx")
    spec = wrapper.registry.get("consilium_preview")
    await spec.handler({"topic": "t", "context_files": [str(brief)]})
    assert len(fake_client.packs_created) == 1
    # Preview cleans up immediately after use
    assert len(fake_client.packs_deleted) == 1
    assert fake_client.packs_created[0][0] == fake_client.packs_deleted[0]


async def test_start_tool_returns_job_id(wrapper, fake_client):
    spec = wrapper.registry.get("consilium_start")
    result = await spec.handler({"topic": "t", "template": "quick_check"})
    assert result["job_id"] == 42
    assert result["status"] == "running"
    assert result["ephemeral_pack"] is None


async def test_start_with_context_files_keeps_pack_for_wait(
    wrapper, fake_client, tmp_path
):
    brief = tmp_path / "b.md"
    brief.write_text("ctx")
    spec = wrapper.registry.get("consilium_start")
    result = await spec.handler(
        {"topic": "t", "context_files": [str(brief)]}
    )
    # Pack created, but NOT deleted yet — _wait will clean up.
    assert len(fake_client.packs_created) == 1
    assert len(fake_client.packs_deleted) == 0
    assert result["ephemeral_pack"].startswith("_eph_")


async def test_start_cost_denied_returns_error_dict(wrapper, fake_client):
    fake_client.raise_cost_denied = True
    spec = wrapper.registry.get("consilium_start")
    result = await spec.handler({"topic": "t"})
    assert result["error"] == "cost_denied"
    assert "per_job_cap_exceeded" in result["violations"]


async def test_status_tool(wrapper, fake_client):
    spec = wrapper.registry.get("consilium_status")
    result = await spec.handler({"job_id": 42})
    assert result["job_id"] == 42
    assert result["status"] == "completed"


async def test_cancel_tool(wrapper, fake_client):
    spec = wrapper.registry.get("consilium_cancel")
    result = await spec.handler({"job_id": 42})
    assert result == {"cancelled": True, "job_id": 42}
    assert fake_client.calls[-1] == ("cancel_job", {"job_id": 42})


async def test_wait_saves_markdown_and_returns_tldr(
    wrapper, fake_client, tmp_path
):
    fake_client._stream_events = [
        {"kind": "round_started", "round_index": 0},
        {"kind": "done", "message": "ok"},
    ]
    spec = wrapper.registry.get("consilium_wait")
    result = await spec.handler(
        {"job_id": 42, "save_to": str(tmp_path / "out.md")}
    )
    assert result["md_path"] == str(tmp_path / "out.md")
    assert "short summary" in result["tldr"]
    assert (tmp_path / "out.md").exists()


async def test_wait_cleans_up_ephemeral_pack(wrapper, fake_client, tmp_path):
    fake_client._stream_events = [{"kind": "done", "message": "ok"}]
    spec = wrapper.registry.get("consilium_wait")
    await spec.handler(
        {
            "job_id": 42,
            "save_to": str(tmp_path / "out.md"),
            "ephemeral_pack": "_eph_1234",
        }
    )
    assert "_eph_1234" in fake_client.packs_deleted


async def test_wait_error_returns_failure_dict(wrapper, fake_client, tmp_path):
    fake_client._stream_events = [
        {"kind": "error", "message": "provider blew up"}
    ]
    spec = wrapper.registry.get("consilium_wait")
    result = await spec.handler({"job_id": 42, "save_to": str(tmp_path / "x.md")})
    assert result["error"] == "job_failed"
    assert "provider blew up" in result["message"]


async def test_wait_handles_job_not_found_without_unbound_local(
    wrapper, fake_client, tmp_path
):
    """R1 regression — when get_status raises JobNotFound after the
    stream completes, the final return must not crash with
    UnboundLocalError on `status` (Phase 8 review fix)."""
    fake_client._stream_events = [{"kind": "done", "message": "ok"}]
    fake_client.raise_status_not_found = True
    spec = wrapper.registry.get("consilium_wait")
    result = await spec.handler(
        {"job_id": 42, "save_to": str(tmp_path / "out.md")}
    )
    # Should reach the happy path and return md_path; cost_usd is None
    # because we couldn't fetch status.
    assert result["md_path"] == str(tmp_path / "out.md")
    assert result["cost_usd"] is None
