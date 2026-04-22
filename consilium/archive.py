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


@dataclass(frozen=True)
class JobSummary:
    """Lightweight summary for list views — no JSON loaded from disk."""

    job_id: int
    topic: str
    project: str | None
    template_name: str
    template_version: str
    rounds: int
    started_at: str  # ISO 8601
    duration_seconds: float
    total_cost_usd: float
    judge_truncated: bool


def _row_to_summary(row: sqlite3.Row) -> JobSummary:
    return JobSummary(
        job_id=row["job_id"],
        topic=row["topic"],
        project=row["project"],
        template_name=row["template_name"],
        template_version=row["template_version"],
        rounds=row["rounds"],
        started_at=row["started_at"],
        duration_seconds=row["duration_seconds"],
        total_cost_usd=row["total_cost_usd"],
        judge_truncated=bool(row["judge_truncated"]),
    )


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

    def list_jobs(
        self,
        *,
        limit: int = 50,
        project: str | None = None,
        template: str | None = None,
    ) -> list[JobSummary]:
        """Latest jobs first (by `created_at`). Optional filters by project
        and/or template. Uses SQLite only — no JSON reads."""
        sql = ["SELECT * FROM jobs WHERE 1=1"]
        params: list[object] = []
        if project is not None:
            sql.append("AND project = ?")
            params.append(project)
        if template is not None:
            sql.append("AND template_name = ?")
            params.append(template)
        sql.append("ORDER BY created_at DESC, job_id DESC LIMIT ?")
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_summary(r) for r in rows]

    def search(self, query: str, *, limit: int = 20) -> list[JobSummary]:
        """Full-text search across topic/project/tldr/recommendation/transcript.
        Ranked by BM25, newest ties first.

        Note: the tokenizer is `unicode61` — it handles Cyrillic but does not
        stem Russian morphology. Use prefix matching (`концепц*`) if you need
        to catch declensions.
        """
        q = query.strip()
        if not q:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT j.* FROM jobs j
                JOIN jobs_fts_content c ON c.job_id = j.job_id
                JOIN jobs_fts f ON f.rowid = c.id
                WHERE jobs_fts MATCH ?
                ORDER BY bm25(jobs_fts), j.created_at DESC
                LIMIT ?
                """,
                (q, limit),
            ).fetchall()
        return [_row_to_summary(r) for r in rows]

    def load_job(self, job_id: int) -> JobResult:
        """Rehydrate a JobResult from its JSON file. JSON is the source of truth —
        SQLite only stores the pointer. Raises KeyError if `job_id` unknown."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT json_path FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"job {job_id} not found in archive")
        json_path = self.root / row["json_path"]
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return JobResult.model_validate(data)
