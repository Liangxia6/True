-- trueeval.state.v1
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_uri TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    cancelled INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_runs (
    execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    repeat_index INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT,
    external_job_id TEXT,
    deadline TEXT,
    last_error_json TEXT,
    input_uri TEXT,
    output_uri TEXT,
    raw_result_uri TEXT,
    answer_uri TEXT,
    session_id TEXT,
    created_at TEXT NOT NULL,
    submitted_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (run_id, task_id, repeat_index),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    external_job_id TEXT,
    channel TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    request_uri TEXT,
    response_uri TEXT,
    lookup_available INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (execution_id) REFERENCES task_runs(execution_id)
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (execution_id, attempt_index),
    FOREIGN KEY (execution_id) REFERENCES task_runs(execution_id)
);

CREATE TABLE IF NOT EXISTS grading_jobs (
    grading_job_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    grader_id TEXT NOT NULL,
    grader_version TEXT NOT NULL,
    status TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (execution_id) REFERENCES task_runs(execution_id)
);

CREATE TABLE IF NOT EXISTS score_records (
    score_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    grading_job_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    repeat_index INTEGER NOT NULL,
    grader_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (grading_job_id) REFERENCES grading_jobs(grading_job_id)
);

CREATE TABLE IF NOT EXISTS budget_ledger (
    reservation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    reserved_usd REAL NOT NULL,
    actual_usd REAL,
    released INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    settled_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS outbox_events (
    run_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    projected INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, event_sequence)
);

CREATE INDEX IF NOT EXISTS idx_task_runs_run_status ON task_runs(run_id, status);
CREATE INDEX IF NOT EXISTS idx_outbox_unprojected ON outbox_events(run_id, projected, event_sequence);
CREATE INDEX IF NOT EXISTS idx_submissions_idem ON submissions(idempotency_key);
