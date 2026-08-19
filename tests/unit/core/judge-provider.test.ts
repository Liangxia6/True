import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";

import { JudgeProfileSchema } from "../../../src/schemas/contracts.js";
import {
  OpenAICompatibleJudgeProvider,
  ProcessJudgeProvider,
} from "../../../src/core/grading/judge/provider.js";

test("OpenAI-compatible Judge sends the configured model and secret only in Authorization", async () => {
  let body: Record<string, unknown> = {};
  let authorization = "";
  const server = createServer((request, response) => {
    authorization = request.headers.authorization ?? "";
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ model: "actual-model", choices: [{ message: { content: "ok" } }], usage: { prompt_tokens: 3, completion_tokens: 1 } }));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  process.env.TRUEEVAL_TEST_JUDGE_KEY = "test-secret-never-persist";
  try {
    const profile = JudgeProfileSchema.parse({ schema_version: "trueeval.judge_profile.v0.1", judge_profile_id: "test", transport: "openai_compatible", base_url: `http://127.0.0.1:${address.port}/v1`, api_key_env: "TRUEEVAL_TEST_JUDGE_KEY", model: "requested-model", temperature: 0, seed: null, max_output_tokens: 50, timeout_seconds: 2, max_retries: 0 });
    const result = await new OpenAICompatibleJudgeProvider(profile).invoke({ system: "s", user: "u" });
    assert.equal(result.text, "ok");
    assert.equal(result.actualModel, "actual-model");
    assert.equal(body.model, "requested-model");
    assert.equal(authorization, "Bearer test-secret-never-persist");
    assert(!JSON.stringify(body).includes("test-secret-never-persist"));
  } finally {
    delete process.env.TRUEEVAL_TEST_JUDGE_KEY;
    server.close();
  }
});

test("Process Judge obeys the JSON stdin/stdout protocol", async () => {
  const profile = JudgeProfileSchema.parse({ schema_version: "trueeval.judge_profile.v0.1", judge_profile_id: "process-test", transport: "process", command: [process.execPath, "tests/fixtures/judge-process.mjs"], model: "fixture", temperature: 0, seed: null, max_output_tokens: 100, timeout_seconds: 5, max_retries: 0 });
  const result = await new ProcessJudgeProvider(profile).invoke({ system: "s", user: "plain" });
  assert.match(result.text, /结论: 正确/);
  assert.equal(result.actualModel, "fixture-judge-v1");
});
