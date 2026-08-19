import assert from "node:assert/strict";
import { test } from "node:test";

import { GoldRecordSchema, JudgeProfileSchema, ResearchSubmissionSchema, TaskSpecSchema } from "../../../src/schemas/contracts.js";
import { gradeXbenchShortFact } from "../../../src/core/grading/xbench-short-fact.js";

const task = TaskSpecSchema.parse({ schema_version: "trueeval.task.v0.1", task_id: "x-1", benchmark_id: "xbench-deepsearch", split: "test", domain: "research", track: "short_fact", input: { prompt: "What?", language: "en", as_of: null, attachments: [] }, expected_output: { answer_form: "short_text", citation_required: false }, required_capabilities: [], constraints: { timeout_seconds: 30, internet_required: true, max_attempts: 1 }, evaluation_profile: { official_grader: "xbench", overlays: [] }, provenance: {} });
const gold = GoldRecordSchema.parse({ schema_version: "trueeval.research_gold.v0.1", task_id: "x-1", answer_type: "short_text", reference_answer: "Paris", acceptable_answers: [], unacceptable_answers: [], claims: [], temporal_scope: {}, official_grader_payload: {}, provenance: {} });
const submission = (answer: string) => ResearchSubmissionSchema.parse({ schema_version: "trueeval.research_submission.v0.1", run_id: "r", case_id: "c", attempt_id: "a", task_id: "x-1", track: "short_fact", final_answer: answer, sections: [], claims: [], citations: [], attachments: [], normalization: { normalizer_id: "n", normalizer_version: "1", source_artifact_sha256: `sha256:${"0".repeat(64)}`, citation_collection_status: "product_absent" } });

test("xbench exact marked answer skips the LLM Judge", async () => {
  const result = await gradeXbenchShortFact({ task, gold, submission: submission("最终答案: Paris。"), profile: null, provider: null });
  assert.equal(result.exactMatch, true);
  assert.equal(result.verdict.conclusion, "correct");
});

test("xbench semantic grading uses the configured Judge", async () => {
  const profile = JudgeProfileSchema.parse({ schema_version: "trueeval.judge_profile.v0.1", judge_profile_id: "p", transport: "process", command: ["unused"], model: "m", temperature: 0, seed: null, max_output_tokens: 20, timeout_seconds: 2, max_retries: 0 });
  let calls = 0;
  const result = await gradeXbenchShortFact({ task, gold, submission: submission("The French capital is Paris."), profile, provider: { invoke: async () => { calls += 1; return { text: "最终答案: Paris\n解释: 一致\n结论: 正确", actualModel: "m-v1", rawResponse: {}, usage: { input_tokens: null, output_tokens: null, cost_usd: null } }; } } });
  assert.equal(calls, 1);
  assert.equal(result.verdict.conclusion, "correct");
  assert.equal(result.judgeJob?.judge_config.model_version, "m-v1");
});
