const UI_NOISE_LINES = new Set([
  "豆包",
  "新工作任务",
  "新对话",
  "更多",
  "最近",
  "关于豆包",
  "下载电脑版",
  "登录",
  "对话",
  "工作",
  "快速",
  "新",
  "PPT 生成",
  "图像生成",
  "帮我写作",
  "视频生成",
  "翻译",
  "深入研究",
  "录音转写",
  "复制",
  "重新生成",
  "赞",
  "踩",
]);

export function normalizeText(value: string): string {
  return value
    .replace(/\r\n/g, "\n")
    .replace(/^[ \t]+|[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function sanitizePathSegment(value: string): string {
  const clean = value
    .normalize("NFKC")
    .replace(/[^\p{Letter}\p{Number}._-]+/gu, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 96);
  return clean || "task";
}

export function fallbackAnswerFromMainText(
  mainText: string,
  prompt: string,
  baselineText: string,
): string {
  const promptNormalized = normalizeText(prompt);
  const baselineLines = new Set(
    normalizeText(baselineText)
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
  );

  const lines = normalizeText(mainText)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => line !== promptNormalized)
    .filter((line) => !baselineLines.has(line))
    .filter((line) => !UI_NOISE_LINES.has(line));

  return normalizeText(lines.join("\n"));
}
