import { randomUUID } from "node:crypto";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

import type { ArtifactRef, JudgeJob, ScoreRecord } from "../../schemas/contracts.js";
import { assertTransition, type CaseState } from "../state/case-state.js";

export interface RunRow {
  run_id: string;
  status: string;
  manifest_uri: string;
  manifest_sha256: string;
  created_at: string;
  updated_at: string;
}

export interface CaseRow {
  case_id: string;
  run_id: string;
  task_id: string;
  sut_id: string;
  status: CaseState;
  ordinal: number;
  current_attempt_id: string | null;
  updated_at: string;
}

export interface AttemptRow {
  attempt_id: string;
  case_id: string;
  attempt_number: number;
  status: string;
  submitted_at: string | null;
  completed_at: string | null;
  result_uri: string | null;
  error_code: string | null;
}

export class StateDatabase {
  private readonly database: DatabaseSync;

  constructor(readonly filePath: string) {
    const absolute = path.resolve(filePath);
    mkdirSync(path.dirname(absolute), { recursive: true });
    this.database = new DatabaseSync(absolute);
    this.database.exec("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;");
    this.migrate();
  }

  close(): void {
    this.database.close();
  }

  private migrate(): void {
    this.database.exec(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        manifest_uri TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        sut_id TEXT NOT NULL,
        status TEXT NOT NULL,
        ordinal INTEGER NOT NULL,
        current_attempt_id TEXT,
        lease_owner TEXT,
        lease_expires_at TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(run_id, task_id, sut_id),
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
      );
      CREATE TABLE IF NOT EXISTS attempts (
        attempt_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        status TEXT NOT NULL,
        external_session_id TEXT,
        submitted_at TEXT,
        completed_at TEXT,
        result_uri TEXT,
        error_code TEXT,
        UNIQUE(case_id, attempt_number),
        FOREIGN KEY(case_id) REFERENCES cases(case_id)
      );
      CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        case_id TEXT,
        attempt_id TEXT,
        seq INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(run_id, case_id, attempt_id, seq)
      );
      CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        case_id TEXT,
        attempt_id TEXT,
        kind TEXT NOT NULL,
        uri TEXT NOT NULL,
        media_type TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS scores (
        score_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL,
        metric_id TEXT NOT NULL,
        grader_id TEXT NOT NULL,
        grader_version TEXT NOT NULL,
        status TEXT NOT NULL,
        value_json TEXT,
        record_uri TEXT NOT NULL,
        UNIQUE(attempt_id, metric_id, grader_id, grader_version)
      );
      CREATE TABLE IF NOT EXISTS judge_jobs (
        judge_job_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        case_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL,
        grader_id TEXT NOT NULL,
        grader_version TEXT NOT NULL,
        purpose TEXT NOT NULL,
        profile_hash TEXT NOT NULL,
        cache_key TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence REAL,
        cache_source_job_id TEXT,
        job_uri TEXT NOT NULL,
        verdict_uri TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_judge_jobs_cache ON judge_jobs(cache_key, status);
      INSERT OR IGNORE INTO schema_migrations(version, applied_at)
      VALUES (1, datetime('now'));
    `);
  }

  createRun(runId: string, manifestUri: string, manifestSha256: string): void {
    const now = new Date().toISOString();
    this.database
      .prepare(`INSERT INTO runs(run_id, status, manifest_uri, manifest_sha256, created_at, updated_at)
        VALUES (?, 'CREATED', ?, ?, ?, ?)`)
      .run(runId, manifestUri, manifestSha256, now, now);
  }

  updateRunStatus(runId: string, status: string): void {
    this.database
      .prepare("UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?")
      .run(status, new Date().toISOString(), runId);
  }

  createCase(input: Omit<CaseRow, "status" | "current_attempt_id" | "updated_at">): void {
    const now = new Date().toISOString();
    this.database
      .prepare(`INSERT INTO cases(case_id, run_id, task_id, sut_id, status, ordinal, updated_at)
        VALUES (?, ?, ?, ?, 'CREATED', ?, ?)`)
      .run(input.case_id, input.run_id, input.task_id, input.sut_id, input.ordinal, now);
    this.addEvent(input.run_id, input.case_id, null, "CREATED", {});
  }

  createAttempt(caseId: string, attemptId: string, attemptNumber: number): void {
    this.database
      .prepare(`INSERT INTO attempts(attempt_id, case_id, attempt_number, status)
        VALUES (?, ?, ?, 'CREATED')`)
      .run(attemptId, caseId, attemptNumber);
    this.database
      .prepare("UPDATE cases SET current_attempt_id = ?, updated_at = ? WHERE case_id = ?")
      .run(attemptId, new Date().toISOString(), caseId);
  }

  updateAttempt(
    attemptId: string,
    update: {
      status: string;
      submittedAt?: string | null;
      completedAt?: string | null;
      resultUri?: string | null;
      errorCode?: string | null;
    },
  ): void {
    this.database
      .prepare(`UPDATE attempts SET status = ?, submitted_at = COALESCE(?, submitted_at),
        completed_at = COALESCE(?, completed_at), result_uri = COALESCE(?, result_uri),
        error_code = COALESCE(?, error_code) WHERE attempt_id = ?`)
      .run(
        update.status,
        update.submittedAt ?? null,
        update.completedAt ?? null,
        update.resultUri ?? null,
        update.errorCode ?? null,
        attemptId,
      );
  }

  transitionCase(caseId: string, target: CaseState, payload: Record<string, unknown> = {}): void {
    const current = this.getCase(caseId);
    if (!current) throw new Error(`Unknown case: ${caseId}`);
    assertTransition(current.status, target);
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.addEvent(current.run_id, caseId, current.current_attempt_id, target, payload);
      this.database
        .prepare("UPDATE cases SET status = ?, updated_at = ? WHERE case_id = ?")
        .run(target, new Date().toISOString(), caseId);
      this.database.exec("COMMIT");
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  resetPreSubmissionCase(caseId: string, reason: string): void {
    const current = this.getCase(caseId);
    if (!current) throw new Error(`Unknown case: ${caseId}`);
    const safeStates: CaseState[] = [
      "CREATED",
      "QUEUED",
      "RESOURCE_LEASED",
      "WORKER_READY",
      "SESSION_CREATED",
    ];
    if (!safeStates.includes(current.status)) {
      throw new Error(`Case ${caseId} cannot be safely reset from ${current.status}`);
    }
    if (current.status === "CREATED") {
      this.transitionCase(caseId, "QUEUED", { recovery: true, reason });
      return;
    }
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.addEvent(current.run_id, caseId, current.current_attempt_id, "RECOVERY_RESET", {
        from: current.status,
        to: "QUEUED",
        reason,
      });
      this.database
        .prepare("UPDATE cases SET status = 'QUEUED', updated_at = ? WHERE case_id = ?")
        .run(new Date().toISOString(), caseId);
      if (current.current_attempt_id) {
        this.database
          .prepare("UPDATE attempts SET status = 'CREATED' WHERE attempt_id = ?")
          .run(current.current_attempt_id);
      }
      this.database.exec("COMMIT");
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  addEvent(
    runId: string,
    caseId: string | null,
    attemptId: string | null,
    eventType: string,
    payload: Record<string, unknown>,
  ): void {
    const row = this.database
      .prepare(`SELECT COALESCE(MAX(seq), -1) + 1 AS next_seq FROM events
        WHERE run_id = ? AND case_id IS ? AND attempt_id IS ?`)
      .get(runId, caseId, attemptId) as { next_seq: number };
    this.database
      .prepare(`INSERT INTO events(event_id, run_id, case_id, attempt_id, seq, event_type, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(
        randomUUID(),
        runId,
        caseId,
        attemptId,
        row.next_seq,
        eventType,
        JSON.stringify(payload),
        new Date().toISOString(),
      );
  }

  addArtifact(runId: string, caseId: string | null, attemptId: string | null, ref: ArtifactRef): void {
    this.database
      .prepare(`INSERT INTO artifacts(artifact_id, run_id, case_id, attempt_id, kind, uri, media_type,
        sha256, size_bytes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(
        ref.artifact_id,
        runId,
        caseId,
        attemptId,
        ref.kind,
        ref.uri,
        ref.media_type,
        ref.sha256,
        ref.size_bytes,
        new Date().toISOString(),
      );
  }

  addScore(score: ScoreRecord, recordUri: string): void {
    this.database
      .prepare(`INSERT OR REPLACE INTO scores(score_id, run_id, case_id, attempt_id, metric_id,
        grader_id, grader_version, status, value_json, record_uri)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(
        randomUUID(),
        score.run_id,
        score.case_id,
        score.attempt_id,
        score.metric_id,
        score.grader.id,
        score.grader.version,
        score.status,
        JSON.stringify(score.value),
        recordUri,
      );
  }

  addJudgeJob(job: JudgeJob, profileHash: string, jobUri: string, verdictUri: string, confidence: number): void {
    this.database
      .prepare(`INSERT INTO judge_jobs(judge_job_id, run_id, case_id, attempt_id, grader_id,
        grader_version, purpose, profile_hash, cache_key, status, confidence, cache_source_job_id,
        job_uri, verdict_uri, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?, ?, ?, ?)`)
      .run(
        job.judge_job_id,
        job.run_id,
        job.case_id,
        job.attempt_id,
        job.grader_id,
        job.grader_version,
        job.purpose,
        profileHash,
        job.cache_key,
        confidence,
        job.cache_source_job_id,
        jobUri,
        verdictUri,
        job.created_at,
        new Date().toISOString(),
      );
  }

  findJudgeCache(cacheKey: string): { judge_job_id: string; verdict_uri: string } | undefined {
    return this.database
      .prepare(`SELECT judge_job_id, verdict_uri FROM judge_jobs
        WHERE cache_key = ? AND status = 'COMPLETED' AND verdict_uri IS NOT NULL
        ORDER BY completed_at DESC LIMIT 1`)
      .get(cacheKey) as { judge_job_id: string; verdict_uri: string } | undefined;
  }

  getRun(runId: string): RunRow | undefined {
    return this.database.prepare("SELECT * FROM runs WHERE run_id = ?").get(runId) as RunRow | undefined;
  }

  getCase(caseId: string): CaseRow | undefined {
    return this.database.prepare("SELECT * FROM cases WHERE case_id = ?").get(caseId) as CaseRow | undefined;
  }

  getAttempt(attemptId: string): AttemptRow | undefined {
    return this.database.prepare("SELECT * FROM attempts WHERE attempt_id = ?").get(attemptId) as
      | AttemptRow
      | undefined;
  }

  listCases(runId: string): CaseRow[] {
    return this.database
      .prepare("SELECT * FROM cases WHERE run_id = ? ORDER BY ordinal")
      .all(runId) as unknown as CaseRow[];
  }

  listScores(runId: string): Array<{
    case_id: string;
    attempt_id: string;
    metric_id: string;
    status: string;
    value_json: string | null;
    record_uri: string;
  }> {
    return this.database
      .prepare("SELECT case_id, attempt_id, metric_id, status, value_json, record_uri FROM scores WHERE run_id = ?")
      .all(runId) as unknown as Array<{
      case_id: string;
      attempt_id: string;
      metric_id: string;
      status: string;
      value_json: string | null;
      record_uri: string;
    }>;
  }

  listEvents(runId: string, caseId: string): Array<{
    seq: number;
    event_type: string;
    payload_json: string;
    created_at: string;
  }> {
    return this.database
      .prepare(`SELECT seq, event_type, payload_json, created_at FROM events
        WHERE run_id = ? AND case_id = ? ORDER BY created_at, seq`)
      .all(runId, caseId) as unknown as Array<{
      seq: number;
      event_type: string;
      payload_json: string;
      created_at: string;
    }>;
  }
}
