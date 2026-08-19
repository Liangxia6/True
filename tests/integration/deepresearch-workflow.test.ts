import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { gradeEvaluationRun } from "../../src/core/grading/runner.js";
import { runEvaluation } from "../../src/core/orchestrator/offline-runner.js";
import { StateDatabase } from "../../src/core/storage/database.js";
import { RunManifestSchema } from "../../src/schemas/contracts.js";

test("two DeepResearchEval reports execute and keep official quality/fact scores separate", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "trueeval-deepresearch-"));
  const benchmark = path.join(temporary, "benchmark");
  await mkdir(benchmark, { recursive: true });
  const tasks = [1, 2].map((ordinal) => ({ schema_version: "trueeval.research_task.v0.1", task_id: `deepresearcheval.fixture.${ordinal}`, benchmark_id: "deepresearcheval", upstream_task_id: String(ordinal), split: "smoke", task_family: "report_research", input: { prompt: `Long research question ${ordinal}`, language: "en", as_of: "2025-06", attachments: [] }, expected_output: { answer_form: "report", citation_required: false }, constraints: { internet_required: true, timeout_seconds: 30 }, provenance: {} }));
  await writeFile(path.join(benchmark, "tasks.jsonl"), `${tasks.map((task) => JSON.stringify(task)).join("\n")}\n`);
  await writeFile(path.join(benchmark, "gold.jsonl"), `${tasks.map((task) => JSON.stringify({ schema_version: "trueeval.research_gold.v0.1", task_id: task.task_id, answer_type: "report", reference_answer: null, acceptable_answers: [], unacceptable_answers: [], claims: [], temporal_scope: {}, official_grader_payload: {}, provenance: {} })).join("\n")}\n`);
  const manifest = RunManifestSchema.parse({ schema_version: "trueeval.run_manifest.v0.1", run_id: null, name: "deepresearch-two", benchmark: { id: "deepresearcheval", version: "fixture", root: benchmark, split: "smoke", task_selector: { ids: [], limit: 2, seed: 1 } }, sut: { id: "fixture.process", adapter: "process", options: { command: [process.execPath, path.resolve("tests/fixtures/process-research-agent.mjs")] } }, execution: { worker: "process", concurrency: 1, max_attempts: 1, headless: false, keep_worker_open: true, new_session_per_task: true, timeout_seconds: 30 }, evaluation: { run_official: true, overlays: ["citation_reliability"], grader_versions_locked: true, judge_profile: null, official_grader_command: [process.execPath, path.resolve("tests/fixtures/deepresearch-official-grader.mjs")] }, artifacts: { root: path.join(temporary, "runs"), retain_raw_html: true, retain_screenshots: true }, state: { database: path.join(temporary, "state.db") } });
  const run = await runEvaluation(manifest);
  assert.deepEqual(await gradeEvaluationRun({ runId: run.runId, artifactsRoot: manifest.artifacts.root, stateDatabase: manifest.state.database }), { scored: 2 });
  const db = new StateDatabase(manifest.state.database);
  try {
    const scores = db.listScores(run.runId);
    assert.equal(scores.filter((score) => score.metric_id === "official.quality_score").length, 2);
    assert.equal(scores.filter((score) => score.metric_id === "official.fact_ratio").length, 2);
    assert.equal(scores.filter((score) => score.metric_id.startsWith("trueeval.citation_")).length, 6);
  } finally { db.close(); }
});
