import { readFile } from "node:fs/promises";
import path from "node:path";

import { parse } from "yaml";

import { RunManifestSchema, type RunManifest } from "../../schemas/contracts.js";

export async function loadManifest(filePath: string): Promise<RunManifest> {
  const absolute = path.resolve(filePath);
  const source = await readFile(absolute, "utf8");
  const parsed = parse(source) as unknown;
  return RunManifestSchema.parse(parsed);
}

export function resolveManifestPaths(manifest: RunManifest, cwd = process.cwd()): RunManifest {
  return {
    ...manifest,
    benchmark: {
      ...manifest.benchmark,
      root: path.resolve(cwd, manifest.benchmark.root),
    },
    artifacts: {
      ...manifest.artifacts,
      root: path.resolve(cwd, manifest.artifacts.root),
    },
    state: {
      database: path.resolve(cwd, manifest.state.database),
    },
    evaluation: {
      ...manifest.evaluation,
      judge_profile: manifest.evaluation.judge_profile
        ? path.resolve(cwd, manifest.evaluation.judge_profile)
        : null,
    },
  };
}
