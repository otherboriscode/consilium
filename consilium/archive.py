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
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from consilium.models import JobResult
from consilium.transcript import format_full_markdown

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "archive_schema.sql"

# Any of these in a user query triggers FTS5 parser (phrase/prefix/operator).
# `*` is intentionally NOT here — it's a valid and supported prefix wildcard.
_FTS_PARSER_TRIGGERS = frozenset('"():+')


def _escape_fts_query(query: str) -> str:
    """Sanitize a user query for FTS5 `MATCH`.

    - Empty/whitespace → empty (caller should return [] without querying).
    - If the query contains FTS5 special syntax (quotes, parens, operators),
      wrap the whole thing in a phrase match with inner `"` escaped.
    - Plain words and prefix queries (`kitty*`) pass through unchanged so users
      keep access to the useful bits of FTS5 syntax.
    """
    q = query.strip()
    if not q:
        return q
    if any(c in q for c in _FTS_PARSER_TRIGGERS):
        return '"' + q.replace('"', '""') + '"'
    return q

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


StatsGroupBy = Literal["model", "template", "project"]


@dataclass(frozen=True)
class StatsRow:
    key: str | None  # None only possible for group_by="project" with NULL projects
    n_jobs: int
    total_cost_usd: float


@dataclass(frozen=True)
class ROIRow:
    """$ spent on a model divided by total score points the judge gave it.
    `cost_per_score` is None when total_score is 0 (avoids div-by-zero and
    correctly flags that the model earned nothing per judge)."""

    model: str
    total_cost_usd: float
    total_score: int
    n_jobs: int
    cost_per_score: float | None


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

    def __init__(self, root: Path | None = None, *, auto_init: bool = True) -> None:
        self.root = root or _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "archive.sqlite"
        if auto_init:
            self.init_schema()

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
        """Persist `result` as md + json files and SQLite rows atomically.

        Ordering:
          1. Prepare content in memory (no disk writes yet)
          2. Commit SQL transaction (index becomes source of truth for paths)
          3. Write files via `.tmp` + `os.replace` (atomic rename on POSIX)
          4. If step 3 fails, roll back the SQL row so no orphan index entry survives

        Idempotent on the same `job_id`: re-running replaces row + files in place.
        """
        yyyy = result.started_at.strftime("%Y")
        mm = result.started_at.strftime("%m")
        folder = self.root / yyyy / mm
        folder.mkdir(parents=True, exist_ok=True)
        slug = _slugify(result.config.topic)
        md_path = folder / f"{result.job_id:04d}-{slug}.md"
        json_path = folder / f"{result.job_id:04d}-{slug}.json"
        tmp_md = md_path.with_suffix(md_path.suffix + ".tmp")
        tmp_json = json_path.with_suffix(json_path.suffix + ".tmp")

        # 1. Build content. Raises before we touch disk or SQL.
        md_content = format_full_markdown(result)
        json_content = json.dumps(
            result.model_dump(mode="json"), ensure_ascii=False, indent=2
        )

        transcript_text = "\n\n".join(
            (m.text or "") for m in result.messages if m.text
        )
        judge = result.judge
        tldr = judge.tldr if judge else ""
        recommendation = judge.recommendation if judge else ""
        role_to_model = {p.role: p.model for p in result.config.participants}

        # 2. SQL first — if FTS insert or anything else blows up, we haven't
        #    touched the filesystem yet, so no orphan files are left behind.
        with self._connect() as conn:
            try:
                # Cascades to job_costs, job_scores, jobs_fts_content via
                # ON DELETE CASCADE; FTS5 index is updated by trigger.
                conn.execute(
                    "DELETE FROM jobs WHERE job_id = ?", (result.job_id,)
                )
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
                        "INSERT INTO job_costs (job_id, model, cost_usd) "
                        "VALUES (?, ?, ?)",
                        (result.job_id, model, cost),
                    )
                if judge is not None:
                    for role, score in judge.scores.items():
                        role_model = role_to_model.get(role)
                        if role_model is None:
                            continue  # judge named a role not in config
                        conn.execute(
                            "INSERT INTO job_scores (job_id, role, model, score) "
                            "VALUES (?, ?, ?, ?)",
                            (result.job_id, role, role_model, score),
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
            except Exception:
                conn.rollback()
                raise

        # 3. Write files via tmp + rename. If this throws, roll the SQL back.
        try:
            tmp_md.write_text(md_content, encoding="utf-8")
            os.replace(tmp_md, md_path)
            tmp_json.write_text(json_content, encoding="utf-8")
            os.replace(tmp_json, json_path)
        except Exception:
            # 4. Rollback: drop the SQL row so index stays consistent.
            try:
                with self._connect() as conn:
                    conn.execute(
                        "DELETE FROM jobs WHERE job_id = ?", (result.job_id,)
                    )
                    conn.commit()
            except sqlite3.Error:
                # Best-effort rollback; if even this fails, the original
                # exception from the file write is more informative.
                pass
            for p in (tmp_md, tmp_json):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

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

    def get_stats(self, *, group_by: StatsGroupBy) -> list[StatsRow]:
        """Aggregated counts and total cost.

        - group_by="model":    joins via job_costs; one row per model touched.
        - group_by="template": one row per template_name.
        - group_by="project":  one row per non-NULL project (NULL is dropped).
        """
        if group_by == "model":
            sql = """
                SELECT jc.model AS key,
                       COUNT(DISTINCT jc.job_id) AS n_jobs,
                       SUM(jc.cost_usd) AS total_cost
                FROM job_costs jc
                GROUP BY jc.model
                ORDER BY total_cost DESC
            """
        elif group_by == "template":
            sql = """
                SELECT template_name AS key,
                       COUNT(*) AS n_jobs,
                       SUM(total_cost_usd) AS total_cost
                FROM jobs
                GROUP BY template_name
                ORDER BY total_cost DESC
            """
        elif group_by == "project":
            sql = """
                SELECT project AS key,
                       COUNT(*) AS n_jobs,
                       SUM(total_cost_usd) AS total_cost
                FROM jobs
                WHERE project IS NOT NULL
                GROUP BY project
                ORDER BY total_cost DESC
            """
        else:
            raise ValueError(f"group_by must be model/template/project, got {group_by!r}")
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [
            StatsRow(
                key=r["key"],
                n_jobs=r["n_jobs"],
                total_cost_usd=r["total_cost"] or 0.0,
            )
            for r in rows
        ]

    def get_roi_stats(self) -> list[ROIRow]:
        """ROI per participant model: cost spent ÷ judge score points earned.

        Judge-only models (Haiku as synthesizer) are excluded — they are not
        in `job_scores`. We aggregate per-job first to avoid row multiplication
        when a model plays multiple roles (unlikely today, but safe).
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT jc.model AS model,
                       SUM(jc.cost_usd) AS total_cost,
                       COALESCE(
                           (SELECT SUM(score) FROM job_scores
                            WHERE model = jc.model),
                           0
                       ) AS total_score,
                       COUNT(DISTINCT jc.job_id) AS n_jobs
                FROM job_costs jc
                WHERE jc.model IN (SELECT DISTINCT model FROM job_scores)
                GROUP BY jc.model
                ORDER BY total_cost DESC
                """
            ).fetchall()
        result: list[ROIRow] = []
        for r in rows:
            total_score = int(r["total_score"])
            total_cost = r["total_cost"] or 0.0
            cps = (total_cost / total_score) if total_score > 0 else None
            result.append(
                ROIRow(
                    model=r["model"],
                    total_cost_usd=total_cost,
                    total_score=total_score,
                    n_jobs=r["n_jobs"],
                    cost_per_score=cps,
                )
            )
        return result

    def search(self, query: str, *, limit: int = 20) -> list[JobSummary]:
        """Full-text search across topic/project/tldr/recommendation/transcript.
        Ranked by BM25, newest ties first.

        Special characters in `query` (quotes, parens, +, :) are escaped by
        wrapping the whole query in a phrase match so malformed FTS5 syntax
        can't crash the call. Prefix wildcards (`концепц*`) pass through
        unchanged. Unrecoverable FTS5 parse errors are logged and return [].

        Note: the tokenizer is `unicode61` — it handles Cyrillic but does not
        stem Russian morphology. Use prefix matching (`концепц*`) if you need
        to catch declensions.
        """
        q = _escape_fts_query(query)
        if not q:
            return []
        try:
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
        except sqlite3.OperationalError as e:
            logger.warning("FTS5 query %r failed: %s", query, e)
            return []
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
