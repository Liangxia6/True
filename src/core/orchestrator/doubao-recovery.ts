import path from "node:path";

import { JsonlBenchmarkAdapter } from "../../adapters/benchmark/jsonl/adapter.js";
import { DoubaoBatchAdapter, doubaoOptionsFromManifest } from "../../adapters/sut/web/doubao/facade.js";
import { normalizeText } from "../../adapters/sut/web/doubao/text.js";
import { DefaultResearchNormalizer } from "../../domains/research/normalizers/default.js";
import {
  RawSUTResultSchema,
  ResearchSubmissionSchema,
  RunManifestSchema,
  type RawSUTResult,
} from "../../schemas/contracts.js";
import { ArtifactStore } from "../storage/artifact-store.js";
import { StateDatabase } from "../storage/database.js";

function safeSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^\.+/, "") || "task";
}

export async function recoverDoubaoSubmissions(input: { runId: string; artifactsRoot: string; stateDatabase: string }): Promise<{ recovered: number; notFound: number; failed: number }> {
  const database = new StateDatabase(input.stateDatabase);
  const store = new ArtifactStore(path.join(input.artifactsRoot, input.runId));
  let recovered = 0;
  let notFound = 0;
  let failed = 0;
  try {
    const run = database.getRun(input.runId);
    if (!run) throw new Error(`Unknown run: ${input.runId}`);
    const lock = await store.readJson<{ manifest: unknown; selected_task_ids: string[] }>(run.manifest_uri);
    const manifest = RunManifestSchema.parse(lock.manifest);
    if (manifest.sut.adapter !== "doubao_web") throw new Error("recover-doubao only supports doubao_web runs");
    const tasks = new Map((await new JsonlBenchmarkAdapter(manifest.benchmark.root).listTasks(manifest.benchmark.split)).map((task) => [task.task_id, task]));
    const adapter = new DoubaoBatchAdapter(doubaoOptionsFromManifest({ sutId: manifest.sut.id, headless: manifest.execution.headless, options: manifest.sut.options }));
    const normalizer = new DefaultResearchNormalizer();
    await adapter.openWorker();
    try {
      for (const caseRow of database.listCases(input.runId)) {
        if (caseRow.status !== "SUBMISSION_UNCONFIRMED") continue;
        if (!caseRow.current_attempt_id) throw new Error(`Case has no attempt: ${caseRow.case_id}`);
        const attempt = database.getAttempt(caseRow.current_attempt_id);
        const task = tasks.get(caseRow.task_id);
        if (!attempt || !task) throw new Error(`Recovery input missing for ${caseRow.task_id}`);
        const root = `cases/${safeSegment(task.task_id)}/attempts/${String(attempt.attempt_number).padStart(4, "0")}`;
        let confirmed = false;
        const raw = await adapter.recoverExisting({ identity: { runId: input.runId, caseId: caseRow.case_id, attemptId: attempt.attempt_id }, task, timeoutSeconds: Math.min(task.constraints.timeout_seconds, manifest.execution.timeout_seconds), artifactDirectory: store.resolve(`${root}/raw/recovery`), onSubmissionConfirmed: async (detail) => {
          const submittedAt = new Date().toISOString();
          database.updateAttempt(attempt.attempt_id, { status: "SUBMITTED", submittedAt });
          database.transitionCase(caseRow.case_id, "SUBMITTED", { recovery: true, ...detail });
          database.transitionCase(caseRow.case_id, "RUNNING", { recovery: true });
          confirmed = true;
        } });
        if (!raw) { notFound += 1; continue; }
        if (!confirmed) throw new Error(`Recovery returned a result without verifying submission: ${task.task_id}`);
        if (raw.status !== "completed" || raw.raw_answer_text === null) {
          const failedRef = await store.writeJson(`${root}/raw/result.recovery-failed.json`, "raw_sut_result", raw);
          database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, failedRef);
          database.updateAttempt(attempt.attempt_id, { status: raw.status, completedAt: raw.completed_at, errorCode: raw.error?.code });
          database.transitionCase(caseRow.case_id, raw.status === "timeout" ? "TIMED_OUT" : "COLLECTION_FAILED", { recovery: true });
          failed += 1;
          continue;
        }
        database.transitionCase(caseRow.case_id, "COMPLETED", { recovery: true });
        database.transitionCase(caseRow.case_id, "COLLECTED", { recovery: true });
        const answerRef = await store.writeText(`${root}/raw/response.recovered.txt`, "raw_answer", raw.raw_answer_text);
        database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, answerRef);
        const events = database.listEvents(input.runId, caseRow.case_id).map((event) => JSON.stringify({ seq: event.seq, at: event.created_at, state: event.event_type, detail: JSON.parse(event.payload_json) })).join("\n");
        const eventsRef = await store.writeText(`${root}/events.recovered.jsonl`, "trajectory_events", `${events}\n`, "application/x-ndjson");
        database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, eventsRef);
        const completeRaw: RawSUTResult = RawSUTResultSchema.parse({ ...raw, raw_response: answerRef, events: eventsRef });
        const rawRef = await store.writeJson(`${root}/raw/result.recovered.json`, "raw_sut_result", completeRaw);
        database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, rawRef);
        const submission = await normalizer.normalize(completeRaw, task);
        const submissionRef = await store.writeJson(`${root}/normalized/research-submission.json`, "research_submission", submission);
        database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, submissionRef);
        database.updateAttempt(attempt.attempt_id, { status: "READY_FOR_GRADING", completedAt: raw.completed_at, resultUri: submissionRef.uri });
        database.transitionCase(caseRow.case_id, "NORMALIZED", { recovery: true, submission_sha256: submissionRef.sha256 });
        database.transitionCase(caseRow.case_id, "READY_FOR_GRADING", { recovery: true });
        recovered += 1;
      }
    } finally { await adapter.closeWorker(); }
    database.updateRunStatus(input.runId, database.listCases(input.runId).every((entry) => entry.status === "READY_FOR_GRADING") ? "READY_FOR_GRADING" : "RECOVERY_INCOMPLETE");
    return { recovered, notFound, failed };
  } finally { database.close(); }
}

