import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { gradeEvaluationRun } from "../../src/core/grading/runner.js";
import { runEvaluation } from "../../src/core/orchestrator/offline-runner.js";
import { RunManifestSchema } from "../../src/schemas/contracts.js";
import { StateDatabase } from "../../src/core/storage/database.js";

test("xbench production path runs real Process Judge, citation overlay, and regrade cache", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "trueeval-xbench-"));
  const benchmark = path.join(temporary, "benchmark");
  await mkdir(benchmark, { recursive: true });
  const task = { schema_version: "trueeval.research_task.v0.1", task_id: "xbench.fixture.000001", benchmark_id: "xbench-deepsearch", upstream_task_id: "1", split: "smoke", task_family: "short_fact", input: { prompt: "Fixture question", language: "en", as_of: null, attachments: [] }, expected_output: { answer_form: "short_text", citation_required: true }, constraints: { internet_required: true, timeout_seconds: 30 }, provenance: {} };
  const gold = { schema_version: "trueeval.research_gold.v0.1", task_id: task.task_id, answer_type: "short_text", reference_answer: "fixture", acceptable_answers: [], unacceptable_answers: [], claims: [], temporal_scope: {}, official_grader_payload: {}, provenance: {} };
  await writeFile(path.join(benchmark, "tasks.jsonl"), `${JSON.stringify(task)}\n`);
  await writeFile(path.join(benchmark, "gold.jsonl"), `${JSON.stringify(gold)}\n`);
  const profilePath = path.join(temporary, "judge.yaml");
  await writeFile(profilePath, `schema_version: trueeval.judge_profile.v0.1\njudge_profile_id: fixture\ntransport: process\ncommand: [${JSON.stringify(process.execPath)}, ${JSON.stringify(path.resolve("tests/fixtures/judge-process.mjs"))}]\nmodel: fixture\ntemperature: 0\nseed: null\nmax_output_tokens: 100\ntimeout_seconds: 5\nmax_retries: 0\n`);
  const manifest = RunManifestSchema.parse({ schema_version: "trueeval.run_manifest.v0.1", run_id: null, name: "xbench-grade-integration", benchmark: { id: "xbench-deepsearch", version: "fixture", root: benchmark, split: "smoke", task_selector: { ids: [], limit: 1, seed: 1 } }, sut: { id: "fixture.process", adapter: "process", options: { command: [process.execPath, path.resolve("tests/fixtures/process-research-agent.mjs")] } }, execution: { worker: "process", concurrency: 1, max_attempts: 1, headless: false, keep_worker_open: true, new_session_per_task: true, timeout_seconds: 30 }, evaluation: { run_official: true, overlays: ["citation_reliability"], grader_versions_locked: true, judge_profile: profilePath, official_grader_command: null }, artifacts: { root: path.join(temporary, "runs"), retain_raw_html: true, retain_screenshots: true }, state: { database: path.join(temporary, "state.db") } });
  const run = await runEvaluation(manifest);
  assert.deepEqual(await gradeEvaluationRun({ runId: run.runId, artifactsRoot: manifest.artifacts.root, stateDatabase: manifest.state.database }), { scored: 1 });
  const db = new StateDatabase(manifest.state.database);
  try {
    const scores = db.listScores(run.runId);
    assert.equal(scores.length, 6);
    assert.equal(scores.find((score) => score.metric_id === "official.answer_accuracy")?.value_json, "1");
    assert.equal(scores.find((score) => score.metric_id === "trueeval.citation_completeness")?.value_json, "0");
  } finally { db.close(); }
  await gradeEvaluationRun({ runId: run.runId, artifactsRoot: manifest.artifacts.root, stateDatabase: manifest.state.database });
  const files = await readdir(run.runRoot, { recursive: true });
  const rawResponses = files.filter((file) => file.endsWith("response.raw.json"));
  const contents = await Promise.all(rawResponses.map((file) => readFile(path.join(run.runRoot, file), "utf8")));
  assert(contents.some((value) => value.includes('"cache_hit": true')));
});
