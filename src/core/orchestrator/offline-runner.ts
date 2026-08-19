import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import path from "node:path";

import { createSUTAdapter } from "../../adapters/sut/factory.js";
import type { SUTAdapter } from "../../domains/research/contracts/adapters.js";
import { DefaultResearchNormalizer } from "../../domains/research/normalizers/default.js";
import {
  RawSUTResultSchema,
  RunManifestSchema,
  type RawSUTResult,
  type RunManifest,
  type TaskSpec,
} from "../../schemas/contracts.js";
import { ArtifactStore } from "../storage/artifact-store.js";
import { type AttemptRow, type CaseRow, StateDatabase } from "../storage/database.js";
import { hashObject } from "../utils/hash.js";
import { validateRunManifest } from "../validation/manifest-validator.js";

function safeSegment(value: string): string {
  const safe = value.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^\.+/, "");
  return safe || "task";
}

function gitCommit(): string | null {
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  } catch {
    return null;
  }
}

interface ScheduledCase {
  task: TaskSpec;
  caseId: string;
  attemptId: string;
  attemptNumber: number;
}

export interface EvaluationRunResult {
  runId: string;
  runRoot: string;
  taskCount: number;
}

export interface ResumeResult {
  runId: string;
  resumed: number;
  skipped: number;
  needsHuman: number;
}

function caseRoot(scheduled: ScheduledCase): string {
  return `cases/${safeSegment(scheduled.task.task_id)}/attempts/${String(scheduled.attemptNumber).padStart(4, "0")}`;
}

async function executeCase(input: {
  runId: string;
  manifest: RunManifest;
  scheduled: ScheduledCase;
  adapter: SUTAdapter;
  store: ArtifactStore;
  database: StateDatabase;
  normalizer: DefaultResearchNormalizer;
}): Promise<void> {
  const { runId, manifest, scheduled, adapter, store, database, normalizer } = input;
  const { task, caseId, attemptId } = scheduled;
  const root = caseRoot(scheduled);
  const current = database.getCase(caseId);
  if (!current) throw new Error(`Unknown scheduled case: ${caseId}`);
  if (current.status === "CREATED") database.transitionCase(caseId, "QUEUED");
  else if (current.status !== "QUEUED") {
    throw new Error(`Case ${caseId} must be CREATED or QUEUED before execution, got ${current.status}`);
  }

  database.transitionCase(caseId, "RESOURCE_LEASED", { worker: manifest.execution.worker });
  database.transitionCase(caseId, "WORKER_READY");
  database.transitionCase(caseId, "SESSION_CREATED", { isolated: true });

  const request = {
    schema_version: "trueeval.sut_request.v0.1",
    run_id: runId,
    case_id: caseId,
    attempt_id: attemptId,
    task_id: task.task_id,
    input: task.input,
    expected_output: task.expected_output,
    timeout_seconds: Math.min(task.constraints.timeout_seconds, manifest.execution.timeout_seconds),
  };
  const requestRef = await store.writeJson(`${root}/request.json`, "sut_request", request);
  database.addArtifact(runId, caseId, attemptId, requestRef);

  database.transitionCase(caseId, "SUBMITTING");
  let submissionConfirmed = false;

  let raw: RawSUTResult;
  try {
  raw = await adapter.execute({
    identity: { runId, caseId, attemptId },
    task,
    timeoutSeconds: request.timeout_seconds,
    artifactDirectory: store.resolve(`${root}/raw/provider`),
    onSubmissionConfirmed: async (detail) => {
      if (submissionConfirmed) throw new Error(`Adapter confirmed submission more than once: ${task.task_id}`);
      const submittedAt = new Date().toISOString();
      database.updateAttempt(attemptId, { status: "SUBMITTED", submittedAt });
      database.transitionCase(caseId, "SUBMITTED", { submitted_at: submittedAt, ...detail });
      database.transitionCase(caseId, "RUNNING");
      submissionConfirmed = true;
    },
  });
  } catch (error) {
    raw = RawSUTResultSchema.parse({
      schema_version: "trueeval.raw_sut_result.v0.1",
      run_id: runId,
      case_id: caseId,
      attempt_id: attemptId,
      task_id: task.task_id,
      sut_id: manifest.sut.id,
      status: submissionConfirmed ? "collection_failed" : "provider_error",
      submitted_at: submissionConfirmed ? new Date().toISOString() : null,
      completed_at: new Date().toISOString(),
      raw_answer_text: null,
      raw_citations: [],
      raw_response: null,
      screenshots: [],
      events: null,
      usage: { latency_ms: 0, input_tokens: null, output_tokens: null, search_calls: null, cost_usd: null },
      collection: { answer_status: "not_observable", citation_status: "adapter_failed" },
      error: { code: "ADAPTER_EXECUTE_ERROR", message: error instanceof Error ? error.message : String(error), retryable: !submissionConfirmed },
    });
  }
  if (raw.status === "completed" && !submissionConfirmed) {
    throw new Error(`Adapter returned a completed result without submission checkpoint: ${task.task_id}`);
  }
  if (raw.status !== "completed" || raw.raw_answer_text === null) {
    const failedRawRef = await store.writeJson(`${root}/raw/result.raw.json`, "raw_sut_result", raw);
    database.addArtifact(runId, caseId, attemptId, failedRawRef);
    database.updateAttempt(attemptId, {
      status: raw.status,
      completedAt: raw.completed_at,
      errorCode: raw.error?.code,
    });
    const target =
      raw.status === "timeout"
        ? "TIMED_OUT"
        : raw.status === "submission_unconfirmed"
          ? "SUBMISSION_UNCONFIRMED"
          : raw.status === "collection_failed"
            ? "COLLECTION_FAILED"
            : "PROVIDER_ERROR";
    database.transitionCase(caseId, target);
    return;
  }

  database.transitionCase(caseId, "COMPLETED");
  database.transitionCase(caseId, "COLLECTED");
  const answerRef = await store.writeText(
    `${root}/raw/response.txt`,
    "raw_answer",
    raw.raw_answer_text,
    "text/plain; charset=utf-8",
  );
  database.addArtifact(runId, caseId, attemptId, answerRef);

  const eventLines = database
    .listEvents(runId, caseId)
    .map((event) =>
      JSON.stringify({
        seq: event.seq,
        at: event.created_at,
        state: event.event_type,
        detail: JSON.parse(event.payload_json) as unknown,
      }),
    )
    .join("\n");
  const eventsRef = await store.writeText(
    `${root}/events.jsonl`,
    "trajectory_events",
    `${eventLines}\n`,
    "application/x-ndjson",
  );
  database.addArtifact(runId, caseId, attemptId, eventsRef);

  const completeRaw: RawSUTResult = RawSUTResultSchema.parse({
    ...raw,
    raw_response: answerRef,
    events: eventsRef,
  });
  const rawRef = await store.writeJson(`${root}/raw/result.raw.json`, "raw_sut_result", completeRaw);
  database.addArtifact(runId, caseId, attemptId, rawRef);

  let submission;
  try {
    submission = await normalizer.normalize(completeRaw, task);
  } catch (error) {
    database.updateAttempt(attemptId, {
      status: "NORMALIZATION_FAILED",
      completedAt: raw.completed_at,
      errorCode: error instanceof Error ? error.name || "NORMALIZATION_FAILED" : "NORMALIZATION_FAILED",
    });
    database.transitionCase(caseId, "NORMALIZATION_FAILED", {
      message: error instanceof Error ? error.message : String(error),
    });
    return;
  }
  const submissionRef = await store.writeJson(
    `${root}/normalized/research-submission.json`,
    "research_submission",
    submission,
  );
  database.addArtifact(runId, caseId, attemptId, submissionRef);
  database.updateAttempt(attemptId, {
    status: "READY_FOR_GRADING",
    completedAt: raw.completed_at,
    resultUri: submissionRef.uri,
  });
  database.transitionCase(caseId, "NORMALIZED", { submission_sha256: submissionRef.sha256 });
  database.transitionCase(caseId, "READY_FOR_GRADING");
}

