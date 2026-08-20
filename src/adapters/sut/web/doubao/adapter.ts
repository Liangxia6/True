import { createHash } from "node:crypto";
import { appendFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type { Locator, Page } from "playwright";

import { fallbackAnswerFromMainText, normalizeText } from "./text.js";
import type { Citation, RunEvent, RunnerOptions } from "./types.js";

const ENTRY_URL = "https://www.doubao.com/chat/";
const ALLOWED_HOSTS = new Set(["doubao.com", "www.doubao.com"]);

export class DoubaoAutomationError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "DoubaoAutomationError";
  }
}

export interface CollectedOutput {
  answer: string;
  citations: Citation[];
  rawHtml: string;
  mainText: string;
}

export class DoubaoWebAdapter {
  private baselineMainText = "";
  private promptHash = "";

  constructor(
    private readonly page: Page,
    private readonly options: RunnerOptions,
    private readonly resultDir: string,
  ) {}

  async open(): Promise<void> {
    await this.event("PAGE_OPENING", { url: ENTRY_URL });
    await this.page.goto(ENTRY_URL, {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
    this.assertAllowedHost();
    await this.page.waitForLoadState("domcontentloaded");
    await this.waitForTextbox(60_000);
    this.baselineMainText = await this.readMainText();
    await this.screenshot("00-home.png");
    await this.event("PAGE_READY", {
      url: this.page.url(),
      title: await this.page.title(),
    });
  }

  async ensureLogin(): Promise<void> {
    // 豆包的登录按钮可能晚于输入框渲染，先给页面一个短暂稳定窗口。
    await this.page.waitForTimeout(1_500);
    if (await this.sessionLooksLoggedIn()) {
      await this.settleAuthenticatedSession();
      return;
    }
    if (this.options.allowAnonymous) {
      await this.event("ANONYMOUS_MODE_ALLOWED");
      return;
    }
    await this.waitForManualLogin("页面检测到未登录");
    await this.settleAuthenticatedSession();
  }

  async ensurePersonalChat(): Promise<void> {
    const before = await this.readMainText();
    const onWork =
      before.includes("今天有什么工作要处理") ||
      (before.includes("豆包 工作") && before.includes("新工作任务"));
    if (!onWork) {
      await this.event("PERSONAL_CHAT_ALREADY");
      return;
    }

    await this.screenshot("00a-workspace.png");
    await this.event("WORKSPACE_DETECTED", { action: "switch_to_dialog" });
    const switcher = await this.firstEnabledVisible([
      this.page.getByRole("button", { name: "对话", exact: true }),
      this.page.getByRole("tab", { name: "对话", exact: true }),
      this.page.getByRole("button", { name: "主对话", exact: true }),
      this.page.getByText("主对话", { exact: true }),
      this.page.getByText("对话", { exact: true }),
    ]);
    if (switcher) {
      try {
        await switcher.click({ timeout: 5_000 });
        await this.page.waitForTimeout(1_200);
      } catch {
        await this.event("SWITCH_CLICK_FAILED");
      }
    }

    const deadline = Date.now() + Math.min(this.options.loginTimeoutSeconds, 180) * 1000;
    let waited = false;
    while (Date.now() < deadline) {
      if (await this.personalChatReady()) {
        await this.screenshot("00b-personal-chat.png");
        await this.event("PERSONAL_CHAT_READY", { still_work: false });
        return;
      }
      if (!waited) {
        await this.event("PERSONAL_CHAT_WAIT", {
          hint: "请在弹出的 Edge 窗口点左侧“主对话”，或切到带“深入研究”的普通豆包。",
        });
        waited = true;
      }
      await this.page.waitForTimeout(2_000);
    }

    await this.screenshot("00b-personal-chat.png");
    throw new DoubaoAutomationError(
      "UI_CHANGED",
      "仍停留在“豆包工作”，未能切回带“深入研究”的普通对话。",
    );
  }

  async startCleanConversation(): Promise<void> {
    const candidates = this.options.researchMode
      ? [
          this.page.getByRole("button", { name: "新对话", exact: true }),
          this.page.getByText("新对话", { exact: true }),
        ]
      : [
          this.page.getByRole("button", { name: "新对话", exact: true }),
          this.page.getByText("新对话", { exact: true }),
          this.page.getByRole("button", { name: "新工作任务", exact: true }),
          this.page.getByText("新工作任务", { exact: true }),
        ];
    const locator = await this.resolveUniqueVisible(candidates, "新对话", false);
    if (locator) {
      await locator.click();
      await this.page.waitForTimeout(500);
      await this.waitForTextbox(30_000);
    }

    const textbox = await this.textbox();
    await textbox.fill("");
    this.baselineMainText = await this.readMainText();
    await this.event("CLEAN_CONVERSATION_READY", {
      new_chat_control_found: Boolean(locator),
    });
  }

  async selectResearchMode(): Promise<void> {
    if (!this.options.researchMode) {
      await this.event("RESEARCH_MODE_SKIPPED");
      return;
    }

    for (let attempt = 0; attempt < 2; attempt += 1) {
      const research = await this.resolveUniqueVisible(
        [
          this.page.getByRole("button", { name: "深入研究", exact: true }),
          this.page.getByText("深入研究", { exact: true }),
          this.page.getByRole("button", { name: "完成调研分析", exact: true }),
          this.page.getByText("完成调研分析", { exact: true }),
        ],
        "深入研究/完成调研分析",
        true,
      );
      if (!research) {
        throw new DoubaoAutomationError(
          "RESEARCH_MODE_UNAVAILABLE",
          "未找到唯一可见的“深入研究”或“完成调研分析”控件，豆包 UI 可能已更新或账号无权限。",
        );
      }

      const before = await this.controlState(research);
      await research.click();
      await this.page.waitForTimeout(800);
      const after = await this.controlState(research).catch(() => null);
      await this.screenshot("01-research-mode.png");
      if (await this.researchLoginPromptVisible()) {
        await this.event("LOGIN_REQUIRED_AFTER_RESEARCH_SELECTION");
        await this.waitForManualLogin("“深入研究”要求登录");
        continue;
      }
      await this.event("RESEARCH_MODE_SELECTED", {
        before,
        after,
        selection_state_changed:
          Boolean(after) && JSON.stringify(before) !== JSON.stringify(after),
      });
      return;
    }
    throw new DoubaoAutomationError(
      "LOGIN_REQUIRED",
      "登录后仍无法启用豆包“深入研究”，请检查账号权限或重新登录。",
    );
  }

  async submitPrompt(): Promise<void> {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const urlBefore = this.page.url();
      const sentByButton = await this.fillAndSend();
      await this.page.waitForTimeout(1_500);
      await this.recoverAfterNavigation();
      if (!(await this.sessionLooksLoggedIn())) {
        await this.event("SESSION_LOST_AFTER_SUBMIT", {
          attempt,
          url: this.page.url(),
        });
        await this.waitForManualLogin("提交后登录态丢失，请在同一窗口重新登录");
        await this.settleAuthenticatedSession();
        await this.startCleanConversation();
        await this.selectResearchMode();
        continue;
      }
      const submitted =
        this.conversationStarted(urlBefore) || (await this.waitForPromptEcho(30_000));
      if (!submitted) {
        throw new DoubaoAutomationError(
          "SUBMISSION_UNCONFIRMED",
          "已触发发送，但页面未确认提示词已提交；为避免重复任务，脚本不会自动重发。",
        );
      }
      await this.screenshot("03-submitted.png");
      await this.event("SUBMITTED", {
        prompt_sha256: this.promptHash,
        submission_method: sentByButton ? "send_button" : "enter_key",
        url: this.page.url(),
        attempt,
      });
      return;
    }
    throw new DoubaoAutomationError(
      "LOGIN_REQUIRED",
      "提交时豆包两次清掉登录态。请只在脚本弹出的窗口登录，登录完成后等侧栏出现“云盘”再继续。",
    );
  }

  async waitForCompletion(): Promise<CollectedOutput> {
    const deadline = Date.now() + this.options.timeoutSeconds * 1000;
    let lastAnswer = "";
    let stable = 0;
    let bestAnswer = "";
    let missingPromptPolls = 0;

    await this.event("WAITING_FOR_RESULT", {
      timeout_seconds: this.options.timeoutSeconds,
    });

    while (Date.now() < deadline) {
      try {
        await this.recoverAfterNavigation();
      } catch (error) {
        if (!this.isDestroyedError(error)) throw error;
        await this.page.waitForTimeout(1_000);
        continue;
      }
      this.assertAllowedHost();
      const mainText = await this.readMainText();
      const promptStillVisible = await this.promptInMessageArea();
      missingPromptPolls = promptStillVisible ? 0 : missingPromptPolls + 1;
      if (missingPromptPolls >= 2) {
        if (!(await this.sessionLooksLoggedIn())) {
          throw new DoubaoAutomationError(
            "LOGIN_REQUIRED",
            "豆包在提交后终止了未登录会话；请只在脚本弹出的窗口重新登录后重试。",
          );
        }
        throw new DoubaoAutomationError(
          "PROVIDER_ERROR",
          "已提交的会话从页面消失，无法可靠读取输出。",
        );
      }
      const answer = await this.extractAnswer(mainText);
      const running = await this.isRunning();
      const providerError = await this.detectProviderError();
      if (providerError) {
        throw new DoubaoAutomationError("PROVIDER_ERROR", providerError);
      }

      if (answer.length > bestAnswer.length) bestAnswer = answer;
      if (answer && answer === lastAnswer) stable += 1;
      else stable = answer ? 1 : 0;
      lastAnswer = answer;

      await this.event("RESULT_OBSERVED", {
        answer_chars: answer.length,
        stable_polls: stable,
        running,
      });

      if (answer && !running && stable >= this.options.stablePolls) {
        await this.event("RESULT_STABLE", { answer_chars: answer.length });
        return this.collect(answer, mainText);
      }
      await this.page.waitForTimeout(this.options.pollIntervalMs);
    }

    if (bestAnswer) {
      await writeFile(path.join(this.resultDir, "partial-answer.md"), bestAnswer, "utf8");
    }
    throw new DoubaoAutomationError(
      "TIMEOUT",
      `等待豆包输出超时（${this.options.timeoutSeconds} 秒）。`,
    );
  }

  async collect(answer: string, mainText?: string): Promise<CollectedOutput> {
    const finalMainText = mainText ?? (await this.readMainText());
    const rawHtml = await this.page.locator("main").innerHTML().catch(async () => this.page.content());
    const citations = await this.extractCitations();
    await this.screenshot("04-completed.png");
    await writeFile(path.join(this.resultDir, "response.raw.html"), rawHtml, "utf8");
    await writeFile(path.join(this.resultDir, "response.visible.md"), answer, "utf8");
    await writeFile(
      path.join(this.resultDir, "citations.raw.json"),
      JSON.stringify(citations, null, 2),
      "utf8",
    );
    await writeFile(path.join(this.resultDir, "page.visible.txt"), finalMainText, "utf8");
    await this.event("COLLECTED", {
      answer_chars: answer.length,
      citation_count: citations.length,
    });
    return { answer, citations, rawHtml, mainText: finalMainText };
  }

  async screenshot(name: string): Promise<string | null> {
    const target = path.join(this.resultDir, name);
    try {
      await this.page.screenshot({ path: target, fullPage: true });
      return target;
    } catch {
      return null;
    }
  }

  private assertAllowedHost(): void {
    const host = new URL(this.page.url()).hostname;
    if (!ALLOWED_HOSTS.has(host)) {
      throw new DoubaoAutomationError(
        "UNEXPECTED_HOST",
        `页面跳转到未授权域名：${host}`,
      );
    }
  }

  private async loginButtonVisible(): Promise<boolean> {
    const button = this.page.getByRole("button", { name: "登录", exact: true });
    return (await button.count()) === 1 && (await button.isVisible());
  }

  private async researchLoginPromptVisible(): Promise<boolean> {
    const prompt = this.page.getByText("登录以解锁更多功能", { exact: true });
    return (await prompt.count()) === 1 && (await prompt.isVisible());
  }

  private async sessionLooksLoggedIn(): Promise<boolean> {
    if (this.page.url().includes("from_logout")) return false;
    if (await this.loginButtonVisible()) return false;
    if (await this.researchLoginPromptVisible()) return false;
    const cloud = await this.page
      .getByText("云盘", { exact: true })
      .first()
      .isVisible()
      .catch(() => false);
    const skills = await this.page
      .getByText("技能·连接器·伙伴", { exact: true })
      .first()
      .isVisible()
      .catch(() => false);
    return Boolean(cloud || skills);
  }

  private async settleAuthenticatedSession(): Promise<void> {
    await this.recoverAfterNavigation();
    if (!(await this.sessionLooksLoggedIn())) {
      throw new DoubaoAutomationError(
        "LOGIN_REQUIRED",
        "登录态未稳定。请只在脚本弹出的窗口登录，并确认侧栏出现“云盘”。",
      );
    }
    await this.page.reload({ waitUntil: "domcontentloaded", timeout: 60_000 });
    await this.page.waitForTimeout(1_500);
    await this.recoverAfterNavigation();
    if (!(await this.sessionLooksLoggedIn())) {
      throw new DoubaoAutomationError(
        "LOGIN_REQUIRED",
        "刷新后登录态未保持。请只在脚本弹出的窗口登录，并确认侧栏出现“云盘”。",
      );
    }
    await this.waitForTextbox(30_000);
    await this.screenshot("00c-session.png");
    await this.event("SESSION_SETTLED", { url: this.page.url() });
  }

  private async recoverAfterNavigation(): Promise<void> {
    try {
      await this.page.waitForLoadState("domcontentloaded", { timeout: 15_000 });
    } catch {
      // 页面可能仍在跳转
    }
    this.assertAllowedHost();
    if (!this.page.url().includes("from_logout")) return;
    await this.event("LOGOUT_REDIRECT", { url: this.page.url() });
    await this.page.goto(ENTRY_URL, {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
  }

  private isDestroyedError(error: unknown): boolean {
    const message = error instanceof Error ? error.message : String(error);
    return (
      message.includes("Execution context was destroyed") ||
      message.includes("Target closed") ||
      message.includes("Target page, context or browser has been closed")
    );
  }

  private async withFreshPage<T>(fn: () => Promise<T>): Promise<T> {
    let last: unknown;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        return await fn();
      } catch (error) {
        last = error;
        if (!this.isDestroyedError(error) || attempt === 2) throw error;
        await this.recoverAfterNavigation();
      }
    }
    throw last;
  }

  private async waitForManualLogin(reason: string): Promise<void> {
    if (this.options.headless) {
      throw new DoubaoAutomationError(
        "LOGIN_REQUIRED",
        `${reason}；请关闭 --headless 后运行并在浏览器中手动登录。`,
      );
    }

    await this.event("LOGIN_REQUIRED", {
      reason,
      timeout_seconds: this.options.loginTimeoutSeconds,
    });
    process.stdout.write(
      `\n${reason}。请在已打开的豆包浏览器窗口中完成登录，等到左侧出现“云盘”后再等待脚本继续；脚本将等待 ${this.options.loginTimeoutSeconds} 秒。\n`,
    );

    const deadline = Date.now() + this.options.loginTimeoutSeconds * 1000;
    let stableAuthenticatedPolls = 0;
    while (Date.now() < deadline) {
      await this.page.waitForTimeout(2_000);
      const authenticated = await this.sessionLooksLoggedIn();
      stableAuthenticatedPolls = authenticated ? stableAuthenticatedPolls + 1 : 0;
      if (stableAuthenticatedPolls >= 4) {
        await this.event("LOGIN_CONFIRMED");
        await this.waitForTextbox(30_000);
        return;
      }
    }
    throw new DoubaoAutomationError(
      "LOGIN_REQUIRED",
      `等待登录超时（${this.options.loginTimeoutSeconds} 秒）。侧栏需出现“云盘”才算登录完成。`,
    );
  }

  private async fillAndSend(): Promise<boolean> {
    const textbox = await this.textbox();
    await textbox.fill(this.options.prompt);
    const actual = await this.composerValue(textbox);
    const expected = normalizeText(this.options.prompt);
    if (actual !== expected) {
      throw new DoubaoAutomationError(
        "PROMPT_INPUT_MISMATCH",
        "输入框内容与原始提示词不一致，已停止提交。",
      );
    }
    this.promptHash = createHash("sha256").update(expected).digest("hex");
    await this.event("PROMPT_READY", { prompt_sha256: this.promptHash });
    await this.screenshot("02-prompt-ready.png");

    const sentByButton = await this.tryClickSendButton();
    if (!sentByButton) await textbox.press("Enter");
    return sentByButton;
  }

  private async composerValue(locator: Locator): Promise<string> {
    return normalizeText(
      await locator.evaluate((element) => {
        if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
          return element.value;
        }
        return element.textContent ?? "";
      }),
    );
  }

