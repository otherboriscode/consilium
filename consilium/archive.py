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

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from consilium.models import JobResult
from consilium.transcript import format_full_markdown

_SCHEMA_PATH = Path(__file__).parent / "archive_schema.sql"

# Keep cyrillic + latin alphanumerics; collapse everything else to dashes.
_SLUG_RE = re.compile(r"[^a-z0-9а-я]+", re.IGNORECASE)


def _slugify(topic: str, *, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", topic.lower()).strip("-")
    return slug[:max_len] or "debate"


@dataclass(frozen=True)
class SavedJob:
    job_id: int
    md_path: Path
    json_path: Path


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

    def save_job(self, result: JobResult) -> SavedJob:
        """Persist `result` as md + json files and SQLite rows. Idempotent on
        the same `job_id`: re-running replaces the row and files in place."""
        yyyy = result.started_at.strftime("%Y")
        mm = result.started_at.strftime("%m")
        folder = self.root / yyyy / mm
        folder.mkdir(parents=True, exist_ok=True)
        slug = _slugify(result.config.topic)
        md_path = folder / f"{result.job_id:04d}-{slug}.md"
        json_path = folder / f"{result.job_id:04d}-{slug}.json"

        md_path.write_text(format_full_markdown(result), encoding="utf-8")
        json_path.write_text(
            json.dumps(
                result.model_dump(mode="json"), ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

        transcript_text = "\n\n".join(
            (m.text or "") for m in result.messages if m.text
        )

        judge = result.judge
        tldr = judge.tldr if judge else ""
        recommendation = judge.recommendation if judge else ""

        role_to_model = {p.role: p.model for p in result.config.participants}

        with self._connect() as conn:
            # Full replace — cascades to job_costs, job_scores, jobs_fts_content
            # via FK ON DELETE CASCADE, and FTS index via trigger.
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (result.job_id,))
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, topic, project, template_name, template_version,
                    rounds, started_at, completed_at, duration_seconds,
                    total_cost_usd, judge_truncated, md_path, json_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.job_id,
                    result.config.topic,
                    result.config.project,
                    result.config.template_name,
                    result.config.template_version,
                    result.config.rounds,
                    result.started_at.isoformat(),
                    result.completed_at.isoformat(),
                    result.duration_seconds,
                    result.total_cost_usd,
                    int(result.judge_truncated),
                    str(md_path.relative_to(self.root)),
                    str(json_path.relative_to(self.root)),
                ),
            )
            for model, cost in result.cost_breakdown.items():
                conn.execute(
                    "INSERT INTO job_costs (job_id, model, cost_usd) VALUES (?, ?, ?)",
                    (result.job_id, model, cost),
                )
            if judge is not None:
                for role, score in judge.scores.items():
                    model = role_to_model.get(role)
                    if model is None:
                        continue  # orphan score: judge named a role not in config
                    conn.execute(
                        "INSERT INTO job_scores (job_id, role, model, score) VALUES (?, ?, ?, ?)",
                        (result.job_id, role, model, score),
                    )
            conn.execute(
                """
                INSERT INTO jobs_fts_content
                    (job_id, topic, project, tldr, recommendation, transcript)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.job_id,
                    result.config.topic,
                    result.config.project,
                    tldr,
                    recommendation,
                    transcript_text,
                ),
            )
            conn.commit()

        return SavedJob(job_id=result.job_id, md_path=md_path, json_path=json_path)
