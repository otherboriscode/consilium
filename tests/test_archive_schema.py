import sqlite3

from consilium.archive import Archive


def test_fts5_is_available_in_sqlite():
    """Required: stdlib sqlite3 must ship with FTS5. Fails loudly if the Python
    build is missing it, so we catch the environment issue early."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
    finally:
        conn.close()


def test_archive_init_creates_all_tables(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    with archive._connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "jobs" in names
    assert "job_costs" in names
    assert "job_scores" in names
    assert "jobs_fts_content" in names
    assert "jobs_fts" in names


def test_archive_init_is_idempotent(tmp_path):
    archive = Archive(root=tmp_path / "arch")
    archive.init_schema()
    archive.init_schema()  # must not raise on re-run
    # Sanity: trivial insert succeeds.
    with archive._connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, topic, template_name, template_version,
                              rounds, started_at, completed_at, duration_seconds,
                              total_cost_usd, md_path, json_path)
            VALUES (1, 't', 'tpl', 'v', 1, '2026-04-22', '2026-04-22',
                    1.0, 0.1, 'p.md', 'p.json')
            """
        )
        conn.commit()
        cnt = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert cnt == 1


def test_archive_root_is_created_if_missing(tmp_path):
    root = tmp_path / "does" / "not" / "exist"
    assert not root.exists()
    Archive(root=root)  # constructor must mkdir
    assert root.is_dir()