  private async textbox(): Promise<Locator> {
    const locators = [
      ...(await this.page.getByRole("textbox").all()),
      ...(await this.page.locator("textarea").all()),
      ...(await this.page.locator('[contenteditable="true"]').all()),
    ];
    const visible: Locator[] = [];
    for (const match of locators) {
      try {
        if (await match.isVisible()) visible.push(match);
      } catch {
        // 节点可能已从 DOM 卸下
      }
    }

    const expected = normalizeText(this.options.prompt);
    if (expected) {
      for (const match of visible) {
        try {
          const value = await this.composerValue(match);
          if (value.includes(expected.slice(0, 24))) return match;
        } catch {
          // 忽略失效节点
        }
      }
    }

    const byPlaceholder = await this.firstEnabledVisible([
      this.page.getByRole("textbox", { name: /发消息|输入主题|输入问题|输入主题和报告要求/ }),
      this.page.getByPlaceholder(/发消息|输入主题|输入问题|输入主题和报告要求/),
    ]);
    if (byPlaceholder) return byPlaceholder;

    if (visible.length === 1) return visible[0]!;

    let best: Locator | null = null;
    let bestY = -1;
    for (const match of visible) {
      const box = await match.boundingBox().catch(() => null);
      if (!box || box.width < 200) continue;
      if (box.y > bestY) {
        bestY = box.y;
        best = match;
      }
    }
    if (best) return best;
    throw new DoubaoAutomationError("UI_CHANGED", "未找到可见的消息输入框。");
  }

