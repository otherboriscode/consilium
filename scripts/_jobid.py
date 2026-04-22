"""
File-locked counter for sequential job IDs. Lives under CONSILIUM_DATA_DIR
(same root as packs) so a single machine can run multiple CLI invocations
without stomping on each other's IDs.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path


def _counter_path() -> Path:
    base = Path(
        os.environ.get(
            "CONSILIUM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "consilium"),
        )
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / "next_job_id.txt"


def next_job_id() -> int:
    """Atomically increment and return the next job id (starts at 1)."""
    path = _counter_path()
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read().strip()
            current = int(raw) if raw else 0
            next_id = current + 1
            f.seek(0)
            f.truncate()
            f.write(str(next_id))
            f.flush()
            os.fsync(f.fileno())
            return next_id
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
