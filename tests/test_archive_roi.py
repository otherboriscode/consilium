import pytest

from consilium.archive import Archive, ROIRow
from tests.test_archive_save import make_result


def test_roi_computes_cost_per_score_point(tmp_path):
    """Over 2 jobs Opus cost $0.030 total and earned score=4 (2+2)
    → $0.0075 per score point."""
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    for i in range(1, 3):
        archive.save_job(make_result(job_id=i))
    rows = archive.get_roi_stats()
    by = {r.model: r for r in rows}
    assert "claude-opus-4-7" in by
    assert by["claude-opus-4-7"].total_cost_usd == pytest.approx(0.030, rel=1e-3)
    assert by["claude-opus-4-7"].total_score == 4
    assert by["claude-opus-4-7"].cost_per_score == pytest.approx(0.0075, rel=1e-3)
    assert by["claude-opus-4-7"].n_jobs == 2


def test_roi_excludes_judge_only_models(tmp_path):
    """Haiku is the judge — no job_scores row for it — so it must be absent
    from the ROI output (it's not a participant)."""
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=1))
    rows = archive.get_roi_stats()
    models = {r.model for r in rows}
    assert "claude-haiku-4-5" not in models
    assert "claude-opus-4-7" in models


def test_roi_zero_score_yields_none_cost_per_score(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    r = make_result(job_id=1)
    new_judge = r.judge.model_copy(update={"scores": {"architect": 0}})
    r = r.model_copy(update={"judge": new_judge})
    archive.save_job(r)

    rows = archive.get_roi_stats()
    by = {r.model: r for r in rows}
    assert by["claude-opus-4-7"].total_score == 0
    assert by["claude-opus-4-7"].cost_per_score is None


def test_roi_returns_row_type(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=1))
    rows = archive.get_roi_stats()
    assert all(isinstance(r, ROIRow) for r in rows)


def test_roi_empty_archive(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    assert archive.get_roi_stats() == []
