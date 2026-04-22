from consilium.archive import Archive, JobSummary
from tests.test_archive_save import make_result


def _save_multiple(
    archive: Archive,
    n: int,
    *,
    project: str | None = None,
    template: str = "product_concept",
) -> None:
    for i in range(1, n + 1):
        r = make_result(job_id=i, project=project)
        r = r.model_copy(
            update={"config": r.config.model_copy(update={"template_name": template})}
        )
        archive.save_job(r)


def test_list_jobs_returns_all_sorted_desc(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    _save_multiple(archive, 3)
    rows = archive.list_jobs()
    assert all(isinstance(r, JobSummary) for r in rows)
    assert [r.job_id for r in rows] == [3, 2, 1]


def test_list_jobs_filters_by_project(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    _save_multiple(archive, 2, project="a")
    archive.save_job(make_result(job_id=3, project="b"))
    rows = archive.list_jobs(project="a")
    assert {r.job_id for r in rows} == {1, 2}


def test_list_jobs_filters_by_template(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    _save_multiple(archive, 2, template="product_concept")
    r = make_result(job_id=3)
    r = r.model_copy(
        update={"config": r.config.model_copy(update={"template_name": "quick_check"})}
    )
    archive.save_job(r)
    rows = archive.list_jobs(template="quick_check")
    assert {r.job_id for r in rows} == {3}


def test_list_jobs_honors_limit(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    _save_multiple(archive, 10)
    rows = archive.list_jobs(limit=3)
    assert len(rows) == 3


def test_list_jobs_empty_archive(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    assert archive.list_jobs() == []