async function withWorker<T>(adapter: SUTAdapter, operation: () => Promise<T>): Promise<T> {
  await adapter.openWorker();
  try {
    return await operation();
  } finally {
    await adapter.closeWorker();
  }
}

export async function runEvaluation(manifest: RunManifest): Promise<EvaluationRunResult> {
  const validation = await validateRunManifest(manifest);
  const runId = manifest.run_id ?? randomUUID();
  const runRoot = path.join(manifest.artifacts.root, runId);
  const store = new ArtifactStore(runRoot);
  const database = new StateDatabase(manifest.state.database);
  const adapter = createSUTAdapter(manifest);
  const normalizer = new DefaultResearchNormalizer();

  const manifestInputRef = await store.writeJson("manifest.input.json", "run_manifest_input", manifest);
  const lockedManifest = {
    schema_version: "trueeval.run_manifest_lock.v0.1",
    run_id: runId,
    locked_at: new Date().toISOString(),
    manifest,
    selected_task_ids: validation.tasks.map((task) => task.task_id),
    sut: validation.sut,
    judge_profile: validation.judgeProfile
      ? {
          profile: validation.judgeProfile.profile,
          profile_hash: validation.judgeProfile.profileHash,
          source_path: validation.judgeProfile.sourcePath,
        }
      : null,
    environment: {
      node: process.version,
      platform: process.platform,
      arch: process.arch,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      git_commit: gitCommit(),
    },
  };
  const manifestLockRef = await store.writeJson(
    "manifest.lock.json",
    "run_manifest_lock",
    lockedManifest,
  );

  try {
    database.createRun(runId, manifestLockRef.uri, manifestLockRef.sha256);
    database.addArtifact(runId, null, null, manifestInputRef);
    database.addArtifact(runId, null, null, manifestLockRef);
    database.updateRunStatus(runId, "RUNNING");

    const scheduledCases = validation.tasks.map<ScheduledCase>((task, index) => {
      const scheduled = {
        task,
        caseId: randomUUID(),
        attemptId: randomUUID(),
        attemptNumber: 1,
      };
      database.createCase({
        case_id: scheduled.caseId,
        run_id: runId,
        task_id: task.task_id,
        sut_id: validation.sut.sut_id,
        ordinal: index,
      });
      database.createAttempt(scheduled.caseId, scheduled.attemptId, scheduled.attemptNumber);
      return scheduled;
    });

    await withWorker(adapter, async () => {
      for (const scheduled of scheduledCases) {
        await executeCase({ runId, manifest, scheduled, adapter, store, database, normalizer });
      }
    });
    database.updateRunStatus(runId, "READY_FOR_GRADING");
    const runSummaryRef = await store.writeJson("run-summary.json", "run_summary", {
      schema_version: "trueeval.run_summary.v0.1",
      run_id: runId,
      status: "READY_FOR_GRADING",
      task_count: validation.tasks.length,
      manifest_hash: hashObject(lockedManifest),
    });
    database.addArtifact(runId, null, null, runSummaryRef);
    return { runId, runRoot, taskCount: validation.tasks.length };
  } catch (error) {
    const existing = database.getRun(runId);
    if (existing) database.updateRunStatus(runId, "FAILED");
    throw error;
  } finally {
    database.close();
  }
}

