import assert from "node:assert/strict";
import { test } from "node:test";

import { GoldRecordSchema, JudgeProfileSchema, ResearchSubmissionSchema, TaskSpecSchema } from "../../../src/schemas/contracts.js";
import { gradeBrowseCompShortFact } from "../../../src/core/grading/browsecomp-short-fact.js";

const task = TaskSpecSchema.parse({ schema_version: "trueeval.task.v0.1", task_id: "b-1", benchmark_id: "browsecomp-zh", split: "test", domain: "research", track: "short_fact", input: { prompt: "何时？", language: "zh", as_of: null, attachments: [] }, expected_output: { answer_form: "short_text", citation_required: false }, required_capabilities: [], constraints: { timeout_seconds: 30, internet_required: true, max_attempts: 1 }, evaluation_profile: { official_grader: "browsecomp-zh", overlays: [] }, provenance: {} });
const gold = GoldRecordSchema.parse({ schema_version: "trueeval.research_gold.v0.1", task_id: "b-1", answer_type: "short_text", reference_answer: "2019年4月23日", acceptable_answers: [], unacceptable_answers: [], claims: [], temporal_scope: {}, official_grader_payload: {}, provenance: {} });
const submission = ResearchSubmissionSchema.parse({ schema_version: "trueeval.research_submission.v0.1", run_id: "r", case_id: "c", attempt_id: "a", task_id: "b-1", track: "short_fact", final_answer: "答案是2019年4月23日。", sections: [], claims: [], citations: [], attachments: [], normalization: { normalizer_id: "n", normalizer_version: "1", source_artifact_sha256: `sha256:${"0".repeat(64)}`, citation_collection_status: "product_absent" } });

test("BrowseComp-ZH non-marked response uses its official-compatible Judge format", async () => {
  const profile = JudgeProfileSchema.parse({ schema_version: "trueeval.judge_profile.v0.1", judge_profile_id: "p", transport: "process", command: ["unused"], model: "gpt-4o-compatible", temperature: 0, seed: null, max_output_tokens: 100, timeout_seconds: 5, max_retries: 0 });
  const result = await gradeBrowseCompShortFact({ task, gold, submission, profile, provider: { invoke: async () => ({ text: "extracted_final_answer: 2019年4月23日\nreasoning: 与正确答案一致\ncorrect: yes\nconfidence: 100", actualModel: "fixture", rawResponse: {}, usage: { input_tokens: null, output_tokens: null, cost_usd: null } }) } });
  assert.equal(result.verdict.conclusion, "correct");
  assert.equal(result.judgeJob?.judge_config.prompt_id, "browsecomp_zh.JUDGE_PROMPT_CN");
});
