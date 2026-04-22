import pytest

from consilium.archive import Archive
from consilium.models import JobResult
from tests.test_archive_save import make_result


def test_load_roundtrips_full_result(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    original = make_result(job_id=55, project="demo")
    archive.save_job(original)

    loaded = archive.load_job(55)
    assert isinstance(loaded, JobResult)
    assert loaded.job_id == 55
    assert loaded.config.topic == original.config.topic
    assert loaded.config.project == "demo"
    assert loaded.judge is not None
    assert loaded.judge.scores == original.judge.scores
    assert loaded.messages[0].text == "arch content"
    # JSON roundtrip preserves datetime too
    assert loaded.started_at == original.started_at


def test_load_missing_job_raises(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    with pytest.raises(KeyError, match="999"):
        archive.load_job(999)
