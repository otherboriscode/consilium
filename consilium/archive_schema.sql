-- Consilium archive schema v1.
-- Source of truth for each job is its JSON file on disk. SQLite is the
-- index used by list/search/stats. If the DB is lost, it can be rebuilt
-- by replaying save_job() over the JSON files.

CREATE TABLE IF NOT EXISTS jobs (
    id               INTEGER PRIMARY KEY,
    job_id           INTEGER UNIQUE NOT NULL,
    topic            TEXT NOT NULL,
    project          TEXT,                   -- NULL if not supplied
    template_name    TEXT NOT NULL,
    template_version TEXT NOT NULL,
    rounds           INTEGER NOT NULL,
    started_at       TEXT NOT NULL,          -- ISO 8601 UTC
    completed_at     TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    total_cost_usd   REAL NOT NULL,
    judge_truncated  INTEGER NOT NULL DEFAULT 0,
    md_path          TEXT NOT NULL,          -- relative to archive root
    json_path        TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project);
CREATE INDEX IF NOT EXISTS idx_jobs_template ON jobs(template_name);

-- Cost per-model per-job (one row per model that appeared in cost_breakdown).
CREATE TABLE IF NOT EXISTS job_costs (
    id       INTEGER PRIMARY KEY,
    job_id   INTEGER NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    model    TEXT NOT NULL,
    cost_usd REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_costs_model ON job_costs(model);
CREATE INDEX IF NOT EXISTS idx_job_costs_job ON job_costs(job_id);

-- Judge scores per-role per-job. `model` is denormalized for fast ROI queries.
CREATE TABLE IF NOT EXISTS job_scores (
    id       INTEGER PRIMARY KEY,
    job_id   INTEGER NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    role     TEXT NOT NULL,
    model    TEXT NOT NULL,
    score    INTEGER NOT NULL  -- 0..3 (clamped on JudgeOutput creation)
);
CREATE INDEX IF NOT EXISTS idx_job_scores_model ON job_scores(model);
CREATE INDEX IF NOT EXISTS idx_job_scores_job ON job_scores(job_id);

-- External-content FTS5 for full-text search. Shadow table holds source text;
-- triggers keep the FTS index in sync on insert/delete.
CREATE TABLE IF NOT EXISTS jobs_fts_content (
    id             INTEGER PRIMARY KEY,
    job_id         INTEGER UNIQUE NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    topic          TEXT NOT NULL,
    project        TEXT,
    tldr           TEXT NOT NULL DEFAULT '',
    recommendation TEXT NOT NULL DEFAULT '',
    transcript     TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    topic, project, tldr, recommendation, transcript,
    content='jobs_fts_content', content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS jobs_fts_ai AFTER INSERT ON jobs_fts_content BEGIN
    INSERT INTO jobs_fts(rowid, topic, project, tldr, recommendation, transcript)
    VALUES (new.id, new.topic, COALESCE(new.project, ''), new.tldr, new.recommendation, new.transcript);
END;

CREATE TRIGGER IF NOT EXISTS jobs_fts_ad AFTER DELETE ON jobs_fts_content BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, topic, project, tldr, recommendation, transcript)
    VALUES ('delete', old.id, old.topic, COALESCE(old.project, ''), old.tldr, old.recommendation, old.transcript);
END;
