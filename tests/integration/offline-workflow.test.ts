import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { gradeOfflineRun } from "../../src/core/grading/runner.js";
import { runOffline } from "../../src/core/orchestrator/offline-runner.js";
import { generateRunReport } from "../../src/core/reporting/report.js";
import { StateDatabase } from "../../src/core/storage/database.js";
import { RunManifestSchema } from "../../src/schemas/contracts.js";

test("offline workflow runs, grades with Fake Judge, and reports", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "trueeval-workflow-"));
  const artifactsRoot = path.join(temporary, "artifacts");
  const stateDatabase = path.join(temporary, "state.db");
  try {
    const manifest = RunManifestSchema.parse({
      schema_version: "trueeval.run_manifest.v0.1",
      run_id: null,
      name: "integration-offline",
      benchmark: {
        id: "fixture-research",
        version: "fixture-v0.1",
        root: path.resolve("tests/fixtures/benchmark"),
        split: "smoke",
        task_selector: { ids: [], limit: 2, seed: 20260819 },
      },
      sut: { id: "fixture.fake.research", adapter: "fake", options: {} },
      execution: {
        worker: "fake",
        concurrency: 1,
        max_attempts: 1,
        headless: false,
        keep_worker_open: true,
        new_session_per_task: true,
        timeout_seconds: 30,
      },
      evaluation: {
        run_official: false,
        overlays: [],
        grader_versions_locked: true,
        judge_profile: null,
      },
      artifacts: { root: artifactsRoot, retain_raw_html: true, retain_screenshots: true },
      state: { database: stateDatabase },
    });
    const run = await runOffline(manifest);
    assert.equal(run.taskCount, 2);

    const beforeGrade = new StateDatabase(stateDatabase);
    assert.equal(beforeGrade.getRun(run.runId)?.status, "READY_FOR_GRADING");
    assert.deepEqual(
      beforeGrade.listCases(run.runId).map((entry) => entry.status),
      ["READY_FOR_GRADING", "READY_FOR_GRADING"],
    );
    beforeGrade.close();

    assert.deepEqual(
      await gradeOfflineRun({ runId: run.runId, artifactsRoot, stateDatabase }),
      { scored: 2 },
    );
    const report = await generateRunReport({ runId: run.runId, artifactsRoot, stateDatabase });
    assert.equal(report.cases.done, 2);
    assert.equal(report.cases.system_failures, 0);
    assert.equal(report.metrics["trueeval.fixture_judge_quality"]?.mean, 1);

    const reportOnDisk = JSON.parse(
      await readFile(path.join(artifactsRoot, run.runId, "report.json"), "utf8"),
    ) as { run_id: string };
    assert.equal(reportOnDisk.run_id, run.runId);

    const secondGrade = await gradeOfflineRun({ runId: run.runId, artifactsRoot, stateDatabase });
    assert.equal(secondGrade.scored, 2);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});
