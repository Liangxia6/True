import { createReadStream } from "node:fs";
import path from "node:path";
import { createInterface } from "node:readline";

import type { BenchmarkAdapter } from "../../../domains/research/contracts/adapters.js";
import {
  SourceResearchTaskSchema,
  TaskSpecSchema,
  type SourceResearchTask,
  type TaskSpec,
} from "../../../schemas/contracts.js";
import { sha256Text } from "../../../core/utils/hash.js";

function trackFor(taskFamily: string): "short_fact" | "long_form" {
  return taskFamily === "report_research" ? "long_form" : "short_fact";
}

function toTaskSpec(source: SourceResearchTask): TaskSpec {
  if (source.input.attachments.length > 0) {
    throw new Error(`Task ${source.task_id} has attachments not supported by the Phase 0 adapter`);
  }
  const track = trackFor(source.task_family);
  return TaskSpecSchema.parse({
    schema_version: "trueeval.task.v0.1",
    task_id: source.task_id,
    benchmark_id: source.benchmark_id,
    split: source.split,
    domain: "research",
    track,
    input: {
      prompt: source.input.prompt,
      language: source.input.language,
      as_of: source.input.as_of,
      attachments: [],
    },
    expected_output: {
      answer_form: source.expected_output.answer_form,
      citation_required: source.expected_output.citation_required,
    },
    required_capabilities: ["research_mode", track],
    constraints: {
      timeout_seconds: source.constraints.timeout_seconds,
      internet_required: source.constraints.internet_required,
      max_attempts: 1,
    },
    evaluation_profile: {
      official_grader: `${source.benchmark_id}.official`,
      overlays: [],
    },
    provenance: {
      ...source.provenance,
      upstream_task_id: source.upstream_task_id,
      source_schema_version: source.schema_version,
    },
  });
}

export class JsonlBenchmarkAdapter implements BenchmarkAdapter {
  constructor(private readonly benchmarkRoot: string) {}

  async listTasks(split: string): Promise<TaskSpec[]> {
    const sourcePath = path.join(this.benchmarkRoot, "tasks.jsonl");
    const input = createReadStream(sourcePath, { encoding: "utf8" });
    const lines = createInterface({ input, crlfDelay: Infinity });
    const tasks: TaskSpec[] = [];
    let lineNumber = 0;
    for await (const line of lines) {
      lineNumber += 1;
      if (!line.trim()) continue;
      try {
        const source = SourceResearchTaskSchema.parse(JSON.parse(line) as unknown);
        if (source.split === split) tasks.push(toTaskSpec(source));
      } catch (error) {
        throw new Error(`Invalid task at ${sourcePath}:${lineNumber}`, { cause: error });
      }
    }
    return tasks;
  }
}

export function selectTasks(
  tasks: readonly TaskSpec[],
  selector: { ids: readonly string[]; limit: number | null; seed: number },
): TaskSpec[] {
  if (selector.ids.length > 0) {
    const byId = new Map(tasks.map((task) => [task.task_id, task]));
    return selector.ids.map((id) => {
      const task = byId.get(id);
      if (!task) throw new Error(`Selected task not found in split: ${id}`);
      return task;
    });
  }
  const ordered = [...tasks].sort((left, right) => {
    const leftHash = sha256Text(`${selector.seed}:${left.task_id}`);
    const rightHash = sha256Text(`${selector.seed}:${right.task_id}`);
    return leftHash.localeCompare(rightHash);
  });
  return selector.limit === null ? ordered : ordered.slice(0, selector.limit);
}
