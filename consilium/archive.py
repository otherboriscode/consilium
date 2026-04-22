"""
Persistent debate archive.

Each saved job produces three artifacts on disk:

  $CONSILIUM_DATA_DIR/archive/
    archive.sqlite            # index for list/search/stats
    YYYY/MM/
      0001-<slug>.md          # full formatted markdown for humans
      0001-<slug>.json        # JobResult dump (source of truth)

SQLite is an index; the JSON files are the source of truth. If the DB is lost
it can be rebuilt from the JSON files by replaying save_job().
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "archive_schema.sql"


def _default_root() -> Path:
    base = Path(
        os.environ.get(
            "CONSILIUM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "consilium"),
        )
    )
    return base / "archive"


class Archive:
    """SQLite-backed debate archive.

    Safe to call `init_schema()` repeatedly — `CREATE ... IF NOT EXISTS` makes
    it idempotent.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "archive.sqlite"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_schema(self) -> None:
        schema = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)
            conn.commit()