  private async waitForTextbox(timeoutMs: number): Promise<void> {
    await this.page.getByRole("textbox").waitFor({ state: "visible", timeout: timeoutMs });
  }

  private async personalChatReady(): Promise<boolean> {
    const mainText = await this.readMainText();
    const hasResearch = await this.firstEnabledVisible([
      this.page.getByRole("button", { name: "深入研究", exact: true }),
      this.page.getByText("深入研究", { exact: true }),
    ]);
    if (hasResearch) return true;
    return (
      mainText.includes("新对话") &&
      !mainText.includes("今天有什么工作要处理") &&
      !mainText.includes("豆包 工作")
    );
  }

  private async firstEnabledVisible(candidates: Locator[]): Promise<Locator | null> {
    for (const candidate of candidates) {
      const matches = await candidate.all();
      const usable: Locator[] = [];
      for (const match of matches) {
        if (!(await match.isVisible())) continue;
        if (await match.isDisabled()) continue;
        if ((await match.getAttribute("aria-disabled")) === "true") continue;
        usable.push(match);
      }
      if (usable.length === 1) return usable[0] ?? null;
    }
    return null;
  }

  private async resolveUniqueVisible(
    candidates: Locator[],
    label: string,
    required: boolean,
  ): Promise<Locator | null> {
    for (const candidate of candidates) {
      const matches = await candidate.all();
      const visible: Locator[] = [];
      for (const match of matches) {
        if (await match.isVisible()) visible.push(match);
      }
      if (visible.length === 1) return visible[0] ?? null;
    }
    if (required) {
      throw new DoubaoAutomationError(
        "UI_CHANGED",
        `无法唯一定位${label}；请运行页面探测并更新豆包适配器。`,
      );
    }
    return null;
  }

