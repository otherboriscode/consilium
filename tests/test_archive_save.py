import json as _json
from datetime import datetime, timezone

from consilium.archive import Archive
from consilium.models import (
    JobConfig,
    JobResult,
    JudgeConfig,
    JudgeOutput,
    ParticipantConfig,
    RoundMessage,
)
from consilium.providers.base import CallUsage


def make_result(job_id: int = 1, project: str | None = None) -> JobResult:
    """Shared fixture factory used by archive tests."""
    cfg = JobConfig(
        topic="Test topic",
        participants=[
            ParticipantConfig(
                model="claude-opus-4-7", role="architect", system_prompt="s"
            ),
        ],
        judge=JudgeConfig(model="claude-haiku-4-5", system_prompt="j"),
        rounds=1,
        template_name="product_concept",
        template_version="abc123",
        project=project,
    )
    msg = RoundMessage(
        round_index=0,
        role_slug="architect",
        text="arch content",
        error=None,
        usage=CallUsage(input_tokens=100, output_tokens=50),
        duration_seconds=1.0,
        cost_usd=0.015,
    )
    judge = JudgeOutput(
        raw_markdown="# TL;DR\nSynth.",
        tldr="Synth.",
        consensus=["c1"],
        disagreements=["d1"],
        unique_contributions={"architect": "space"},
        blind_spots=["b"],
        recommendation="ship",
        scores={"architect": 2},
    )
    return JobResult(
        job_id=job_id,
        config=cfg,
        messages=[msg],
        judge=judge,
        judge_truncated=False,
        duration_seconds=5.0,
        total_cost_usd=0.020,
        cost_breakdown={"claude-opus-4-7": 0.015, "claude-haiku-4-5": 0.005},
        started_at=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 22, 10, 0, 5, tzinfo=timezone.utc),
    )


def test_save_writes_all_three_artifacts(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    saved = archive.save_job(make_result(job_id=1))

    md_path = tmp_path / "arch" / "2026" / "04" / saved.md_path.name
    json_path = tmp_path / "arch" / "2026" / "04" / saved.json_path.name
    assert md_path.is_file()
    assert json_path.is_file()

    md = md_path.read_text(encoding="utf-8")
    assert "Test topic" in md
    assert "Synth." in md

    data = _json.loads(json_path.read_text(encoding="utf-8"))
    assert data["job_id"] == 1
    assert data["config"]["topic"] == "Test topic"

    with archive._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM job_costs").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM job_scores").fetchone()[0] == 1


def test_save_populates_fts(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=42))

    with archive._connect() as conn:
        row = conn.execute(
            "SELECT topic, tldr, recommendation "
            "FROM jobs_fts_content WHERE job_id = 42"
        ).fetchone()
    assert row["topic"] == "Test topic"
    assert row["tldr"] == "Synth."
    assert row["recommendation"] == "ship"


def test_save_is_idempotent_on_same_job_id(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=7))
    archive.save_job(make_result(job_id=7))
    with archive._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM job_costs").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM job_scores").fetchone()[0] == 1


def test_save_handles_null_judge(tmp_path):
    result = make_result(job_id=3).model_copy(update={"judge": None})
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    saved = archive.save_job(result)
    assert saved.md_path.is_file()
    with archive._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM job_scores").fetchone()[0] == 0
        row = conn.execute(
            "SELECT tldr, recommendation FROM jobs_fts_content WHERE job_id = 3"
        ).fetchone()
        assert row["tldr"] == ""
        assert row["recommendation"] == ""


def test_save_handles_project_field(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=9, project="tanaa-ubud"))
    with archive._connect() as conn:
        row = conn.execute("SELECT project FROM jobs WHERE job_id = 9").fetchone()
    assert row["project"] == "tanaa-ubud"


def test_save_year_month_folder_structure(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    saved = archive.save_job(make_result(job_id=1))
    # started_at is 2026-04-22 → 2026/04/
    assert saved.md_path.parent.parent.name == "2026"
    assert saved.md_path.parent.name == "04"
