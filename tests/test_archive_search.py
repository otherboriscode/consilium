from consilium.archive import Archive
from tests.test_archive_save import make_result


def _with_topic(r, topic):
    return r.model_copy(update={"config": r.config.model_copy(update={"topic": topic})})


def test_search_by_topic_returns_match(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(
        _with_topic(make_result(job_id=1), "Концепция проекта в Убуде")
    )
    archive.save_job(
        _with_topic(make_result(job_id=2), "Ценовая стратегия для коливинга")
    )

    rows = archive.search("Убуде")
    assert [r.job_id for r in rows] == [1]


def test_search_prefix_matches_declensions(tmp_path):
    """unicode61 не стеммит — full word matches only. Prefix * обходит."""
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(_with_topic(make_result(job_id=1), "Концепция"))
    assert len(archive.search("Концепция")) == 1
    # Full declension like "Концепции" won't match without *
    assert len(archive.search("Концепц*")) == 1


def test_search_matches_tldr_and_recommendation(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    r = make_result(job_id=7)
    # mutate a deep copy's judge
    new_judge = r.judge.model_copy(update={"tldr": "UNIQUETLDRMARKER и другие слова"})
    r = r.model_copy(update={"judge": new_judge})
    archive.save_job(r)
    rows = archive.search("UNIQUETLDRMARKER")
    assert [rr.job_id for rr in rows] == [7]


def test_search_empty_returns_empty(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    assert archive.search("") == []
    assert archive.search("   ") == []


def test_search_no_match_returns_empty(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.save_job(make_result(job_id=1))
    assert archive.search("никогдатакогонебылослова") == []


def test_search_limit(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    for i in range(1, 6):
        archive.save_job(_with_topic(make_result(job_id=i), "commonword"))
    rows = archive.search("commonword", limit=3)
    assert len(rows) == 3
