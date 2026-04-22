from datetime import datetime, timedelta, timezone

from consilium.archive import Archive
from consilium.daily_summary import build_daily_summary
from consilium.limits import DEFAULT_LIMITS
from tests.test_archive_save import make_result


def _job_at(job_id: int, when: datetime, **overrides):
    r = make_result(job_id=job_id)
    r = r.model_copy(
        update={
            "started_at": when,
            "completed_at": when + timedelta(seconds=5),
            **overrides,
        }
    )
    return r


def test_daily_summary_empty_archive(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    text = build_daily_summary(archive=archive, limits=DEFAULT_LIMITS, now=now)
    assert "нет активности" in text.lower()


def test_daily_summary_formats_yesterday_activity(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today_start - timedelta(hours=3)  # 21 April
    archive.save_job(_job_at(1, yesterday))
    archive.save_job(_job_at(2, yesterday))
    archive.save_job(_job_at(3, today_start + timedelta(hours=1)))  # today

    text = build_daily_summary(archive=archive, limits=DEFAULT_LIMITS, now=now)
    assert "📊 Вчера:" in text
    # 2 yesterday; pluralized "2 дискуссии"
    assert "2 дискуссии" in text
    assert "📈 Месяц:" in text
    assert "claude-opus-4-7" in text  # top cost source in make_result


def test_daily_summary_flags_truncated_runs(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    yesterday = now - timedelta(hours=10)
    archive.save_job(_job_at(1, yesterday, judge_truncated=True))
    archive.save_job(_job_at(2, yesterday))

    text = build_daily_summary(archive=archive, limits=DEFAULT_LIMITS, now=now)
    assert "обрезан" in text.lower()
    assert "#0001" in text


def test_daily_summary_uses_limits_percent(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    now = datetime(2026, 4, 22, 9, 0, tzinfo=timezone.utc)
    yesterday = now - timedelta(hours=10)
    archive.save_job(_job_at(1, yesterday))  # cost $0.02

    text = build_daily_summary(archive=archive, limits=DEFAULT_LIMITS, now=now)
    # $0.02 / $300 = 0%, formatted as 0
    assert "(0%)" in text
