import assert from "node:assert/strict";
import test from "node:test";

import { RunManifestSchema, TaskSpecSchema } from "../../../src/schemas/contracts.js";

test("TaskSpec rejects an invalid schema version", () => {
  const result = TaskSpecSchema.safeParse({ schema_version: "wrong" });
  assert.equal(result.success, false);
});

test("RunManifest requires a new session for every task", () => {
  const result = RunManifestSchema.safeParse({
    schema_version: "trueeval.run_manifest.v0.1",
    run_id: null,
    name: "invalid-session-policy",
    benchmark: {
      id: "fixture",
      version: "v1",
      root: "fixtures",
      split: "test",
      task_selector: { ids: [], limit: 1, seed: 1 },
    },
    sut: { id: "fixture.fake", adapter: "fake", options: {} },
    execution: {
      worker: "fake",
      concurrency: 1,
      max_attempts: 1,
      headless: false,
      keep_worker_open: true,
      new_session_per_task: false,
      timeout_seconds: 30,
    },
    evaluation: {
      run_official: false,
      overlays: [],
      grader_versions_locked: true,
      judge_profile: null,
    },
    artifacts: { root: "artifacts", retain_raw_html: true, retain_screenshots: true },
    state: { database: ".trueeval/test.db" },
  });
  assert.equal(result.success, false);
});
