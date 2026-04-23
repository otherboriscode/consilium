import pytest

from consilium_server.api.models import (
    JobListItem,
    JobStatusResponse,
    ProgressEvent,
    SubmitJobRequest,
    SubmitJobResponse,
)


def test_submit_request_accepts_minimal_payload():
    req = SubmitJobRequest(topic="test", template="quick_check")
    assert req.topic == "test"
    assert req.template == "quick_check"
    assert req.context_block is None
    assert req.pack is None
    assert req.rounds is None
    assert req.force is False


def test_submit_request_validates_mutually_exclusive_context():
    with pytest.raises(ValueError, match="pack"):
        SubmitJobRequest(
            topic="t",
            template="quick_check",
            context_block="...",
            pack="tanaa",
        )


def test_submit_request_rejects_empty_topic():
    with pytest.raises(ValueError):
        SubmitJobRequest(topic="", template="quick_check")


def test_submit_response_shape():
    r = SubmitJobResponse(
        job_id=42,
        status="running",
        estimated_cost_usd=0.50,
        estimated_duration_seconds=120.0,
    )
    assert r.warnings == []


def test_job_status_response_shape():
    r = JobStatusResponse(
        job_id=42,
        status="running",
        rounds_completed=1,
        rounds_total=2,
        started_at="2026-04-23T10:00:00+00:00",
        estimated_cost_usd=0.50,
        current_cost_usd=0.18,
        template="quick_check",
    )
    assert r.status == "running"
    assert r.completed_at is None


def test_job_status_response_accepts_completed_fields():
    r = JobStatusResponse(
        job_id=1,
        status="completed",
        rounds_completed=2,
        rounds_total=2,
        started_at="2026-04-23T10:00:00+00:00",
        completed_at="2026-04-23T10:05:00+00:00",
        estimated_cost_usd=0.5,
        current_cost_usd=0.48,
        template="quick_check",
        topic="тема",
    )
    assert r.status == "completed"


def test_progress_event_serializable():
    e = ProgressEvent(
        kind="round_completed",
        round_index=0,
        message="Round 0 done (5/5)",
        timestamp="2026-04-23T10:01:30+00:00",
    )
    data = e.model_dump(mode="json")
    assert data["kind"] == "round_completed"
    assert data["round_index"] == 0


def test_job_list_item_shape():
    item = JobListItem(
        job_id=5,
        status="completed",
        topic="тема",
        template="product_concept",
        started_at="2026-04-23T10:00:00+00:00",
        cost_usd=0.73,
    )
    assert item.duration_seconds is None
