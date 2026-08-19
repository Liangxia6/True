import path from "node:path";

import { JsonlBenchmarkAdapter } from "../../adapters/benchmark/jsonl/adapter.js";
import { JsonlGoldStore } from "../../adapters/benchmark/jsonl/gold-store.js";
import {
  JudgeProfileSchema,
  ResearchSubmissionSchema,
  RunManifestSchema,
  ScoreRecordSchema,
  ShortFactJudgeVerdictSchema,
  type JudgeProfile,
  type ScoreRecord,
  type TaskSpec,
} from "../../schemas/contracts.js";
import { ArtifactStore } from "../storage/artifact-store.js";
import { StateDatabase } from "../storage/database.js";
import { hashObject } from "../utils/hash.js";
import { gradeCitationOverlay } from "./citation-overlay.js";
import { gradeBrowseCompShortFact } from "./browsecomp-short-fact.js";
import { deepResearchScores, invokeDeepResearchOfficial } from "./deepresearch-official.js";
import { runFakeJudge } from "./fake-judge.js";
import { createJudgeProvider, type JudgeProvider } from "./judge/provider.js";
import { gradeXbenchShortFact } from "./xbench-short-fact.js";

function safeSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^\.+/, "") || "task";
}

interface LockedManifest {
  manifest: unknown;
  selected_task_ids: string[];
  judge_profile?: {
    profile: unknown;
    profile_hash: string;
  } | null;
}

async function persistXbenchGrade(input: {
  database: StateDatabase;
  store: ArtifactStore;
  task: TaskSpec;
  submission: ReturnType<typeof ResearchSubmissionSchema.parse>;
  submissionRef: Awaited<ReturnType<ArtifactStore["reference"]>>;
  attemptRoot: string;
  goldStore: JsonlGoldStore;
  profile: JudgeProfile | null;
  profileHash: string | null;
  provider: JudgeProvider | null;
}): Promise<ScoreRecord> {
  const gold = await input.goldStore.get(input.task.task_id);
  const result = await gradeXbenchShortFact({
    task: input.task,
    gold,
    submission: input.submission,
    profile: input.profile,
    provider: input.provider,
    lookupCache: async (cacheKey) => {
      const cached = input.database.findJudgeCache(cacheKey);
      if (!cached) return null;
      return {
        jobId: cached.judge_job_id,
        verdict: ShortFactJudgeVerdictSchema.parse(await input.store.readJson(cached.verdict_uri)),
      };
    },
  });
  const verdictRef = await input.store.writeJson(
    `${input.attemptRoot}/scores/xbench.answer-verdict.json`,
    "short_fact_judge_verdict",
    result.verdict,
  );
  input.database.addArtifact(
    input.submission.run_id,
    input.submission.case_id,
    input.submission.attempt_id,
    verdictRef,
  );

  if (result.judgeJob) {
    const job = { ...result.judgeJob, input_refs: [input.submissionRef] };
    const jobRoot = `${input.attemptRoot}/judge-jobs/${job.judge_job_id}`;
    const jobRef = await input.store.writeJson(`${jobRoot}/job.json`, "judge_job", job);
    const rawRef = await input.store.writeJson(`${jobRoot}/response.raw.json`, "judge_raw_response", result.invocation?.rawResponse ?? { cache_hit: true, cache_source_job_id: result.judgeJob.cache_source_job_id });
    const jobVerdictRef = await input.store.writeJson(
      `${jobRoot}/verdict.json`,
      "judge_verdict",
      result.verdict,
    );
    for (const ref of [jobRef, rawRef, jobVerdictRef]) {
      input.database.addArtifact(
        input.submission.run_id,
        input.submission.case_id,
        input.submission.attempt_id,
        ref,
      );
    }
    input.database.addJudgeJob(
      job,
      input.profileHash ?? hashObject(job.judge_config),
      jobRef.uri,
      jobVerdictRef.uri,
      result.verdict.confidence ?? 0,
    );
  }

  const score = ScoreRecordSchema.parse({
    schema_version: "trueeval.score.v0.1",
    run_id: input.submission.run_id,
    case_id: input.submission.case_id,
    attempt_id: input.submission.attempt_id,
    task_id: input.submission.task_id,
    namespace: "official",
    metric_id: "official.answer_accuracy",
    role: "score",
    value: result.verdict.conclusion === "correct" ? 1 : 0,
    status: "scored",
    grader: {
      id: "xbench.official-answer-grader",
      version: "17c5621-compatible-v1",
      config_hash:
        input.profileHash ?? hashObject({ grader: "xbench.official-answer-grader", exact: true }),
    },
    evidence_refs: [input.submissionRef, verdictRef],
    detail: {
      exact_match: result.exactMatch,
      extracted_answer: result.verdict.extracted_answer,
      rationale: result.verdict.rationale,
      judge_job_id: result.judgeJob?.judge_job_id ?? null,
      judge_cache_hit: result.cacheHit,
      official_compatibility: "upstream_prompt_semantics_with_locked_configurable_judge",
    },
  });
  const scoreRef = await input.store.writeJson(
    `${input.attemptRoot}/scores/official.answer-accuracy.json`,
    "score_record",
    score,
  );
  input.database.addArtifact(
    input.submission.run_id,
    input.submission.case_id,
    input.submission.attempt_id,
    scoreRef,
  );
  input.database.addScore(score, scoreRef.uri);
  return score;
}

