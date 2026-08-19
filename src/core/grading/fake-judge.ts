import { randomUUID } from "node:crypto";

import {
  FixtureJudgeVerdictSchema,
  JudgeJobSchema,
  ScoreRecordSchema,
  type ArtifactRef,
  type ResearchSubmission,
  type ScoreRecord,
} from "../../schemas/contracts.js";
import { ArtifactStore } from "../storage/artifact-store.js";
import { StateDatabase } from "../storage/database.js";
import { hashObject, sha256Text } from "../utils/hash.js";

export interface FakeJudgeResult {
  score: ScoreRecord;
  scoreRef: ArtifactRef;
}

export async function runFakeJudge(input: {
  database: StateDatabase;
  store: ArtifactStore;
  submission: ResearchSubmission;
  submissionRef: ArtifactRef;
  jobRoot: string;
}): Promise<FakeJudgeResult> {
  const { database, store, submission, submissionRef, jobRoot } = input;
  const profile = {
    provider: "trueeval-fixture",
    model: "deterministic-fake-judge",
    model_version: "v0.1",
    temperature: 0,
    seed: 20260819,
    max_output_tokens: 256,
    prompt_id: "fixture-quality",
    prompt_version: "v0.1",
    prompt_sha256: sha256Text("Score 1 when a non-empty fixture answer exists."),
    output_schema: "trueeval.fixture_judge_verdict.v0.1",
  };
  const profileHash = hashObject(profile);
  const cacheKey = hashObject({
    run_id: submission.run_id,
    grader: "trueeval.fixture-judge.v0.1",
    profile_hash: profileHash,
    submission_sha256: submissionRef.sha256,
  });
  const cached = database.findJudgeCache(cacheKey);
  const judgeJobId = randomUUID();
  const job = JudgeJobSchema.parse({
    schema_version: "trueeval.judge_job.v0.1",
    judge_job_id: judgeJobId,
    run_id: submission.run_id,
    case_id: submission.case_id,
    attempt_id: submission.attempt_id,
    grader_id: "trueeval.fixture-judge",
    grader_version: "v0.1",
    purpose: "fixture_quality",
    input_refs: [submissionRef],
    allowed_input_fields: ["final_answer"],
    judge_config: profile,
    cache_key: cacheKey,
    cache_source_job_id: cached?.judge_job_id ?? null,
    created_at: new Date().toISOString(),
  });
  const jobRef = await store.writeJson(`${jobRoot}/${judgeJobId}/job.json`, "judge_job", job);
  database.addArtifact(submission.run_id, submission.case_id, submission.attempt_id, jobRef);

  const verdict = cached
    ? FixtureJudgeVerdictSchema.parse(await store.readJson(cached.verdict_uri))
    : FixtureJudgeVerdictSchema.parse({
        schema_version: "trueeval.fixture_judge_verdict.v0.1",
        judge_job_id: judgeJobId,
        score: submission.final_answer.trim() ? 1 : 0,
        confidence: 1,
        rationale: "Deterministic fixture verdict; not a production LLM judgment.",
      });
  const currentVerdict = {
    ...verdict,
    judge_job_id: judgeJobId,
  };
  const verdictRef = await store.writeJson(
    `${jobRoot}/${judgeJobId}/verdict.json`,
    "judge_verdict",
    currentVerdict,
  );
  database.addArtifact(submission.run_id, submission.case_id, submission.attempt_id, verdictRef);
  database.addJudgeJob(job, profileHash, jobRef.uri, verdictRef.uri, currentVerdict.confidence);

  const score = ScoreRecordSchema.parse({
    schema_version: "trueeval.score.v0.1",
    run_id: submission.run_id,
    case_id: submission.case_id,
    attempt_id: submission.attempt_id,
    task_id: submission.task_id,
    namespace: "trueeval",
    metric_id: "trueeval.fixture_judge_quality",
    role: "diagnostic",
    value: currentVerdict.score,
    status: "scored",
    grader: {
      id: "trueeval.fixture-judge",
      version: "v0.1",
      config_hash: profileHash,
    },
    evidence_refs: [submissionRef, verdictRef],
    detail: {
      experimental: true,
      cache_hit: Boolean(cached),
      judge_job_id: judgeJobId,
      rationale: currentVerdict.rationale,
    },
  });
  const attemptRoot = jobRoot.endsWith("/judge-jobs")
    ? jobRoot.slice(0, -"/judge-jobs".length)
    : jobRoot;
  const scoreRef = await store.writeJson(
    `${attemptRoot}/scores/trueeval.fixture-judge.v0.1.json`,
    "score_record",
    score,
  );
  database.addArtifact(submission.run_id, submission.case_id, submission.attempt_id, scoreRef);
  database.addScore(score, scoreRef.uri);
  return { score, scoreRef };
}
