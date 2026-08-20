#!/usr/bin/env node
import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { chromium, type BrowserContext } from "playwright";

import {
  DoubaoAutomationError,
  DoubaoWebAdapter,
  ENTRY_URL,
} from "../adapters/sut/web/doubao/adapter.js";
import { sanitizePathSegment } from "../adapters/sut/web/doubao/text.js";
import type {
  DoubaoRunResult,
  RunnerOptions,
  RunStatus,
} from "../adapters/sut/web/doubao/types.js";

function usage(): string {
  return `
用法：
  npm run doubao -- --prompt "你的研究问题"
  npm run doubao -- --prompt-file ./question.txt --task-id demo-001

参数：
  --prompt <text>                 提示词，与 --prompt-file 二选一
  --prompt-file <path>            从 UTF-8 文件读取提示词
  --task-id <id>                  任务 ID，默认 doubao-<timestamp>
  --timeout-seconds <n>           输出等待时间，默认 2700
  --login-timeout-seconds <n>     人工登录等待时间，默认 300
  --profile-dir <path>            浏览器 Profile，默认 .trueeval/profiles/doubao
  --artifacts-dir <path>          结果根目录，默认 artifacts/doubao
  --poll-interval-ms <n>          轮询间隔，默认 5000
  --stable-polls <n>              内容连续稳定次数，默认 3
  --browser-channel <name>        浏览器通道，默认 chrome
  --headless                      无头运行；首次登录不建议
  --keep-open                     结束后保留浏览器，便于调试
  --chat-mode                     使用普通对话，不选择“深入研究”
  --probe-only                    只验证页面和研究模式，不发送提示词
  --allow-anonymous               允许未登录探测；实际发送仍可能被豆包终止
  --help                          显示帮助
`;
}

function argMap(argv: string[]): Map<string, string | boolean> {
  const result = new Map<string, string | boolean>();
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token?.startsWith("--")) continue;
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) result.set(token, true);
    else {
      result.set(token, next);
      i += 1;
    }
  }
  return result;
}

function stringArg(args: Map<string, string | boolean>, key: string): string | undefined {
  const value = args.get(key);
  return typeof value === "string" ? value : undefined;
}

