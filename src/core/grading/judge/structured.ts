import type { z } from "zod";

export function parseStructuredOutput<T>(text: string, schema: z.ZodType<T>): T {
  const trimmed = text.trim();
  const unfenced = trimmed.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const start = unfenced.indexOf("{");
  const end = unfenced.lastIndexOf("}");
  if (start < 0 || end < start) throw new Error("Judge output does not contain a JSON object");
  return schema.parse(JSON.parse(unfenced.slice(start, end + 1)) as unknown);
}
