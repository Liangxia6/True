import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { ArtifactStore } from "../../../src/core/storage/artifact-store.js";

test("ArtifactStore writes atomically and records a hash", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "trueeval-artifact-"));
  try {
    const store = new ArtifactStore(temporary);
    const ref = await store.writeJson("case/result.json", "fixture", { ok: true });
    assert.match(ref.sha256, /^sha256:[a-f0-9]{64}$/);
    assert.equal(ref.uri, "case/result.json");
    assert.deepEqual(JSON.parse(await readFile(path.join(temporary, ref.uri), "utf8")), { ok: true });
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

test("ArtifactStore rejects path traversal", () => {
  const store = new ArtifactStore(path.join(os.tmpdir(), "trueeval-artifact-root"));
  assert.throws(() => store.resolve("../secret.txt"), /escapes run root/);
  assert.throws(() => store.resolve("/tmp/secret.txt"), /relative path/);
});
