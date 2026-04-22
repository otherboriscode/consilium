import pytest

from consilium.archive import Archive, StatsRow
from tests.test_archive_save import make_result


def test_stats_by_model_sums_cost(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    for i in range(1, 4):
        archive.save_job(make_result(job_id=i))
    rows = archive.get_stats(group_by="model")
    assert all(isinstance(r, StatsRow) for r in rows)
    by = {r.key: r for r in rows}
    # make_result uses cost_breakdown={opus: 0.015, haiku: 0.005}
    assert by["claude-opus-4-7"].total_cost_usd == pytest.approx(0.045, rel=1e-3)
    assert by["claude-opus-4-7"].n_jobs == 3
    assert by["claude-haiku-4-5"].total_cost_usd == pytest.approx(0.015, rel=1e-3)
    assert by["claude-haiku-4-5"].n_jobs == 3


def test_stats_by_template(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=1))  # product_concept
    r = make_result(job_id=2)
    r = r.model_copy(
        update={"config": r.config.model_copy(update={"template_name": "quick_check"})}
    )
    archive.save_job(r)
    rows = archive.get_stats(group_by="template")
    by = {r.key: r for r in rows}
    assert by["product_concept"].n_jobs == 1
    assert by["quick_check"].n_jobs == 1


def test_stats_by_project_excludes_null(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=1, project="a"))
    archive.save_job(make_result(job_id=2, project=None))
    rows = archive.get_stats(group_by="project")
    assert all(r.key is not None for r in rows)
    by = {r.key: r for r in rows}
    assert "a" in by and by["a"].n_jobs == 1


def test_stats_rejects_unknown_group_by(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    with pytest.raises(ValueError):
        archive.get_stats(group_by="unknown")  # type: ignore[arg-type]


def test_stats_empty_archive(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    assert archive.get_stats(group_by="model") == []
    assert archive.get_stats(group_by="template") == []
    assert archive.get_stats(group_by="project") == []
