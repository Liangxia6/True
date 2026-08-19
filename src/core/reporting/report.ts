import path from "node:path";

import { ArtifactStore } from "../storage/artifact-store.js";
import { StateDatabase } from "../storage/database.js";

export interface RunReport {
  schema_version: "trueeval.report.v0.1";
  run_id: string;
  run_status: string;
  benchmark_id: string;
  sut: { id: string; adapter: string; channel: string };
  cases: {
    total: number;
    done: number;
    system_failures: number;
  };
  metrics: Record<string, { scored: number; mean: number | null; statuses: Record<string, number> }>;
  generated_at: string;
}

export async function generateRunReport(input: {
  runId: string;
  artifactsRoot: string;
  stateDatabase: string;
}): Promise<RunReport> {
  const database = new StateDatabase(input.stateDatabase);
  const store = new ArtifactStore(path.join(input.artifactsRoot, input.runId));
  try {
    const run = database.getRun(input.runId);
    if (!run) throw new Error(`Unknown run: ${input.runId}`);
    const cases = database.listCases(input.runId);
    const scores = database.listScores(input.runId);
    const lock = await store.readJson<{ manifest: { benchmark: { id: string }; sut: { id: string; adapter: string } }; sut: { channel: string } }>(run.manifest_uri);
    const grouped = new Map<string, number[]>();
    const statusCounts = new Map<string, Record<string, number>>();
    for (const score of scores) {
      const counts = statusCounts.get(score.metric_id) ?? {};
      counts[score.status] = (counts[score.status] ?? 0) + 1;
      statusCounts.set(score.metric_id, counts);
      if (score.status !== "scored" || score.value_json === null) continue;
      const value = JSON.parse(score.value_json) as unknown;
      if (typeof value !== "number") continue;
      const values = grouped.get(score.metric_id) ?? [];
      values.push(value);
      grouped.set(score.metric_id, values);
    }
    const metrics = Object.fromEntries(
      [...new Set([...grouped.keys(), ...statusCounts.keys()])].map((metric) => {
        const values = grouped.get(metric) ?? [];
        return [metric, { scored: values.length, mean: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null, statuses: statusCounts.get(metric) ?? {} }];
      }),
    );
    const report: RunReport = {
      schema_version: "trueeval.report.v0.1",
      run_id: input.runId,
      run_status: run.status,
      benchmark_id: lock.manifest.benchmark.id,
      sut: { id: lock.manifest.sut.id, adapter: lock.manifest.sut.adapter, channel: lock.sut.channel },
      cases: {
        total: cases.length,
        done: cases.filter((entry) => entry.status === "DONE").length,
        system_failures: cases.filter((entry) => !["DONE", "READY_FOR_GRADING"].includes(entry.status)).length,
      },
      metrics,
      generated_at: new Date().toISOString(),
    };
    await store.writeJson("report.json", "run_report", report);
    const metricLines = Object.entries(metrics).map(
      ([metric, value]) => `| ${metric} | ${value.scored} | ${value.mean ?? "not_observable"} | ${JSON.stringify(value.statuses)} |`,
    );
    await store.writeText(
      "report.md",
      "run_report_markdown",
      [
        `# TrueEval Run ${input.runId}`,
        "",
        `- Run status: ${run.status}`,
        `- Benchmark: ${report.benchmark_id}`,
        `- SUT: ${report.sut.id} (${report.sut.channel}/${report.sut.adapter})`,
        `- Cases: ${report.cases.done}/${report.cases.total} done`,
        `- System failures: ${report.cases.system_failures}`,
        "",
        "| Metric | Scored cases | Mean | Statuses |",
        "|---|---:|---:|---|",
        ...metricLines,
        "",
      ].join("\n"),
        "text/markdown; charset=utf-8",
    );
    return report;
  } finally {
    database.close();
  }
}
