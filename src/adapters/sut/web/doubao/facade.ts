import { mkdir } from "node:fs/promises";
import path from "node:path";

import { chromium, type BrowserContext, type Page } from "playwright";

import type { SUTAdapter, SUTRequest } from "../../../../domains/research/contracts/adapters.js";
import {
  RawSUTResultSchema,
  SUTSpecSchema,
  type RawSUTResult,
  type SUTSpec,
} from "../../../../schemas/contracts.js";
import { DoubaoAutomationError, DoubaoWebAdapter } from "./adapter.js";
import type { RunnerOptions } from "./types.js";

export interface DoubaoBatchOptions {
  sutId: string;
  profileDir: string;
  headless: boolean;
  browserChannel?: string;
  loginTimeoutSeconds: number;
  pollIntervalMs: number;
  stablePolls: number;
  allowAnonymous: boolean;
}

function executionStatus(code: string): RawSUTResult["status"] {
  if (code === "TIMEOUT") return "timeout";
  if (code === "SUBMISSION_UNCONFIRMED") return "submission_unconfirmed";
  if (code === "RESULT_EXTRACTION_FAILED") return "collection_failed";
  if (code === "PROVIDER_ERROR" || code === "LOGIN_REQUIRED" || code === "UI_CHANGED") {
    return "provider_error";
  }
  return "provider_error";
}

export class DoubaoBatchAdapter implements SUTAdapter {
  private context: BrowserContext | null = null;
  private page: Page | null = null;

  constructor(private readonly options: DoubaoBatchOptions) {}

  async spec(): Promise<SUTSpec> {
    return SUTSpecSchema.parse({
      schema_version: "trueeval.sut.v0.1",
      sut_id: this.options.sutId,
      provider: "doubao",
      product: "web_deep_research",
      channel: "web",
      adapter_id: "trueeval.doubao-web",
      adapter_version: "v0.2",
      account_tier: null,
      capabilities: {
        research_mode: true,
        short_fact: true,
        long_form: true,
        visible_citations: true,
        citation_urls: "visible_only",
        file_output: false,
      },
      concurrency: {
        max_workers: 1,
        account_scoped: true,
      },
    });
  }

  async openWorker(): Promise<void> {
    if (this.context) return;
    await mkdir(this.options.profileDir, { recursive: true });
    this.context = await chromium.launchPersistentContext(this.options.profileDir, {
      headless: this.options.headless,
      viewport: { width: 1440, height: 1000 },
      locale: "zh-CN",
      timezoneId: "Asia/Shanghai",
      ...(this.options.browserChannel ? { channel: this.options.browserChannel } : {}),
    });
    this.page = this.context.pages()[0] ?? (await this.context.newPage());
  }

  async closeWorker(): Promise<void> {
    const context = this.context;
    this.context = null;
    this.page = null;
    if (context) await context.close();
  }

