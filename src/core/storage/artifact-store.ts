import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import type { ArtifactRef } from "../../schemas/contracts.js";
import { sha256Text } from "../utils/hash.js";

function assertSafeRelativePath(relativePath: string): void {
  if (!relativePath || path.isAbsolute(relativePath)) {
    throw new Error("Artifact path must be a non-empty relative path");
  }
  const normalized = path.normalize(relativePath);
  if (normalized === ".." || normalized.startsWith(`..${path.sep}`)) {
    throw new Error(`Artifact path escapes run root: ${relativePath}`);
  }
}

export class ArtifactStore {
  readonly root: string;

  constructor(root: string) {
    this.root = path.resolve(root);
  }

  resolve(relativePath: string): string {
    assertSafeRelativePath(relativePath);
    const absolute = path.resolve(this.root, relativePath);
    if (absolute !== this.root && !absolute.startsWith(`${this.root}${path.sep}`)) {
      throw new Error(`Artifact path escapes run root: ${relativePath}`);
    }
    return absolute;
  }

  async writeJson(relativePath: string, kind: string, value: unknown): Promise<ArtifactRef> {
    return this.writeText(relativePath, kind, `${JSON.stringify(value, null, 2)}\n`, "application/json");
  }

  async writeText(
    relativePath: string,
    kind: string,
    value: string,
    mediaType = "text/plain; charset=utf-8",
  ): Promise<ArtifactRef> {
    const target = this.resolve(relativePath);
    await mkdir(path.dirname(target), { recursive: true });
    const temporary = `${target}.${randomUUID()}.tmp`;
    await writeFile(temporary, value, "utf8");
    await rename(temporary, target);
    return this.reference(relativePath, kind, mediaType);
  }

  async reference(relativePath: string, kind: string, mediaType: string): Promise<ArtifactRef> {
    const target = this.resolve(relativePath);
    const [bytes, metadata] = await Promise.all([readFile(target), stat(target)]);
    return {
      artifact_id: randomUUID(),
      kind,
      uri: relativePath.split(path.sep).join("/"),
      media_type: mediaType,
      sha256: sha256Text(bytes),
      size_bytes: metadata.size,
    };
  }

  async readJson<T>(relativePath: string): Promise<T> {
    return JSON.parse(await readFile(this.resolve(relativePath), "utf8")) as T;
  }

  async readText(relativePath: string): Promise<string> {
    return readFile(this.resolve(relativePath), "utf8");
  }
}