async function persistBrowseCompGrade(input: Parameters<typeof persistXbenchGrade>[0]): Promise<ScoreRecord> {
  const gold = await input.goldStore.get(input.task.task_id);
  const result = await gradeBrowseCompShortFact({ task: input.task, gold, submission: input.submission, profile: input.profile, provider: input.provider });
  const verdictRef = await input.store.writeJson(`${input.attemptRoot}/scores/browsecomp-zh.answer-verdict.json`, "short_fact_judge_verdict", result.verdict);
  input.database.addArtifact(input.submission.run_id, input.submission.case_id, input.submission.attempt_id, verdictRef);
  if (result.judgeJob && result.invocation) {
    const job = { ...result.judgeJob, input_refs: [input.submissionRef] };
    const root = `${input.attemptRoot}/judge-jobs/${job.judge_job_id}`;
    const jobRef = await input.store.writeJson(`${root}/job.json`, "judge_job", job);
    const rawRef = await input.store.writeJson(`${root}/response.raw.json`, "judge_raw_response", result.invocation.rawResponse);
    const judgeVerdictRef = await input.store.writeJson(`${root}/verdict.json`, "judge_verdict", result.verdict);
    for (const ref of [jobRef, rawRef, judgeVerdictRef]) input.database.addArtifact(input.submission.run_id, input.submission.case_id, input.submission.attempt_id, ref);
    input.database.addJudgeJob(job, input.profileHash ?? hashObject(job.judge_config), jobRef.uri, judgeVerdictRef.uri, result.verdict.confidence ?? 0);
  }
  const score = ScoreRecordSchema.parse({ schema_version: "trueeval.score.v0.1", run_id: input.submission.run_id, case_id: input.submission.case_id, attempt_id: input.submission.attempt_id, task_id: input.submission.task_id, namespace: "official", metric_id: "official.answer_accuracy", role: "score", value: result.verdict.conclusion === "correct" ? 1 : 0, status: "scored", grader: { id: "browsecomp-zh.official-answer-grader", version: "upstream-compatible-v1", config_hash: input.profileHash ?? hashObject({ grader: "browsecomp-zh", exact: true }) }, evidence_refs: [input.submissionRef, verdictRef], detail: { exact_match: result.exactMatch, extracted_answer: result.verdict.extracted_answer, rationale: result.verdict.rationale, judge_job_id: result.judgeJob?.judge_job_id ?? null } });
  const scoreRef = await input.store.writeJson(`${input.attemptRoot}/scores/official.answer-accuracy.json`, "score_record", score);
  input.database.addArtifact(input.submission.run_id, input.submission.case_id, input.submission.attempt_id, scoreRef);
  input.database.addScore(score, scoreRef.uri);
  return score;
}