  private async controlState(locator: Locator): Promise<Record<string, string | null>> {
    return locator.evaluate((element) => ({
      ariaPressed: element.getAttribute("aria-pressed"),
      ariaSelected: element.getAttribute("aria-selected"),
      dataState: element.getAttribute("data-state"),
      className: typeof element.className === "string" ? element.className : null,
      backgroundColor: window.getComputedStyle(element).backgroundColor,
      color: window.getComputedStyle(element).color,
      parentClassName:
        element.parentElement && typeof element.parentElement.className === "string"
          ? element.parentElement.className
          : null,
      parentDataState: element.parentElement?.getAttribute("data-state") ?? null,
    }));
  }

  private async tryClickSendButton(): Promise<boolean> {
    const candidates = [
      this.page.getByRole("button", { name: "发送", exact: true }),
      this.page.getByRole("button", { name: "发送消息", exact: true }),
      this.page.locator('button[type="submit"]'),
    ];
    for (const candidate of candidates) {
      if (
        (await candidate.count()) === 1 &&
        (await candidate.isVisible()) &&
        (await candidate.isEnabled())
      ) {
        await candidate.click();
        return true;
      }
    }

    // 豆包当前（2026-08）的发送键没有可访问名称或 submit 类型，只显示箭头图标。
    // 以输入框为锚点，选择其右下方唯一、可见、启用的小型空文本按钮。
    // 该几何兜底不依赖混淆 class，也不会误点左侧的附件按钮。
    const deadline = Date.now() + 5_000;
    while (Date.now() < deadline) {
      let textboxBox: { x: number; y: number; width: number; height: number } | null = null;
      try {
        textboxBox = await (await this.textbox()).boundingBox();
      } catch {
        textboxBox = { x: 400, y: 800, width: 600, height: 80 };
      }
      if (!textboxBox) return false;

      const matches: Locator[] = [];
      for (const button of await this.page.locator("button").all()) {
        if (!(await button.isVisible()) || !(await button.isEnabled())) continue;
        if (normalizeText((await button.textContent()) ?? "")) continue;
        const box = await button.boundingBox();
        if (!box) continue;

        const centerX = box.x + box.width / 2;
        const centerY = box.y + box.height / 2;
        const textboxRight = textboxBox.x + textboxBox.width;
        const horizontallyAtRight = centerX >= textboxRight - 60 && centerX <= textboxRight + 40;
        const verticallyInComposer =
          centerY >= textboxBox.y - 20 && centerY <= textboxBox.y + textboxBox.height + 90;
        const smallIconButton =
          box.width >= 24 && box.width <= 64 && box.height >= 24 && box.height <= 64;
        if (horizontallyAtRight && verticallyInComposer && smallIconButton) {
          matches.push(button);
        }
      }

      if (matches.length === 1) {
        await matches[0]!.click();
        return true;
      }
      if (matches.length > 1) {
        throw new DoubaoAutomationError(
          "UI_CHANGED",
          `输入框右侧发现 ${matches.length} 个可能的发送按钮，已停止以避免误操作。`,
        );
      }
      await this.page.waitForTimeout(250);
    }
    return false;
  }

