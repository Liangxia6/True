import { spawn } from "node:child_process";

import {
  DeepResearchOfficialVerdictSchema,
  ScoreRecordSchema,
  type ArtifactRef,
  type DeepResearchOfficialVerdict,
  type ResearchSubmission,
  type ScoreRecord,
  type TaskSpec,
} from "../../schemas/contracts.js";
import { hashObject } from "../utils/hash.js";

export async function invokeDeepResearchOfficial(input: {
  command: string[];
  task: TaskSpec;
  submission: ResearchSubmission;
  timeoutSeconds?: number;
}): Promise<{ verdict: DeepResearchOfficialVerdict; raw: unknown }> {
  const [executable, ...args] = input.command;
  if (!executable) throw new Error("DeepResearchEval official grader command is empty");
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, { shell: false, stdio: ["pipe", "pipe", "pipe"] });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let settled = false;
    const finish = (operation: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      operation();
    };
    const timeout = setTimeout(() => {
      child.kill("SIGTERM");
      finish(() => reject(new Error("DeepResearchEval official grader timed out")));
    }, (input.timeoutSeconds ?? 1800) * 1000);
    child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    child.on("error", (error) => finish(() => reject(error)));
    child.on("close", (code) => finish(() => {
      if (code !== 0) {
        reject(new Error(`DeepResearchEval official grader exited ${code}: ${Buffer.concat(stderr).toString("utf8").slice(0, 2000)}`));
        return;
      }
      try {
        const raw = JSON.parse(Buffer.concat(stdout).toString("utf8")) as unknown;
        const verdict = DeepResearchOfficialVerdictSchema.parse(raw);
        if (verdict.upstream_commit !== "121d4c34050d0e3b0ee441c52c4467cf58ab941e") {
          throw new Error(`DeepResearchEval bridge returned unexpected upstream commit: ${verdict.upstream_commit}`);
        }
        resolve({ verdict, raw });
      } catch (error) {
        reject(error);
      }
    }));
    child.stdin.end(JSON.stringify({
      schema_version: "trueeval.deepresearch_official_request.v0.1",
      task_id: input.task.task_id,
      query: input.task.input.prompt,
      response: input.submission.final_answer,
      required_upstream_commit: "121d4c34050d0e3b0ee441c52c4467cf58ab941e",
    }));
  });
}

export function deepResearchScores(input: {
  submission: ResearchSubmission;
  verdict: DeepResearchOfficialVerdict;
  verdictRef: ArtifactRef;
  submissionRef: ArtifactRef;
  command: string[];
}): ScoreRecord[] {
  const grader = {
    id: "deepresearcheval.upstream-process-wrapper",
    version: input.verdict.upstream_commit,
    config_hash: hashObject({ command: input.command, upstream_commit: input.verdict.upstream_commit }),
  };
  const base = {
    schema_version: "trueeval.score.v0.1" as const,
    run_id: input.submission.run_id,
    case_id: input.submission.case_id,
    attempt_id: input.submission.attempt_id,
    task_id: input.submission.task_id,
    namespace: "official" as const,
    role: "score" as const,
    grader,
    evidence_refs: [input.submissionRef, input.verdictRef],
  };
  return [
    ScoreRecordSchema.parse({ ...base, metric_id: "official.quality_score", value: input.verdict.quality_score, status: "scored", detail: { dimensions: input.verdict.quality_dimensions, upstream_commit: input.verdict.upstream_commit } }),
    ScoreRecordSchema.parse({ ...base, metric_id: "official.fact_ratio", value: input.verdict.fact_ratio, status: input.verdict.fact_ratio === null ? "not_observable" : "scored", detail: { right_count: input.verdict.right_count, wrong_count: input.verdict.wrong_count, unknown_count: input.verdict.unknown_count, upstream_commit: input.verdict.upstream_commit } }),
  ];
}
