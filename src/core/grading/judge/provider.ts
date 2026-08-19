import { spawn } from "node:child_process";

import type { JudgeProfile } from "../../../schemas/contracts.js";

export interface JudgePrompt {
  system: string;
  user: string;
}

export interface JudgeInvocationResult {
  text: string;
  actualModel: string | null;
  rawResponse: unknown;
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    cost_usd: number | null;
  };
}

export interface JudgeProvider {
  invoke(prompt: JudgePrompt): Promise<JudgeInvocationResult>;
}

class NonRetryableJudgeError extends Error {}

function chatCompletionsUrl(baseUrl: string): string {
  const trimmed = baseUrl.replace(/\/+$/, "");
  return trimmed.endsWith("/chat/completions") ? trimmed : `${trimmed}/chat/completions`;
}

function responseText(payload: unknown): string {
  const object = payload as {
    choices?: Array<{ message?: { content?: string | Array<{ type?: string; text?: string }> } }>;
  };
  const content = object.choices?.[0]?.message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((part) => part.text ?? "").join("");
  throw new Error("Judge response does not contain choices[0].message.content");
}

export class OpenAICompatibleJudgeProvider implements JudgeProvider {
  constructor(private readonly profile: JudgeProfile) {
    if (profile.transport !== "openai_compatible" || !profile.base_url || !profile.api_key_env) {
      throw new Error("OpenAICompatibleJudgeProvider requires an openai_compatible profile");
    }
  }

  async invoke(prompt: JudgePrompt): Promise<JudgeInvocationResult> {
    const apiKeyEnvironment = this.profile.api_key_env!;
    const apiKey = process.env[apiKeyEnvironment];
    if (!apiKey) throw new Error(`Missing Judge API key environment variable: ${apiKeyEnvironment}`);
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.profile.max_retries; attempt += 1) {
      try {
        const response = await fetch(chatCompletionsUrl(this.profile.base_url!), {
          method: "POST",
          headers: {
            authorization: `Bearer ${apiKey}`,
            "content-type": "application/json",
          },
          body: JSON.stringify({
            model: this.profile.model,
            messages: [
              { role: "system", content: prompt.system },
              { role: "user", content: prompt.user },
            ],
            temperature: this.profile.temperature,
            max_tokens: this.profile.max_output_tokens,
            ...(this.profile.seed === null ? {} : { seed: this.profile.seed }),
          }),
          signal: AbortSignal.timeout(this.profile.timeout_seconds * 1000),
        });
        const raw = (await response.json()) as unknown;
        if (!response.ok) {
          const retryable = response.status === 429 || response.status >= 500;
          if (!retryable) {
            throw new NonRetryableJudgeError(`Judge HTTP ${response.status}: ${JSON.stringify(raw).slice(0, 500)}`);
          }
          if (attempt === this.profile.max_retries) {
            throw new Error(`Judge HTTP ${response.status}: ${JSON.stringify(raw).slice(0, 500)}`);
          }
          lastError = new Error(`Judge HTTP ${response.status}`);
        } else {
          const object = raw as {
            model?: string;
            usage?: { prompt_tokens?: number; completion_tokens?: number };
          };
          return {
            text: responseText(raw),
            actualModel: object.model ?? null,
            rawResponse: raw,
            usage: {
              input_tokens: object.usage?.prompt_tokens ?? null,
              output_tokens: object.usage?.completion_tokens ?? null,
              cost_usd: null,
            },
          };
        }
      } catch (error) {
        lastError = error;
        if (error instanceof NonRetryableJudgeError) break;
        if (attempt === this.profile.max_retries) break;
      }
      await new Promise((resolve) => setTimeout(resolve, Math.min(2000, 250 * 2 ** attempt)));
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }
}

export class ProcessJudgeProvider implements JudgeProvider {
  constructor(private readonly profile: JudgeProfile) {
    if (profile.transport !== "process" || !profile.command?.length) {
      throw new Error("ProcessJudgeProvider requires a process profile command");
    }
  }

  async invoke(prompt: JudgePrompt): Promise<JudgeInvocationResult> {
    const [executable, ...args] = this.profile.command!;
    if (!executable) throw new Error("Judge process command is empty");
    return new Promise((resolve, reject) => {
      const child = spawn(executable, args, { shell: false, stdio: ["pipe", "pipe", "pipe"] });
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      let settled = false;
      const finish = (operation: () => void) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        operation();
      };
      const timeout = setTimeout(() => {
        child.kill("SIGTERM");
        finish(() => reject(new Error(`Judge process timed out after ${this.profile.timeout_seconds}s`)));
      }, this.profile.timeout_seconds * 1000);
      child.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
      child.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
      child.on("error", (error) => {
        finish(() => reject(error));
      });
      child.on("close", (code) => {
        finish(() => {
          if (code !== 0) {
            reject(new Error(`Judge process exited ${code}: ${Buffer.concat(stderr).toString("utf8").slice(0, 1000)}`));
            return;
          }
          try {
            const raw = JSON.parse(Buffer.concat(stdout).toString("utf8")) as {
              text: string;
              actual_model?: string | null;
              usage?: { input_tokens?: number; output_tokens?: number; cost_usd?: number };
            };
            if (typeof raw.text !== "string") throw new Error("Judge process result.text must be a string");
            resolve({ text: raw.text, actualModel: raw.actual_model ?? null, rawResponse: raw, usage: { input_tokens: raw.usage?.input_tokens ?? null, output_tokens: raw.usage?.output_tokens ?? null, cost_usd: raw.usage?.cost_usd ?? null } });
          } catch (error) { reject(error); }
        });
      });
      child.stdin.end(
        JSON.stringify({
          schema_version: "trueeval.judge_process_request.v0.1",
          model: this.profile.model,
          temperature: this.profile.temperature,
          max_output_tokens: this.profile.max_output_tokens,
          prompt,
        }),
      );
    });
  }
}

export function createJudgeProvider(profile: JudgeProfile): JudgeProvider {
  return profile.transport === "openai_compatible"
    ? new OpenAICompatibleJudgeProvider(profile)
    : new ProcessJudgeProvider(profile);
}