  async execute(request: SUTRequest): Promise<RawSUTResult> {
    if (!this.page) throw new Error("Doubao worker is not open");
    await mkdir(request.artifactDirectory, { recursive: true });
    const started = Date.now();
    let submittedAt: string | null = null;
    const runnerOptions: RunnerOptions = {
      prompt: request.task.input.prompt,
      taskId: request.task.task_id,
      profileDir: this.options.profileDir,
      artifactsDir: request.artifactDirectory,
      timeoutSeconds: request.timeoutSeconds,
      loginTimeoutSeconds: this.options.loginTimeoutSeconds,
      pollIntervalMs: this.options.pollIntervalMs,
      stablePolls: this.options.stablePolls,
      headless: this.options.headless,
      keepOpen: true,
      researchMode: true,
      browserChannel: this.options.browserChannel,
      probeOnly: false,
      allowAnonymous: this.options.allowAnonymous,
    };
    const adapter = new DoubaoWebAdapter(this.page, runnerOptions, request.artifactDirectory);
    try {
      await adapter.open();
      await adapter.ensureLogin();
      await adapter.startCleanConversation();
      await adapter.selectResearchMode();
      await adapter.submitPrompt();
      submittedAt = new Date().toISOString();
      await request.onSubmissionConfirmed({
        transport: "browser_ui",
        confirmed_at: submittedAt,
      });
      const output = await adapter.waitForCompletion();
      return RawSUTResultSchema.parse({
        schema_version: "trueeval.raw_sut_result.v0.1",
        run_id: request.identity.runId,
        case_id: request.identity.caseId,
        attempt_id: request.identity.attemptId,
        task_id: request.task.task_id,
        sut_id: this.options.sutId,
        status: "completed",
        submitted_at: submittedAt,
        completed_at: new Date().toISOString(),
        raw_answer_text: output.answer,
        raw_citations: output.citations,
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
          citation_status: output.citations.length ? "collected" : "product_absent",
        },
        error: null,
      });
    } catch (error) {
      const code = error instanceof DoubaoAutomationError ? error.code : "UNEXPECTED_ERROR";
      const message = error instanceof Error ? error.message : String(error);
      await adapter.screenshot("error.png");
      return RawSUTResultSchema.parse({
        schema_version: "trueeval.raw_sut_result.v0.1",
        run_id: request.identity.runId,
        case_id: request.identity.caseId,
        attempt_id: request.identity.attemptId,
        task_id: request.task.task_id,
        sut_id: this.options.sutId,
        status: executionStatus(code),
        submitted_at: submittedAt,
        completed_at: new Date().toISOString(),
        raw_answer_text: null,
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
          answer_status: "not_observable",
          citation_status: "not_observable",
        },
        error: {
          code,
          message,
          retryable: code === "PROVIDER_ERROR" && !message.includes("登录"),
        },
      });
    }
  }

  async recoverExisting(request: SUTRequest): Promise<RawSUTResult | null> {
    if (!this.page) throw new Error("Doubao worker is not open");
    await mkdir(request.artifactDirectory, { recursive: true });
    const started = Date.now();
    const runnerOptions: RunnerOptions = {
      prompt: request.task.input.prompt,
      taskId: request.task.task_id,
      profileDir: this.options.profileDir,
      artifactsDir: request.artifactDirectory,
      timeoutSeconds: request.timeoutSeconds,
      loginTimeoutSeconds: this.options.loginTimeoutSeconds,
      pollIntervalMs: this.options.pollIntervalMs,
      stablePolls: this.options.stablePolls,
      headless: this.options.headless,
      keepOpen: true,
      researchMode: true,
      browserChannel: this.options.browserChannel,
      probeOnly: false,
      allowAnonymous: this.options.allowAnonymous,
    };
    const adapter = new DoubaoWebAdapter(this.page, runnerOptions, request.artifactDirectory);
    await adapter.open();
    await adapter.ensureLogin();
    if (!(await adapter.findExistingConversation())) return null;
    const submittedAt = new Date().toISOString();
    await request.onSubmissionConfirmed({ transport: "browser_ui_recovery", verified_at: submittedAt, url: this.page.url() });
    try {
      const output = await adapter.waitForCompletion();
      return RawSUTResultSchema.parse({ schema_version: "trueeval.raw_sut_result.v0.1", run_id: request.identity.runId, case_id: request.identity.caseId, attempt_id: request.identity.attemptId, task_id: request.task.task_id, sut_id: this.options.sutId, status: "completed", submitted_at: submittedAt, completed_at: new Date().toISOString(), raw_answer_text: output.answer, raw_citations: output.citations, raw_response: null, screenshots: [], events: null, usage: { latency_ms: Date.now() - started, input_tokens: null, output_tokens: null, search_calls: null, cost_usd: null }, collection: { answer_status: "complete", citation_status: output.citations.length ? "collected" : "product_absent" }, error: null });
    } catch (error) {
      const code = error instanceof DoubaoAutomationError ? error.code : "RECOVERY_ERROR";
      return RawSUTResultSchema.parse({ schema_version: "trueeval.raw_sut_result.v0.1", run_id: request.identity.runId, case_id: request.identity.caseId, attempt_id: request.identity.attemptId, task_id: request.task.task_id, sut_id: this.options.sutId, status: executionStatus(code), submitted_at: submittedAt, completed_at: new Date().toISOString(), raw_answer_text: null, raw_citations: [], raw_response: null, screenshots: [], events: null, usage: { latency_ms: Date.now() - started, input_tokens: null, output_tokens: null, search_calls: null, cost_usd: null }, collection: { answer_status: "not_observable", citation_status: "adapter_failed" }, error: { code, message: error instanceof Error ? error.message : String(error), retryable: false } });
    }
  }
}

export function doubaoOptionsFromManifest(input: {
  sutId: string;
  headless: boolean;
  options: Record<string, unknown>;
}): DoubaoBatchOptions {
  const stringOption = (key: string, fallback: string): string => {
    const value = input.options[key];
    if (value === undefined) return fallback;
    if (typeof value !== "string" || !value) throw new Error(`sut.options.${key} must be a string`);
    return value;
  };
  const numberOption = (key: string, fallback: number): number => {
    const value = input.options[key];
    if (value === undefined) return fallback;
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
      throw new Error(`sut.options.${key} must be a positive number`);
    }
    return value;
  };
  return {
    sutId: input.sutId,
    profileDir: path.resolve(stringOption("profile_dir", ".trueeval/profiles/doubao")),
    headless: input.headless,
    browserChannel: stringOption("browser_channel", "chrome"),
    loginTimeoutSeconds: numberOption("login_timeout_seconds", 300),
    pollIntervalMs: numberOption("poll_interval_ms", 5000),
    stablePolls: numberOption("stable_polls", 3),
    allowAnonymous: input.options.allow_anonymous === true,
  };
}