export async function refreshDoubaoCitations(input: {
  runId: string;
  artifactsRoot: string;
  stateDatabase: string;
}): Promise<{ refreshed: number; productAbsent: number; notFound: number; failed: number }> {
  const database = new StateDatabase(input.stateDatabase);
  const store = new ArtifactStore(path.join(input.artifactsRoot, input.runId));
  let refreshed = 0;
  let productAbsent = 0;
  let notFound = 0;
  let failed = 0;
  try {
    const run = database.getRun(input.runId);
    if (!run) throw new Error(`Unknown run: ${input.runId}`);
    const lock = await store.readJson<{ manifest: unknown }>(run.manifest_uri);
    const manifest = RunManifestSchema.parse(lock.manifest);
    if (manifest.sut.adapter !== "doubao_web") {
      throw new Error("refresh-doubao-citations only supports doubao_web runs");
    }
    const tasks = new Map(
      (await new JsonlBenchmarkAdapter(manifest.benchmark.root).listTasks(manifest.benchmark.split)).map(
        (task) => [task.task_id, task],
      ),
    );
    const adapter = new DoubaoBatchAdapter(
      doubaoOptionsFromManifest({
        sutId: manifest.sut.id,
        headless: manifest.execution.headless,
        options: manifest.sut.options,
      }),
    );
    await adapter.openWorker();
    try {
      for (const caseRow of database.listCases(input.runId)) {
        if (caseRow.status !== "READY_FOR_GRADING") continue;
        if (!caseRow.current_attempt_id) throw new Error(`Case has no attempt: ${caseRow.case_id}`);
        const attempt = database.getAttempt(caseRow.current_attempt_id);
        const task = tasks.get(caseRow.task_id);
        if (!attempt?.result_uri || !task) {
          failed += 1;
          continue;
        }
        const original = ResearchSubmissionSchema.parse(await store.readJson(attempt.result_uri));
        const root = `cases/${safeSegment(task.task_id)}/attempts/${String(attempt.attempt_number).padStart(4, "0")}`;
        try {
          const raw = await adapter.recoverExisting({
            identity: {
              runId: input.runId,
              caseId: caseRow.case_id,
              attemptId: attempt.attempt_id,
            },
            task,
            timeoutSeconds: Math.min(task.constraints.timeout_seconds, manifest.execution.timeout_seconds),
            artifactDirectory: store.resolve(`${root}/raw/citation-refresh`),
            onSubmissionConfirmed: async () => undefined,
          });
          if (!raw) {
            notFound += 1;
            continue;
          }
          if (raw.status !== "completed" || raw.raw_answer_text === null) {
            const failureRef = await store.writeJson(
              `${root}/raw/result.citation-refresh-failed.json`,
              "raw_sut_result",
              raw,
            );
            database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, failureRef);
            failed += 1;
            continue;
          }
          if (normalizeText(raw.raw_answer_text) !== normalizeText(original.final_answer)) {
            throw new Error(`Answer changed while refreshing citations for ${task.task_id}`);
          }
          const rawRef = await store.writeJson(
            `${root}/raw/result.citation-refresh.json`,
            "raw_sut_result",
            raw,
          );
          database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, rawRef);
          const submission = ResearchSubmissionSchema.parse({
            ...original,
            citations: raw.raw_citations.map((citation) => ({
              citation_id: citation.citation_id,
              display_text: citation.title,
              visible_url: citation.url,
              resolved_url: null,
              quoted_text: null,
              claim_ids: [],
              collection_status: citation.url ? "visible_only" : "unresolvable",
            })),
            normalization: {
              ...original.normalization,
              citation_collection_status: raw.collection.citation_status,
            },
          });
          const submissionRef = await store.writeJson(
            `${root}/normalized/research-submission.citations-refreshed.json`,
            "research_submission",
            submission,
          );
          database.addArtifact(input.runId, caseRow.case_id, attempt.attempt_id, submissionRef);
          database.updateAttempt(attempt.attempt_id, {
            status: "READY_FOR_GRADING",
            resultUri: submissionRef.uri,
          });
          database.addEvent(input.runId, caseRow.case_id, attempt.attempt_id, "CITATIONS_REFRESHED", {
            citation_count: submission.citations.length,
            submission_sha256: submissionRef.sha256,
          });
          if (submission.citations.length) refreshed += 1;
          else productAbsent += 1;
        } catch (error) {
          database.addEvent(input.runId, caseRow.case_id, attempt.attempt_id, "CITATION_REFRESH_FAILED", {
            message: error instanceof Error ? error.message : String(error),
          });
          failed += 1;
        }
      }
    } finally {
      await adapter.closeWorker();
    }
    return { refreshed, productAbsent, notFound, failed };
  } finally {
    database.close();
  }
}
