import assert from "node:assert/strict";
import { test } from "node:test";

import { ResearchSubmissionSchema, TaskSpecSchema } from "../../../src/schemas/contracts.js";
import { deepResearchScores, invokeDeepResearchOfficial } from "../../../src/core/grading/deepresearch-official.js";

const task = TaskSpecSchema.parse({ schema_version: "trueeval.task.v0.1", task_id: "d-1", benchmark_id: "deepresearcheval", split: "v1", domain: "research", track: "long_form", input: { prompt: "Research this", language: "en", as_of: "2025-06", attachments: [] }, expected_output: { answer_form: "report", citation_required: false }, required_capabilities: [], constraints: { timeout_seconds: 30, internet_required: true, max_attempts: 1 }, evaluation_profile: { official_grader: "deepresearcheval", overlays: [] }, provenance: {} });
const submission = ResearchSubmissionSchema.parse({ schema_version: "trueeval.research_submission.v0.1", run_id: "r", case_id: "c", attempt_id: "a", task_id: "d-1", track: "long_form", final_answer: "A report", sections: [], claims: [], citations: [], attachments: [], normalization: { normalizer_id: "n", normalizer_version: "1", source_artifact_sha256: `sha256:${"0".repeat(64)}`, citation_collection_status: "product_absent" } });
const ref = { artifact_id: "x", kind: "x", uri: "x", media_type: "application/json", sha256: `sha256:${"0".repeat(64)}`, size_bytes: 1 };

test("DeepResearchEval wrapper keeps quality and fact boards separate", async () => {
  const command = [process.execPath, "tests/fixtures/deepresearch-official-grader.mjs"];
  const result = await invokeDeepResearchOfficial({ command, task, submission, timeoutSeconds: 5 });
  const scores = deepResearchScores({ submission, verdict: result.verdict, verdictRef: ref, submissionRef: ref, command });
  assert.deepEqual(scores.map((score) => score.metric_id), ["official.quality_score", "official.fact_ratio"]);
  assert.deepEqual(scores.map((score) => score.value), [7.5, 0.8]);
  assert(scores.every((score) => score.namespace === "official"));
});