  private conversationStarted(urlBefore: string): boolean {
    const before = new URL(urlBefore);
    const after = new URL(this.page.url());
    if (after.href.includes("from_logout")) return false;
    const afterPath = after.pathname.replace(/\/+$/, "") || "/";
    if (afterPath.startsWith("/chat/") && afterPath !== "/chat") return true;
    return after.pathname !== before.pathname;
  }

  private async waitForPromptEcho(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    let emptyComposerPolls = 0;
    while (Date.now() < deadline) {
      try {
        const promptInMessageArea = await this.promptInMessageArea();
        const textboxValue = await this.composerValue(await this.textbox());
        if (!textboxValue && promptInMessageArea) return true;
        if (!textboxValue && (await this.sessionLooksLoggedIn())) {
          emptyComposerPolls += 1;
          if (emptyComposerPolls >= 8) return true;
        } else {
          emptyComposerPolls = 0;
        }
      } catch (error) {
        if (this.isDestroyedError(error)) {
          await this.recoverAfterNavigation();
        } else if (await this.promptInMessageArea().catch(() => false)) {
          return true;
        }
      }
      await this.page.waitForTimeout(500);
    }
    return false;
  }

  private async promptInMessageArea(): Promise<boolean> {
    const expected = normalizeText(this.options.prompt);
    return this.withFreshPage(() =>
      this.page.evaluate((prompt) => {
        const root = document.querySelector("main") ?? document.body;
        const clone = root.cloneNode(true) as HTMLElement;
        for (const input of clone.querySelectorAll(
          '[role="textbox"], textarea, input, [contenteditable="true"]',
        )) {
          input.remove();
        }
        return (clone.textContent ?? "").replace(/\s+/g, " ").includes(
          prompt.replace(/\s+/g, " "),
        );
      }, expected),
    );
  }

