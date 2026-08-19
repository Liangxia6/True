import { spawn } from "node:child_process";

import type { SUTAdapter, SUTRequest } from "../../../domains/research/contracts/adapters.js";
import {
  RawSUTResultSchema,
  SUTSpecSchema,
  type RawSUTResult,
  type RunManifest,
  type SUTSpec,
} from "../../../schemas/contracts.js";

interface ProcessOptions {
  sutId: string;
  command: string[];
  provider: string;
  product: string;
}

export class ProcessResearchAdapter implements SUTAdapter {
  constructor(private readonly options: ProcessOptions) {}

  async spec(): Promise<SUTSpec> {
    return SUTSpecSchema.parse({
      schema_version: "trueeval.sut.v0.1",
      sut_id: this.options.sutId,
      provider: this.options.provider,
      product: this.options.product,
      channel: "process",
      adapter_id: "trueeval.process-jsonl",
      adapter_version: "v0.1",
      account_tier: null,
      capabilities: { research_mode: true, short_fact: true, long_form: true, visible_citations: true, citation_urls: "full", file_output: true },
      concurrency: { max_workers: 1, account_scoped: false },
    });
  }

  async openWorker(): Promise<void> {}
  async closeWorker(): Promise<void> {}

  async execute(request: SUTRequest): Promise<RawSUTResult> {
    const [executable, ...args] = this.options.command;
    if (!executable) throw new Error("Process SUT command is empty");
    const started = Date.now();
    let submittedAt: string | null = null;
    return new Promise((resolve) => {
      const child = spawn(executable, args, {
        shell: false,
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env, TRUEEVAL_ARTIFACT_DIR: request.artifactDirectory },
      });
      let stdout = "";
      const stderr: Buffer[] = [];
      let final: Record<string, unknown> | null = null;
      let settled = false;
      const complete = (result: RawSUTResult) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        resolve(result);
      };
      const failure = (code: string, message: string, status: RawSUTResult["status"] = "provider_error") => complete(RawSUTResultSchema.parse({
        schema_version: "trueeval.raw_sut_result.v0.1", run_id: request.identity.runId, case_id: request.identity.caseId, attempt_id: request.identity.attemptId, task_id: request.task.task_id, sut_id: this.options.sutId,
        status, submitted_at: submittedAt, completed_at: new Date().toISOString(), raw_answer_text: null, raw_citations: [], raw_response: null, screenshots: [], events: null,
        usage: { latency_ms: Date.now() - started, input_tokens: null, output_tokens: null, search_calls: null, cost_usd: null },
        collection: { answer_status: "not_observable", citation_status: "not_observable" }, error: { code, message, retryable: status === "provider_error" },
      }));
      const handleLine = async (line: string) => {
        if (!line.trim()) return;
        const event = JSON.parse(line) as Record<string, unknown>;
        if (event.event === "submission_confirmed") {
          if (submittedAt) throw new Error("Process SUT confirmed submission more than once");
          submittedAt = new Date().toISOString();
          await request.onSubmissionConfirmed({ transport: "process_jsonl", ...(typeof event.detail === "object" && event.detail ? event.detail : {}) });
        } else if (event.event === "result") final = event;
      };
      let chain = Promise.resolve();
      child.stdout.on("data", (chunk: Buffer) => {
        stdout += chunk.toString("utf8");
        const lines = stdout.split(/\r?\n/);
        stdout = lines.pop() ?? "";
        for (const line of lines) chain = chain.then(() => handleLine(line));
      });
      child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
      child.on("error", (error) => failure("PROCESS_SPAWN_FAILED", error.message));
      child.on("close", (exitCode) => {
        chain = chain.then(() => handleLine(stdout));
        chain.then(() => {
          if (settled) return;
          if (exitCode !== 0) return failure("PROCESS_EXIT_NONZERO", Buffer.concat(stderr).toString("utf8").slice(0, 2000));
          if (!submittedAt) return failure("SUBMISSION_UNCONFIRMED", "Process did not emit submission_confirmed", "submission_unconfirmed");
          if (!final || typeof final.answer !== "string") return failure("PROCESS_RESULT_INVALID", "Process did not emit a valid result", "collection_failed");
          complete(RawSUTResultSchema.parse({
            schema_version: "trueeval.raw_sut_result.v0.1", run_id: request.identity.runId, case_id: request.identity.caseId, attempt_id: request.identity.attemptId, task_id: request.task.task_id, sut_id: this.options.sutId,
            status: "completed", submitted_at: submittedAt, completed_at: new Date().toISOString(), raw_answer_text: final.answer,
            raw_citations: Array.isArray(final.citations) ? final.citations : [], raw_response: null, screenshots: [], events: null,
            usage: { latency_ms: Date.now() - started, input_tokens: null, output_tokens: null, search_calls: typeof final.search_calls === "number" ? final.search_calls : null, cost_usd: typeof final.cost_usd === "number" ? final.cost_usd : null },
            collection: { answer_status: "complete", citation_status: Array.isArray(final.citations) && final.citations.length ? "collected" : "product_absent" }, error: null,
          }));
        }).catch((error: unknown) => failure("PROCESS_PROTOCOL_ERROR", error instanceof Error ? error.message : String(error), "collection_failed"));
      });
      const timeout = setTimeout(() => {
        child.kill("SIGTERM");
        failure("TIMEOUT", `Process SUT timed out after ${request.timeoutSeconds}s`, "timeout");
      }, request.timeoutSeconds * 1000);
      child.stdin.end(JSON.stringify({ schema_version: "trueeval.sut_process_request.v0.1", identity: request.identity, task: request.task, timeout_seconds: request.timeoutSeconds }));
    });
  }
}

export function processOptionsFromManifest(manifest: RunManifest): ProcessOptions {
  const command = manifest.sut.options.command;
  if (!Array.isArray(command) || command.some((part) => typeof part !== "string" || !part)) {
    throw new Error("sut.options.command must be a non-empty string array for process adapter");
  }
  if (!command.length) throw new Error("sut.options.command must not be empty");
  return {
    sutId: manifest.sut.id,
    command: command as string[],
    provider: typeof manifest.sut.options.provider === "string" ? manifest.sut.options.provider : "external",
    product: typeof manifest.sut.options.product === "string" ? manifest.sut.options.product : "research-agent",
  };
}
