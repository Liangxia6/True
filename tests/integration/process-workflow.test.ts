import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { loadManifest, resolveManifestPaths } from "../../src/core/config/manifest.js";
import { gradeEvaluationRun } from "../../src/core/grading/runner.js";
import { runEvaluation } from "../../src/core/orchestrator/offline-runner.js";
import { StateDatabase } from "../../src/core/storage/database.js";

test("Process SUT runs the same benchmark without core or benchmark changes", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "trueeval-process-"));
  const source = resolveManifestPaths(await loadManifest("manifests/process-fixture-smoke.yaml"));
  const manifest = { ...source, artifacts: { ...source.artifacts, root: path.join(temporary, "runs") }, state: { database: path.join(temporary, "state.db") }, sut: { ...source.sut, options: { ...source.sut.options, command: [process.execPath, path.resolve("tests/fixtures/process-research-agent.mjs")] } } };
  const run = await runEvaluation(manifest);
  assert.equal(run.taskCount, 2);
  const graded = await gradeEvaluationRun({ runId: run.runId, artifactsRoot: manifest.artifacts.root, stateDatabase: manifest.state.database });
  assert.equal(graded.scored, 2);
  const db = new StateDatabase(manifest.state.database);
  try {
    assert(db.listCases(run.runId).every((entry) => entry.status === "DONE"));
    assert.equal(db.listScores(run.runId).length, 2);
  } finally { db.close(); }
  const firstTask = JSON.parse((await readFile("tests/fixtures/benchmark/tasks.jsonl", "utf8")).split("\n")[0]!);
  const caseDirectory = path.join(run.runRoot, "cases", firstTask.task_id, "attempts", "0001", "normalized", "research-submission.json");
  assert.match(await readFile(caseDirectory, "utf8"), /Agent answer for/);
});
