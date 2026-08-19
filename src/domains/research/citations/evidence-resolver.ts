import { randomUUID } from "node:crypto";

import {
  EvidenceSnapshotSchema,
  type CitationRecord,
  type EvidenceSnapshot,
} from "../../../schemas/contracts.js";
import type { ArtifactStore } from "../../../core/storage/artifact-store.js";
import { sha256Text } from "../../../core/utils/hash.js";
import { assertPublicHttpUrl } from "./url-security.js";

const MAX_BYTES = 5 * 1024 * 1024;

function htmlText(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function metadata(html: string, resolved: URL): { title: string | null; publishedAt: string | null } {
  const title = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.replace(/\s+/g, " ").trim() ?? null;
  const publishedAt = html.match(/(?:article:published_time|datePublished)[^>]+content=["']([^"']+)/i)?.[1] ?? null;
  return { title, publishedAt };
}

function accessStatus(status: number, text: string): EvidenceSnapshot["status"] {
  if (status === 401) return "login_required";
  if (status === 402 || /paywall|subscribe to continue|付费阅读|订阅后阅读/i.test(text)) return "paywalled";
  if (status === 403 || status === 429) return "blocked";
  if (status === 404 || status === 410) return "not_found";
  return status >= 200 && status < 300 ? "fetched" : "error";
}

export async function resolveEvidence(input: {
  citation: CitationRecord;
  store: ArtifactStore;
  outputRoot: string;
  timeoutSeconds?: number;
  fetchImpl?: typeof fetch;
}): Promise<EvidenceSnapshot> {
  const requested = input.citation.resolved_url ?? input.citation.visible_url;
  const base = {
    schema_version: "trueeval.evidence_snapshot.v0.1" as const,
    evidence_id: randomUUID(),
    citation_id: input.citation.citation_id,
    requested_url: requested ?? "",
    resolved_url: null,
    redirect_chain: [] as string[],
    retrieved_at: new Date().toISOString(),
    status: "error" as const,
    http_status: null,
    title: null,
    publisher: null,
    published_at: null,
    text_artifact: null,
    html_artifact: null,
    sha256: null,
    error_code: null,
  };
  if (!requested) return EvidenceSnapshotSchema.parse({ ...base, error_code: "EVIDENCE_URL_MISSING" });
  try {
    let current = await assertPublicHttpUrl(requested);
    const redirects: string[] = [];
    const fetcher = input.fetchImpl ?? fetch;
    let response: Response | null = null;
    for (let redirect = 0; redirect <= 5; redirect += 1) {
      response = await fetcher(current, {
        method: "GET",
        redirect: "manual",
        headers: { "user-agent": "TrueEval-EvidenceResolver/0.1" },
        signal: AbortSignal.timeout((input.timeoutSeconds ?? 20) * 1000),
      });
      if (![301, 302, 303, 307, 308].includes(response.status)) break;
      const location = response.headers.get("location");
      if (!location) break;
      redirects.push(current.href);
      current = await assertPublicHttpUrl(new URL(location, current).href);
      response = null;
    }
    if (!response) throw new Error("EVIDENCE_TOO_MANY_REDIRECTS");
    const declaredLength = Number(response.headers.get("content-length") ?? 0);
    if (declaredLength > MAX_BYTES) throw new Error("EVIDENCE_TOO_LARGE");
    const buffer = Buffer.from(await response.arrayBuffer());
    if (buffer.byteLength > MAX_BYTES) throw new Error("EVIDENCE_TOO_LARGE");
    const contentType = response.headers.get("content-type") ?? "";
    const html = buffer.toString("utf8");
    const text = contentType.includes("html") ? htmlText(html) : html;
    const status = accessStatus(response.status, text.slice(0, 20_000));
    let htmlRef = null;
    let textRef = null;
    if (status === "fetched") {
      textRef = await input.store.writeText(`${input.outputRoot}/evidence.txt`, "evidence_text", text);
      if (contentType.includes("html")) {
        htmlRef = await input.store.writeText(`${input.outputRoot}/evidence.html`, "evidence_html", html, "text/html; charset=utf-8");
      }
    }
    const meta = contentType.includes("html") ? metadata(html, current) : { title: null, publishedAt: null };
    return EvidenceSnapshotSchema.parse({
      ...base,
      requested_url: requested,
      resolved_url: current.href,
      redirect_chain: redirects,
      status,
      http_status: response.status,
      title: meta.title,
      publisher: current.hostname,
      published_at: meta.publishedAt,
      text_artifact: textRef,
      html_artifact: htmlRef,
      sha256: sha256Text(text),
    });
  } catch (error) {
    return EvidenceSnapshotSchema.parse({
      ...base,
      requested_url: requested,
      error_code: error instanceof Error ? error.message : String(error),
    });
  }
}
