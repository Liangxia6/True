import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";

import { HttpResearchAdapter } from "../../../src/adapters/sut/api/http-adapter.js";
import { TaskSpecSchema } from "../../../src/schemas/contracts.js";

test("HTTP API adapter sends only public task input and returns normalized raw output", async () => {
  let requestBody: Record<string, unknown> = {};
  const server = createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      requestBody = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ request_id: "req-1", answer: "API answer", citations: [{ citation_id: "c1", url: "https://example.com", title: "Example" }] }));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  const adapter = new HttpResearchAdapter({ sutId: "api.test", endpoint: `http://127.0.0.1:${address.port}`, apiKeyEnv: null, provider: "fixture", product: "research", headers: {} });
  const task = TaskSpecSchema.parse({ schema_version: "trueeval.task.v0.1", task_id: "t", benchmark_id: "b", split: "s", domain: "research", track: "short_fact", input: { prompt: "Question", language: "en", as_of: null, attachments: [] }, expected_output: { answer_form: "short_text", citation_required: true }, required_capabilities: [], constraints: { timeout_seconds: 5, internet_required: true, max_attempts: 1 }, evaluation_profile: { official_grader: null, overlays: [] }, provenance: {} });
  let confirmed = false;
  try {
    const result = await adapter.execute({ identity: { runId: "r", caseId: "c", attemptId: "a" }, task, timeoutSeconds: 5, artifactDirectory: "/tmp/unused", onSubmissionConfirmed: async () => { confirmed = true; } });
    assert.equal(result.status, "completed");
    assert.equal(result.raw_answer_text, "API answer");
    assert.equal(result.raw_citations.length, 1);
    assert.equal(confirmed, true);
    assert.equal(requestBody.prompt, "Question");
    assert(!("gold" in requestBody));
  } finally { server.close(); }
});
