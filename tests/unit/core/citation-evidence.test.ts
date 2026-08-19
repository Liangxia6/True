import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { ArtifactStore } from "../../../src/core/storage/artifact-store.js";
import { resolveEvidence } from "../../../src/domains/research/citations/evidence-resolver.js";
import { assertPublicHttpUrl } from "../../../src/domains/research/citations/url-security.js";

test("Evidence URL guard rejects private and unsafe destinations", async () => {
  await assert.rejects(assertPublicHttpUrl("http://127.0.0.1/private"), /EVIDENCE_PRIVATE_HOST/);
  await assert.rejects(assertPublicHttpUrl("file:///etc/passwd"), /EVIDENCE_UNSAFE_SCHEME/);
});

test("Evidence Resolver snapshots fetched HTML and detects a paywall", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "trueeval-evidence-"));
  const store = new ArtifactStore(root);
  const citation = { citation_id: "c1", display_text: null, visible_url: "https://example.com/a", resolved_url: null, quoted_text: null, claim_ids: [], collection_status: "visible_only" as const };
  const fetched = await resolveEvidence({ citation, store, outputRoot: "one", fetchImpl: async () => new Response("<title>Evidence</title><p>Public fact.</p>", { status: 200, headers: { "content-type": "text/html" } }) });
  assert.equal(fetched.status, "fetched");
  assert.equal(fetched.title, "Evidence");
  assert(fetched.text_artifact);
  const paywalled = await resolveEvidence({ citation, store, outputRoot: "two", fetchImpl: async () => new Response("Subscribe to continue", { status: 200, headers: { "content-type": "text/html" } }) });
  assert.equal(paywalled.status, "paywalled");
  assert.equal(paywalled.text_artifact, null);
});
