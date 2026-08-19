import { ClaimRecordSchema, type ResearchSubmission } from "../../../schemas/contracts.js";

const CITATION_MARKER = /(?:\[(\d+)\]|【(\d+)】)/g;

function looksVerifiable(text: string): boolean {
  return /\d|年|月|日|是|为|达到|增长|下降|发布|宣布|位于|成立|according|reported|was|were|is|are|percent|million|billion/i.test(text);
}

export function extractClaims(submission: ResearchSubmission) {
  const answer = submission.final_answer;
  const spans: Array<{ start: number; end: number; text: string }> = [];
  const pattern = /[^。！？!?\n]+[。！？!?]?/g;
  for (const match of answer.matchAll(pattern)) {
    const raw = match[0];
    const leading = raw.length - raw.trimStart().length;
    const text = raw.trim();
    if (text.length < 8 || match.index === undefined) continue;
    spans.push({ start: match.index + leading, end: match.index + leading + text.length, text });
  }
  return spans.map((span, index) => {
    const citationIds: string[] = [];
    for (const match of span.text.matchAll(CITATION_MARKER)) {
      const ordinal = match[1] ?? match[2];
      const citation = submission.citations[Number(ordinal) - 1];
      if (citation) citationIds.push(citation.citation_id);
    }
    return ClaimRecordSchema.parse({
      claim_id: `claim-${String(index + 1).padStart(4, "0")}`,
      text: span.text,
      source_span: { start: span.start, end: span.end },
      importance: span.text.length >= 80 || index === 0 ? "major" : "minor",
      verifiability: looksVerifiable(span.text) ? "externally_verifiable" : "non_verifiable",
      citation_ids: [...new Set(citationIds)],
    });
  });
}
