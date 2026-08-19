import type { SUTAdapter, SUTRequest } from "../../../domains/research/contracts/adapters.js";
import { RawSUTResultSchema, SUTSpecSchema, type RawSUTResult, type RunManifest, type SUTSpec } from "../../../schemas/contracts.js";

interface HttpApiOptions { sutId: string; endpoint: string; apiKeyEnv: string | null; provider: string; product: string; headers: Record<string, string> }

export class HttpResearchAdapter implements SUTAdapter {
  constructor(private readonly options: HttpApiOptions) {}
  async spec(): Promise<SUTSpec> { return SUTSpecSchema.parse({ schema_version: "trueeval.sut.v0.1", sut_id: this.options.sutId, provider: this.options.provider, product: this.options.product, channel: "api", adapter_id: "trueeval.http-research", adapter_version: "v0.1", account_tier: null, capabilities: { research_mode: true, short_fact: true, long_form: true, visible_citations: true, citation_urls: "full", file_output: false }, concurrency: { max_workers: 1, account_scoped: false } }); }
  async openWorker(): Promise<void> {}
  async closeWorker(): Promise<void> {}
  async execute(request: SUTRequest): Promise<RawSUTResult> {
    const started = Date.now();
    let submittedAt: string | null = null;
    try {
      const apiKey = this.options.apiKeyEnv ? process.env[this.options.apiKeyEnv] : null;
      if (this.options.apiKeyEnv && !apiKey) throw new Error(`Missing SUT API key environment variable: ${this.options.apiKeyEnv}`);
      const response = await fetch(this.options.endpoint, { method: "POST", headers: { "content-type": "application/json", ...this.options.headers, ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) }, body: JSON.stringify({ schema_version: "trueeval.http_research_request.v0.1", task_id: request.task.task_id, prompt: request.task.input.prompt, language: request.task.input.language, as_of: request.task.input.as_of, timeout_seconds: request.timeoutSeconds }), signal: AbortSignal.timeout(request.timeoutSeconds * 1000) });
      const raw = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(`HTTP SUT ${response.status}: ${JSON.stringify(raw).slice(0, 500)}`);
      submittedAt = new Date().toISOString();
      await request.onSubmissionConfirmed({ transport: "http_api", request_id: typeof raw.request_id === "string" ? raw.request_id : null });
      if (typeof raw.answer !== "string") throw new Error("HTTP SUT response.answer must be a string");
      return RawSUTResultSchema.parse({ schema_version: "trueeval.raw_sut_result.v0.1", run_id: request.identity.runId, case_id: request.identity.caseId, attempt_id: request.identity.attemptId, task_id: request.task.task_id, sut_id: this.options.sutId, status: "completed", submitted_at: submittedAt, completed_at: new Date().toISOString(), raw_answer_text: raw.answer, raw_citations: Array.isArray(raw.citations) ? raw.citations : [], raw_response: null, screenshots: [], events: null, usage: { latency_ms: Date.now() - started, input_tokens: typeof raw.input_tokens === "number" ? raw.input_tokens : null, output_tokens: typeof raw.output_tokens === "number" ? raw.output_tokens : null, search_calls: typeof raw.search_calls === "number" ? raw.search_calls : null, cost_usd: typeof raw.cost_usd === "number" ? raw.cost_usd : null }, collection: { answer_status: "complete", citation_status: Array.isArray(raw.citations) && raw.citations.length ? "collected" : "product_absent" }, error: null });
    } catch (error) {
      const timeout = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
      return RawSUTResultSchema.parse({ schema_version: "trueeval.raw_sut_result.v0.1", run_id: request.identity.runId, case_id: request.identity.caseId, attempt_id: request.identity.attemptId, task_id: request.task.task_id, sut_id: this.options.sutId, status: timeout ? "timeout" : submittedAt ? "collection_failed" : "provider_error", submitted_at: submittedAt, completed_at: new Date().toISOString(), raw_answer_text: null, raw_citations: [], raw_response: null, screenshots: [], events: null, usage: { latency_ms: Date.now() - started, input_tokens: null, output_tokens: null, search_calls: null, cost_usd: null }, collection: { answer_status: "not_observable", citation_status: "not_observable" }, error: { code: timeout ? "TIMEOUT" : "HTTP_SUT_ERROR", message: error instanceof Error ? error.message : String(error), retryable: true } });
    }
  }
}

export function httpOptionsFromManifest(manifest: RunManifest): HttpApiOptions {
  const endpoint = manifest.sut.options.endpoint;
  if (typeof endpoint !== "string" || !/^https?:\/\//.test(endpoint)) throw new Error("sut.options.endpoint must be an HTTP(S) URL");
  const headers = manifest.sut.options.headers;
  if (headers !== undefined && (typeof headers !== "object" || headers === null || Array.isArray(headers) || Object.values(headers).some((value) => typeof value !== "string"))) throw new Error("sut.options.headers must contain only string values");
  if (headers && Object.keys(headers).some((key) => /^(authorization|proxy-authorization|x-api-key)$/i.test(key))) {
    throw new Error("Sensitive HTTP headers are forbidden in Manifest; use sut.options.api_key_env");
  }
  return { sutId: manifest.sut.id, endpoint, apiKeyEnv: typeof manifest.sut.options.api_key_env === "string" ? manifest.sut.options.api_key_env : null, provider: typeof manifest.sut.options.provider === "string" ? manifest.sut.options.provider : "external", product: typeof manifest.sut.options.product === "string" ? manifest.sut.options.product : "research-api", headers: (headers ?? {}) as Record<string, string> };
}