function scheduledFromRows(task: TaskSpec, caseRow: CaseRow, attempt: AttemptRow): ScheduledCase {
  return {
    task,
    caseId: caseRow.case_id,
    attemptId: attempt.attempt_id,
    attemptNumber: attempt.attempt_number,
  };
}

export async function resumeEvaluation(input: {
  runId: string;
  artifactsRoot: string;
  stateDatabase: string;
}): Promise<ResumeResult> {
  const database = new StateDatabase(input.stateDatabase);
  const store = new ArtifactStore(path.join(input.artifactsRoot, input.runId));
  try {
    const run = database.getRun(input.runId);
    if (!run) throw new Error(`Unknown run: ${input.runId}`);
    const lock = await store.readJson<{ manifest: unknown; selected_task_ids: string[] }>(run.manifest_uri);
    const manifest = RunManifestSchema.parse(lock.manifest);
    const validation = await validateRunManifest(manifest);
    const tasks = new Map(validation.tasks.map((task) => [task.task_id, task]));
    const adapter = createSUTAdapter(manifest);
    const normalizer = new DefaultResearchNormalizer();
    const resumable: ScheduledCase[] = [];
    let skipped = 0;
    let needsHuman = 0;

    for (const caseRow of database.listCases(input.runId)) {
      if (["READY_FOR_GRADING", "DONE", "SCORED"].includes(caseRow.status)) {
        skipped += 1;
        continue;
      }
      if (!caseRow.current_attempt_id) throw new Error(`Case has no attempt: ${caseRow.case_id}`);
      const attempt = database.getAttempt(caseRow.current_attempt_id);
      if (!attempt) throw new Error(`Unknown attempt: ${caseRow.current_attempt_id}`);
      const task = tasks.get(caseRow.task_id);
      if (!task) throw new Error(`Locked task is missing: ${caseRow.task_id}`);
      if (["CREATED", "QUEUED", "RESOURCE_LEASED", "WORKER_READY", "SESSION_CREATED"].includes(caseRow.status)) {
        database.resetPreSubmissionCase(caseRow.case_id, "process_resume_before_submission");
        resumable.push(scheduledFromRows(task, caseRow, attempt));
        continue;
      }
      if (["SUBMITTING", "SUBMITTED", "RUNNING", "COMPLETED", "COLLECTED", "NORMALIZED"].includes(caseRow.status)) {
        database.transitionCase(caseRow.case_id, "NEEDS_HUMAN_VERIFICATION", {
          reason: "submission_or_collection_state_is_ambiguous_after_restart",
        });
        needsHuman += 1;
        continue;
      }
      skipped += 1;
    }

    if (resumable.length > 0) {
      database.updateRunStatus(input.runId, "RUNNING");
      await withWorker(adapter, async () => {
        for (const scheduled of resumable) {
          await executeCase({
            runId: input.runId,
            manifest,
            scheduled,
            adapter,
            store,
            database,
            normalizer,
          });
        }
      });
    }
    database.updateRunStatus(
      input.runId,
      needsHuman > 0 ? "NEEDS_HUMAN_VERIFICATION" : "READY_FOR_GRADING",
    );
    return { runId: input.runId, resumed: resumable.length, skipped, needsHuman };
  } finally {
    database.close();
  }
}

export const runOffline = runEvaluation;