  private async readMainText(): Promise<string> {
    return this.withFreshPage(async () => {
      const main = this.page.locator("main");
      if ((await main.count()) === 1) return normalizeText(await main.innerText());
      return normalizeText(await this.page.locator("body").innerText());
    });
  }

  private async extractAnswer(mainText: string): Promise<string> {
    const prompt = normalizeText(this.options.prompt);
    const selectors = [
      '[data-streaming="true"]',
      '[data-streaming="false"]',
      ".md-box-root",
      '[data-testid*="message"]',
      "[data-message-id]",
      "article",
      '[class*="message"]',
    ];
    const candidates = await this.withFreshPage(() =>
      this.page.evaluate(
      ({ selectors: candidateSelectors, promptText }) => {
        const seen = new Set<Element>();
        const rows: Array<{ text: string; links: number; order: number; specific: boolean }> = [];
        let order = 0;
        for (const [selectorIndex, selector] of candidateSelectors.entries()) {
          for (const element of document.querySelectorAll(selector)) {
            if (seen.has(element)) continue;
            seen.add(element);
            const htmlElement = element as HTMLElement;
            const style = window.getComputedStyle(htmlElement);
            if (style.display === "none" || style.visibility === "hidden") continue;
            const text = (htmlElement.innerText || "").trim();
            if (!text || text === promptText || text.length < 2) continue;
            rows.push({
              text,
              links: element.querySelectorAll("a[href]").length,
              order: order++,
              specific: selectorIndex <= 2,
            });
          }
        }
        return rows.slice(-100);
      },
      { selectors, promptText: prompt },
    ),
    );

    const scored = candidates
      .map((candidate) => ({
        text: normalizeText(candidate.text),
        score:
          candidate.text.length +
          candidate.links * 100 +
          candidate.order * 2 -
          (candidate.text.includes(prompt) ? prompt.length : 0) +
          (candidate.specific ? 1_000_000 : 0),
      }))
      .filter((candidate) => candidate.text !== prompt)
      .filter((candidate) => candidate.text.length >= 8)
      .sort((a, b) => b.score - a.score);

    const candidate = scored[0]?.text ?? "";
    if (candidate && !candidate.includes("有什么我能帮你的吗")) return candidate;
    if (!(await this.promptInMessageArea())) return "";
    return fallbackAnswerFromMainText(mainText, prompt, this.baselineMainText);
  }

