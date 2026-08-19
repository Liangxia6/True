#!/usr/bin/env node
import path from "node:path";
import process from "node:process";

import { loadManifest, resolveManifestPaths } from "../core/config/manifest.js";
import { gradeOfflineRun } from "../core/grading/runner.js";
import { calibrateCitationFile } from "../core/grading/citation-calibration.js";
import { resumeEvaluation, runEvaluation } from "../core/orchestrator/offline-runner.js";
import {
  recoverDoubaoSubmissions,
  refreshDoubaoCitations,
} from "../core/orchestrator/doubao-recovery.js";
import { generateRunReport } from "../core/reporting/report.js";
import { StateDatabase } from "../core/storage/database.js";
import { validateRunManifest } from "../core/validation/manifest-validator.js";

function usage(): string {
  return `
TrueEval Research MVP

用法：
  npm run trueeval -- validate --manifest <file>
  npm run trueeval -- run --manifest <file>
  npm run trueeval -- resume --run-id <id> [--state-db <file>] [--artifacts-root <dir>]
  npm run trueeval -- recover-doubao --run-id <id> [--state-db <file>] [--artifacts-root <dir>]
  npm run trueeval -- refresh-doubao-citations --run-id <id> [--state-db <file>] [--artifacts-root <dir>]
  npm run trueeval -- grade --run-id <id> [--state-db <file>] [--artifacts-root <dir>]
  npm run trueeval -- report --run-id <id> [--state-db <file>] [--artifacts-root <dir>]
  npm run trueeval -- status --run-id <id> [--state-db <file>]
  npm run trueeval -- calibrate-citations --input <jsonl>

SUT 支持 Fake、豆包 Web、通用 HTTP API 和 Process Agent。真实评分必须配置 Judge Profile；Fake Judge 仅用于 fixture benchmark。
`;
}

function argsMap(argv: string[]): Map<string, string | boolean> {
  const result = new Map<string, string | boolean>();
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token?.startsWith("--")) continue;
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) result.set(token, true);
    else {
      result.set(token, next);
      index += 1;
    }
  }
  return result;
}

function stringArg(args: Map<string, string | boolean>, key: string, fallback?: string): string {
  const value = args.get(key);
  if (typeof value === "string") return value;
  if (fallback !== undefined) return fallback;
  throw new Error(`Missing required argument: ${key}`);
}

async function manifestFromArgs(args: Map<string, string | boolean>) {
  return resolveManifestPaths(await loadManifest(stringArg(args, "--manifest")));
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  if (!command || command === "--help" || command === "help") {
    process.stdout.write(usage());
    return;
  }
  const args = argsMap(rest);
  if (command === "validate") {
    const manifest = await manifestFromArgs(args);
    const result = await validateRunManifest(manifest);
    process.stdout.write(
      `${JSON.stringify({ valid: true, tasks: result.tasks.length, sut: result.sut.sut_id }, null, 2)}\n`,
    );
    return;
  }
  if (command === "run") {
    const manifest = await manifestFromArgs(args);
    const result = await runEvaluation(manifest);
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (command === "calibrate-citations") {
    const result = await calibrateCitationFile(path.resolve(stringArg(args, "--input")));
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }

  const runId = stringArg(args, "--run-id");
  const stateDatabase = path.resolve(stringArg(args, "--state-db", ".trueeval/state.db"));
  const artifactsRoot = path.resolve(stringArg(args, "--artifacts-root", "artifacts/runs"));
  if (command === "resume") {
    const result = await resumeEvaluation({ runId, stateDatabase, artifactsRoot });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (command === "recover-doubao") {
    const result = await recoverDoubaoSubmissions({ runId, stateDatabase, artifactsRoot });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (command === "refresh-doubao-citations") {
    const result = await refreshDoubaoCitations({ runId, stateDatabase, artifactsRoot });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (command === "grade") {
    const result = await gradeOfflineRun({ runId, stateDatabase, artifactsRoot });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (command === "report") {
    const result = await generateRunReport({ runId, stateDatabase, artifactsRoot });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (command === "status") {
    const database = new StateDatabase(stateDatabase);
    try {
      const run = database.getRun(runId);
      if (!run) throw new Error(`Unknown run: ${runId}`);
      const cases = database.listCases(runId);
      process.stdout.write(`${JSON.stringify({ run, cases }, null, 2)}\n`);
    } finally {
      database.close();
    }
    return;
  }
  throw new Error(`Unknown command: ${command}\n${usage()}`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 10;
});
