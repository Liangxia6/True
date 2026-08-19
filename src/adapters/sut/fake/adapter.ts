import type { SUTAdapter, SUTRequest } from "../../../domains/research/contracts/adapters.js";
import {
  RawSUTResultSchema,
  SUTSpecSchema,
  type RawSUTResult,
  type SUTSpec,
} from "../../../schemas/contracts.js";

export class FakeResearchAdapter implements SUTAdapter {
  async openWorker(): Promise<void> {}

  async closeWorker(): Promise<void> {}

  async spec(): Promise<SUTSpec> {
    return SUTSpecSchema.parse({
      schema_version: "trueeval.sut.v0.1",
      sut_id: "fixture.fake.research",
      provider: "trueeval",
      product: "offline-fixture",
      channel: "fake",
      adapter_id: "trueeval.fake-research-adapter",
      adapter_version: "v0.1",
      account_tier: null,
      capabilities: {
        research_mode: true,
        short_fact: true,
        long_form: true,
        visible_citations: false,
        citation_urls: "none",
        file_output: false,
      },
      concurrency: {
        max_workers: 1,
        account_scoped: false,
      },
    });
  }

  async execute(request: SUTRequest): Promise<RawSUTResult> {
    const started = Date.now();
    const now = new Date().toISOString();
    await request.onSubmissionConfirmed({ transport: "fake", confirmed_at: now });
    return RawSUTResultSchema.parse({
      schema_version: "trueeval.raw_sut_result.v0.1",
      run_id: request.identity.runId,
      case_id: request.identity.caseId,
      attempt_id: request.identity.attemptId,
      task_id: request.task.task_id,
      sut_id: "fixture.fake.research",
      status: "completed",
      submitted_at: now,
      completed_at: new Date().toISOString(),
      raw_answer_text: `Fixture answer for ${request.task.task_id}: ${request.task.input.prompt}`,
      raw_citations: [],
      raw_response: null,
      screenshots: [],
      events: null,
      usage: {
        latency_ms: Date.now() - started,
        input_tokens: null,
        output_tokens: null,
        search_calls: null,
        cost_usd: null,
      },
      collection: {
        answer_status: "complete",
        citation_status: "product_absent",
      },
      error: null,
    });
  }
}