function positiveNumber(value: string | undefined, fallback: number, name: string): number {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${name} 必须是正数。`);
  }
  return parsed;
}

async function optionsFromArgv(argv: string[]): Promise<RunnerOptions> {
  const args = argMap(argv);
  if (args.has("--help")) {
    process.stdout.write(usage());
    process.exit(0);
  }

  const promptFile = stringArg(args, "--prompt-file");
  const promptArg = stringArg(args, "--prompt");
  if (Boolean(promptFile) === Boolean(promptArg)) {
    throw new Error("必须且只能提供 --prompt 或 --prompt-file。\n" + usage());
  }
  const prompt = (promptFile ? await readFile(path.resolve(promptFile), "utf8") : promptArg)!.trim();
  if (!prompt) throw new Error("提示词不能为空。");

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  return {
    prompt,
    taskId: stringArg(args, "--task-id") ?? `doubao-${timestamp}`,
    profileDir: path.resolve(
      stringArg(args, "--profile-dir") ?? ".trueeval/profiles/doubao",
    ),
    artifactsDir: path.resolve(
      stringArg(args, "--artifacts-dir") ?? "artifacts/doubao",
    ),
    timeoutSeconds: positiveNumber(
      stringArg(args, "--timeout-seconds"),
      2700,
      "--timeout-seconds",
    ),
    loginTimeoutSeconds: positiveNumber(
      stringArg(args, "--login-timeout-seconds"),
      300,
      "--login-timeout-seconds",
    ),
    pollIntervalMs: positiveNumber(
      stringArg(args, "--poll-interval-ms"),
      5000,
      "--poll-interval-ms",
    ),
    stablePolls: positiveNumber(stringArg(args, "--stable-polls"), 3, "--stable-polls"),
    headless: args.has("--headless"),
    keepOpen: args.has("--keep-open"),
    researchMode: !args.has("--chat-mode"),
    browserChannel: stringArg(args, "--browser-channel") ?? "chrome",
    probeOnly: args.has("--probe-only"),
    allowAnonymous: args.has("--allow-anonymous"),
  };
}

function statusFromCode(code: string): RunStatus {
  if (code === "LOGIN_REQUIRED") return "login_required";
  if (code === "TIMEOUT") return "timeout";
  if (code === "PROVIDER_ERROR") return "provider_error";
  if (code === "SUBMISSION_UNCONFIRMED") return "submission_unconfirmed";
  if (code === "RESULT_EXTRACTION_FAILED") return "result_extraction_failed";
  return "ui_changed";
}

async function launch(options: RunnerOptions): Promise<BrowserContext> {
  await mkdir(options.profileDir, { recursive: true });
  const launchOptions = {
    headless: options.headless,
    viewport: { width: 1440, height: 1000 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
  };
  return chromium.launchPersistentContext(options.profileDir, {
    ...launchOptions,
    ...(options.browserChannel ? { channel: options.browserChannel } : {}),
  });
}

async function main(): Promise<void> {
  const options = await optionsFromArgv(process.argv.slice(2));
  const runId = randomUUID();
  const resultDir = path.join(
    options.artifactsDir,
    `${sanitizePathSegment(options.taskId)}-${runId}`,
  );
  await mkdir(resultDir, { recursive: true });
  await writeFile(
    path.join(resultDir, "request.json"),
    JSON.stringify(
      {
        schema_version: "trueeval.research_request.v0.1",
        run_id: runId,
        task_id: options.taskId,
        prompt: options.prompt,
        requested_at: new Date().toISOString(),
        research_mode: options.researchMode,
      },
      null,
      2,
    ),
    "utf8",
  );

  const started = Date.now();
  let context: BrowserContext | null = null;
  let adapter: DoubaoWebAdapter | null = null;
  let result: DoubaoRunResult;

  try {
    context = await launch(options);
    const pages = context.pages();
    const page = pages[0] ?? (await context.newPage());
    adapter = new DoubaoWebAdapter(page, options, resultDir);
    await adapter.open();
    await adapter.ensureLogin();
    await adapter.ensurePersonalChat();
    await adapter.startCleanConversation();
    await adapter.selectResearchMode();
    const output = options.probeOnly
      ? null
      : await (async () => {
          await adapter.submitPrompt();
          return adapter.waitForCompletion();
        })();

    result = {
      schema_version: "trueeval.research_answer.v0.1",
      run_id: runId,
      task_id: options.taskId,
      status: options.probeOnly ? "probe_completed" : "completed",
      final_answer: output?.answer ?? null,
      citations: output?.citations ?? [],
      artifacts: {
        result_dir: resultDir,
        raw_html_uri: output ? path.join(resultDir, "response.raw.html") : null,
        final_markdown_uri: output ? path.join(resultDir, "response.visible.md") : null,
        screenshot_uri: path.join(
          resultDir,
          output ? "04-completed.png" : "01-research-mode.png",
        ),
        events_uri: path.join(resultDir, "events.jsonl"),
      },
      usage: {
        latency_ms: Date.now() - started,
        input_tokens: null,
        output_tokens: null,
        search_calls: null,
        cost_usd: null,
      },
      sut: {
        provider: "doubao",
        product: options.researchMode ? "web_deep_research" : "web_chat",
        model: null,
        endpoint_family: "browser_ui",
        parameters: {
          entry_url: ENTRY_URL,
          browser_channel: options.browserChannel ?? null,
          research_mode_requested: options.researchMode,
        },
      },
      error: null,
    };
  } catch (error) {
    const code = error instanceof DoubaoAutomationError ? error.code : "UNEXPECTED_ERROR";
    const message = error instanceof Error ? error.message : String(error);
    if (adapter) await adapter.screenshot("error.png");
    result = {
      schema_version: "trueeval.research_answer.v0.1",
      run_id: runId,
      task_id: options.taskId,
      status: statusFromCode(code),
      final_answer: null,
      citations: [],
      artifacts: {
        result_dir: resultDir,
        raw_html_uri: null,
        final_markdown_uri: null,
        screenshot_uri: path.join(resultDir, "error.png"),
        events_uri: path.join(resultDir, "events.jsonl"),
      },
      usage: {
        latency_ms: Date.now() - started,
        input_tokens: null,
        output_tokens: null,
        search_calls: null,
        cost_usd: null,
      },
      sut: {
        provider: "doubao",
        product: options.researchMode ? "web_deep_research" : "web_chat",
        model: null,
        endpoint_family: "browser_ui",
        parameters: {
          entry_url: ENTRY_URL,
          browser_channel: options.browserChannel ?? null,
          research_mode_requested: options.researchMode,
        },
      },
      error: { code, message },
    };
    process.exitCode = 1;
  } finally {
    if (context && !options.keepOpen) await context.close();
  }

  await writeFile(path.join(resultDir, "result.json"), JSON.stringify(result, null, 2), "utf8");
  process.stdout.write(`\n结果：${result.status}\n目录：${resultDir}\n`);
  if (result.final_answer) process.stdout.write(`\n${result.final_answer}\n`);
  if (result.error) process.stderr.write(`${result.error.code}: ${result.error.message}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
});
