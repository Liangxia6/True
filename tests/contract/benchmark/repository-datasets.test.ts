import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { JsonlBenchmarkAdapter } from "../../../src/adapters/benchmark/jsonl/adapter.js";

const datasets = [
  { id: "xbench-deepsearch", split: "2505", expected: 100 },
  { id: "browsecomp-zh", split: "test", expected: 289 },
  { id: "deepresearcheval", split: "v1", expected: 100 },
] as const;

for (const dataset of datasets) {
  const root = path.resolve("benchmarks", dataset.id);
  const tasksPath = path.join(root, "tasks.jsonl");
  test(
    `${dataset.id} ${dataset.split} conforms to the canonical task contract`,
    { skip: !existsSync(tasksPath) },
    async () => {
      const tasks = await new JsonlBenchmarkAdapter(root).listTasks(dataset.split);
      assert.equal(tasks.length, dataset.expected);
      assert.equal(tasks.every((task) => task.benchmark_id === dataset.id), true);
    },
  );
}