  private async isRunning(): Promise<boolean> {
    const stopNames = ["停止生成", "停止", "中止"];
    for (const name of stopNames) {
      const button = this.page.getByRole("button", { name, exact: true });
      if ((await button.count()) === 1 && (await button.isVisible())) return true;
    }
    return this.withFreshPage(() =>
      this.page.evaluate(() =>
        Boolean(
          document.querySelector(
            '[data-streaming="true"], [aria-busy="true"], [data-loading="true"], [data-state="loading"]',
          ),
        ),
      ),
    );
  }

  private async detectProviderError(): Promise<string | null> {
    const errorPhrases = [
      "网络异常",
      "服务异常",
      "请求失败",
      "请稍后重试",
      "操作过于频繁",
    ];
    const mainText = await this.readMainText();
    return errorPhrases.find((phrase) => mainText.includes(phrase)) ?? null;
  }

  private async extractCitations(): Promise<Citation[]> {
    const links = await this.page.locator("main a[href]").evaluateAll((anchors) =>
      anchors.slice(0, 500).map((anchor) => ({
        href: (anchor as HTMLAnchorElement).href,
        title:
          (anchor.textContent || "").trim() ||
          anchor.getAttribute("aria-label") ||
          anchor.getAttribute("title"),
      })),
    );
    const seen = new Set<string>();
    const citations: Citation[] = [];
    for (const link of links) {
      if (!link.href.startsWith("http")) continue;
      const hostname = new URL(link.href).hostname;
      if (ALLOWED_HOSTS.has(hostname) || seen.has(link.href)) continue;
      seen.add(link.href);
      citations.push({
        citation_id: `src${citations.length + 1}`,
        url: link.href,
        title: link.title || null,
        retrieved_at: new Date().toISOString(),
      });
    }
    return citations;
  }

  private async event(state: string, detail?: Record<string, unknown>): Promise<void> {
    await mkdir(this.resultDir, { recursive: true });
    const row: RunEvent = { at: new Date().toISOString(), state, detail };
    await appendFile(
      path.join(this.resultDir, "events.jsonl"),
      `${JSON.stringify(row)}\n`,
      "utf8",
    );
  }
}

export { ENTRY_URL };
