import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import {
  JsonlBenchmarkAdapter,
  selectTasks,
} from "../../../src/adapters/benchmark/jsonl/adapter.js";

const fixtureRoot = path.resolve("tests/fixtures/benchmark");

test("JSONL benchmark adapter maps source tasks without opening gold", async () => {
  const adapter = new JsonlBenchmarkAdapter(fixtureRoot);
  const tasks = await adapter.listTasks("smoke");
  assert.equal(tasks.length, 2);
  assert.equal(tasks[0]?.track, "short_fact");
  assert.equal(tasks[1]?.track, "long_form");
  assert.equal(JSON.stringify(tasks).includes("EXECUTION_MUST_NOT_READ_THIS_FILE"), false);
});

test("task selection is deterministic for a seed", async () => {
  const tasks = await new JsonlBenchmarkAdapter(fixtureRoot).listTasks("smoke");
  const first = selectTasks(tasks, { ids: [], limit: 1, seed: 42 });
  const second = selectTasks(tasks, { ids: [], limit: 1, seed: 42 });
  assert.deepEqual(first.map((task) => task.task_id), second.map((task) => task.task_id));
});
