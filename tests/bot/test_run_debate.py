"""
Tests for `consilium_server.bot.handlers.run_debate._watch_job` — focused
on R3 from the Phase 8 review: ad-hoc packs created by the /new dialog
must be deleted after the debate finishes (success or failure).
"""
from __future__ import annotations

import pytest

from consilium_server.bot.handlers.run_debate import _watch_job


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.edited: list[tuple[int, int, str]] = []

    async def send_message(self, chat_id, text, **_kwargs):
        self.sent.append((chat_id, text))

    async def edit_message_text(
        self, text, chat_id, message_id, **_kwargs
    ):
        self.edited.append((chat_id, message_id, text))

    async def send_document(self, chat_id, document, **_kwargs):
        self.sent.append((chat_id, "(document)"))


class _FakeClient:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.deleted: list[str] = []
        self.archive_md = "# TL;DR\nshort\n\n# Next\nmore"
        self.raise_archive: Exception | None = None

    async def stream_events(self, job_id):
        for ev in self.events:
            yield ev

    async def get_archive_md(self, job_id):
        if self.raise_archive is not None:
            raise self.raise_archive
        return self.archive_md

    async def delete_pack(self, name):
        self.deleted.append(name)


@pytest.fixture
def bot():
    return _FakeBot()


@pytest.fixture
def client():
    return _FakeClient()


async def test_adhoc_pack_is_deleted_after_successful_delivery(bot, client):
    """R3 — happy path: pack named adhoc-… is deleted after `done`."""
    client.events = [{"kind": "done", "message": "ok"}]
    await _watch_job(
        bot=bot,
        client=client,
        job_id=42,
        chat_id=999,
        status_message_id=1,
        pack_name="adhoc-12345-67",
    )
    assert "adhoc-12345-67" in client.deleted


async def test_adhoc_pack_is_deleted_after_error_event(bot, client):
    """R3 — error path: pack still gets cleaned up."""
    client.events = [{"kind": "error", "message": "provider went away"}]
    await _watch_job(
        bot=bot,
        client=client,
        job_id=42,
        chat_id=999,
        status_message_id=1,
        pack_name="adhoc-12345-67",
    )
    assert "adhoc-12345-67" in client.deleted


async def test_adhoc_pack_is_deleted_when_archive_fetch_fails(bot, client):
    """R3 — if the fallback archive fetch raises, finally still cleans up."""
    client.events = []  # stream ends immediately, falls back to archive
    client.raise_archive = RuntimeError("archive missing")
    await _watch_job(
        bot=bot,
        client=client,
        job_id=42,
        chat_id=999,
        status_message_id=1,
        pack_name="adhoc-12345-67",
    )
    assert "adhoc-12345-67" in client.deleted


async def test_named_pack_is_NOT_deleted(bot, client):
    """Only `adhoc-…` packs are ephemeral; named packs (`tanaa`, `ubud`)
    are user-managed and must not be auto-deleted."""
    client.events = [{"kind": "done", "message": "ok"}]
    await _watch_job(
        bot=bot,
        client=client,
        job_id=42,
        chat_id=999,
        status_message_id=1,
        pack_name="tanaa",
    )
    assert client.deleted == []


async def test_no_pack_no_cleanup(bot, client):
    """When the user ran without context, pack_name is None — no delete."""
    client.events = [{"kind": "done", "message": "ok"}]
    await _watch_job(
        bot=bot,
        client=client,
        job_id=42,
        chat_id=999,
        status_message_id=1,
        pack_name=None,
    )
    assert client.deleted == []


async def test_delete_pack_failure_does_not_crash_watch(bot, client):
    """Cleanup is best-effort — a delete_pack exception is logged but
    swallowed."""
    client.events = [{"kind": "done", "message": "ok"}]

    async def _fail_delete(name):
        raise RuntimeError("network gone")

    client.delete_pack = _fail_delete  # type: ignore[method-assign]
    # Should not raise
    await _watch_job(
        bot=bot,
        client=client,
        job_id=42,
        chat_id=999,
        status_message_id=1,
        pack_name="adhoc-x-1",
    )