export async function gradeEvaluationRun(input: {
  runId: string;
  artifactsRoot: string;
  stateDatabase: string;
}): Promise<{ scored: number }> {
  const database = new StateDatabase(input.stateDatabase);
  const store = new ArtifactStore(path.join(input.artifactsRoot, input.runId));
  let scored = 0;
  try {
    const run = database.getRun(input.runId);
    if (!run) throw new Error(`Unknown run: ${input.runId}`);
    const lock = await store.readJson<LockedManifest>(run.manifest_uri);
    const manifest = RunManifestSchema.parse(lock.manifest);
    const sourceTasks = await new JsonlBenchmarkAdapter(manifest.benchmark.root).listTasks(
      manifest.benchmark.split,
    );
    const allTasks = new Map(sourceTasks.map((task) => [task.task_id, task]));
    const selectedTasks = new Map(
      lock.selected_task_ids.map((id) => {
        const task = allTasks.get(id);
        if (!task) throw new Error(`Locked task is missing from benchmark: ${id}`);
        return [id, task];
      }),
    );
    const profile = lock.judge_profile
      ? JudgeProfileSchema.parse(lock.judge_profile.profile)
      : null;
    const profileHash = lock.judge_profile?.profile_hash ?? null;
    const provider = profile ? createJudgeProvider(profile) : null;
    const goldStore = new JsonlGoldStore(manifest.benchmark.root);

    database.updateRunStatus(input.runId, "GRADING");
    for (const caseRow of database.listCases(input.runId)) {
      if (!(["READY_FOR_GRADING", "DONE", "GRADING_FAILED"] as string[]).includes(caseRow.status)) continue;
      if (!caseRow.current_attempt_id) throw new Error(`Case has no attempt: ${caseRow.case_id}`);
      const attempt = database.getAttempt(caseRow.current_attempt_id);
      if (!attempt?.result_uri) throw new Error(`Attempt has no normalized result: ${caseRow.current_attempt_id}`);
      const task = selectedTasks.get(caseRow.task_id);
      if (!task) throw new Error(`Case task was not locked in the run: ${caseRow.task_id}`);
      database.transitionCase(caseRow.case_id, "GRADING");
      try {
      const submission = ResearchSubmissionSchema.parse(await store.readJson(attempt.result_uri));
      const submissionRef = await store.reference(
        attempt.result_uri,
        "research_submission",
        "application/json",
      );
      const attemptRoot = `cases/${safeSegment(caseRow.task_id)}/attempts/${String(attempt.attempt_number).padStart(4, "0")}`;

      if (manifest.benchmark.id === "fixture-research") {
        await runFakeJudge({
          database,
          store,
          submission,
          submissionRef,
          jobRoot: `${attemptRoot}/judge-jobs`,
        });
      } else if (manifest.evaluation.run_official && manifest.benchmark.id === "xbench-deepsearch") {
        await persistXbenchGrade({
          database,
          store,
          task,
          submission,
          submissionRef,
          attemptRoot,
          goldStore,
          profile,
          profileHash,
          provider,
        });
      } else if (manifest.evaluation.run_official && manifest.benchmark.id === "browsecomp-zh") {
        await persistBrowseCompGrade({ database, store, task, submission, submissionRef, attemptRoot, goldStore, profile, profileHash, provider });
      } else if (manifest.evaluation.run_official && manifest.benchmark.id === "deepresearcheval") {
        if (!manifest.evaluation.official_grader_command) {
          throw new Error(
            "DeepResearchEval requires evaluation.official_grader_command pointing to the pinned upstream wrapper",
          );
        }
        const official = await invokeDeepResearchOfficial({
          command: manifest.evaluation.official_grader_command,
          task,
          submission,
          timeoutSeconds: manifest.execution.timeout_seconds,
        });
        const verdictRef = await store.writeJson(
          `${attemptRoot}/scores/deepresearcheval.official-verdict.json`,
          "deepresearch_official_verdict",
          official.verdict,
        );
        database.addArtifact(submission.run_id, submission.case_id, submission.attempt_id, verdictRef);
        for (const score of deepResearchScores({
          submission,
          verdict: official.verdict,
          verdictRef,
          submissionRef,
          command: manifest.evaluation.official_grader_command,
        })) {
          const scoreRef = await store.writeJson(
            `${attemptRoot}/scores/${score.metric_id}.json`,
            "score_record",
            score,
          );
          database.addArtifact(submission.run_id, submission.case_id, submission.attempt_id, scoreRef);
          database.addScore(score, scoreRef.uri);
        }
      } else if (manifest.evaluation.run_official) {
        throw new Error(`Grader is not implemented for benchmark: ${manifest.benchmark.id}`);
      }

      if (manifest.evaluation.overlays.includes("citation_reliability")) {
        const overlayScores = await gradeCitationOverlay({
          task,
          submission,
          submissionRef,
          store,
          database,
          attemptRoot,
          profile,
          profileHash,
        });
        for (const score of overlayScores) {
          const scoreRef = await store.writeJson(
            `${attemptRoot}/scores/${score.metric_id}.json`,
            "score_record",
            score,
          );
          database.addArtifact(submission.run_id, submission.case_id, submission.attempt_id, scoreRef);
          database.addScore(score, scoreRef.uri);
        }
      }

      database.updateAttempt(attempt.attempt_id, { status: "SCORED" });
      database.transitionCase(caseRow.case_id, "SCORED");
      database.transitionCase(caseRow.case_id, "DONE");
      scored += 1;
      } catch (error) {
        database.updateAttempt(attempt.attempt_id, {
          status: "GRADING_FAILED",
          errorCode: error instanceof Error ? error.name || "GRADING_FAILED" : "GRADING_FAILED",
        });
        const current = database.getCase(caseRow.case_id);
        if (current?.status === "GRADING") {
          database.transitionCase(caseRow.case_id, "GRADING_FAILED", {
            message: error instanceof Error ? error.message : String(error),
          });
        }
        throw error;
      }
    }
    database.updateRunStatus(input.runId, "SCORED");
    return { scored };
  } catch (error) {
    database.updateRunStatus(input.runId, "GRADING_FAILED");
    throw error;
  } finally {
    database.close();
  }
}

export const gradeOfflineRun = gradeEvaluationRun;
