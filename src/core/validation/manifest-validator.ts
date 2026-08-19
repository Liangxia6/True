import { JsonlBenchmarkAdapter, selectTasks } from "../../adapters/benchmark/jsonl/adapter.js";
import { createSUTAdapter } from "../../adapters/sut/factory.js";
import type { RunManifest, SUTSpec, TaskSpec } from "../../schemas/contracts.js";
import { loadJudgeProfile } from "../grading/judge/profile.js";

export interface ValidationResult {
  tasks: TaskSpec[];
  sut: SUTSpec;
  judgeProfile: Awaited<ReturnType<typeof loadJudgeProfile>> | null;
}

export async function validateRunManifest(manifest: RunManifest): Promise<ValidationResult> {
  const expectedWorker = manifest.sut.adapter === "fake" ? "fake" : manifest.sut.adapter === "doubao_web" ? "browser" : "process";
  if (manifest.execution.worker !== expectedWorker) {
    throw new Error(`SUT adapter ${manifest.sut.adapter} requires execution.worker=${expectedWorker}`);
  }
  const benchmark = new JsonlBenchmarkAdapter(manifest.benchmark.root);
  const allTasks = await benchmark.listTasks(manifest.benchmark.split);
  const tasks = selectTasks(allTasks, manifest.benchmark.task_selector);
  if (tasks.length === 0) throw new Error("Manifest selected zero tasks");
  const adapter = createSUTAdapter(manifest);
  const sut = await adapter.spec();
  if (sut.sut_id !== manifest.sut.id) {
    throw new Error(`Manifest SUT id ${manifest.sut.id} does not match adapter SUT id ${sut.sut_id}`);
  }
  if (manifest.execution.concurrency > sut.concurrency.max_workers) {
    throw new Error(
      `Requested concurrency ${manifest.execution.concurrency} exceeds SUT limit ${sut.concurrency.max_workers}`,
    );
  }
  for (const task of tasks) {
    if (task.track === "short_fact" && !sut.capabilities.short_fact) {
      throw new Error(`SUT cannot execute short fact task ${task.task_id}`);
    }
    if (task.track === "long_form" && !sut.capabilities.long_form) {
      throw new Error(`SUT cannot execute long form task ${task.task_id}`);
    }
  }
  const judgeProfile = manifest.evaluation.judge_profile
    ? await loadJudgeProfile(manifest.evaluation.judge_profile)
    : null;
  if (
    manifest.evaluation.run_official &&
    ["xbench-deepsearch", "browsecomp-zh"].includes(manifest.benchmark.id) &&
    !judgeProfile
  ) {
    throw new Error(`${manifest.benchmark.id} official grading requires evaluation.judge_profile`);
  }
  if (
    manifest.evaluation.run_official &&
    manifest.benchmark.id === "deepresearcheval" &&
    !manifest.evaluation.official_grader_command
  ) {
    throw new Error("DeepResearchEval official grading requires evaluation.official_grader_command");
  }
  return { tasks, sut, judgeProfile };
}
