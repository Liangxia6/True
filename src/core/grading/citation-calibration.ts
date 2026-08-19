import { readFile } from "node:fs/promises";

import { CitationVerdictSchema } from "../../schemas/contracts.js";

const LABELS = ["supported", "partially_supported", "contradicted", "irrelevant", "insufficient_evidence", "evidence_unavailable"] as const;

export interface CitationCalibrationReport {
  schema_version: "trueeval.citation_calibration_report.v0.1";
  sample_count: number;
  exact_agreement: number;
  cohen_kappa: number;
  eligible_for_official_metrics: boolean;
  minimum_samples: number;
  minimum_kappa: number;
}

export function calculateCitationCalibration(rows: Array<{ expected: string; predicted: string }>): CitationCalibrationReport {
  if (!rows.length) throw new Error("Citation calibration dataset is empty");
  for (const row of rows) {
    if (!LABELS.includes(row.expected as typeof LABELS[number]) || !LABELS.includes(row.predicted as typeof LABELS[number])) throw new Error(`Unknown citation calibration label: ${row.expected}/${row.predicted}`);
  }
  const observed = rows.filter((row) => row.expected === row.predicted).length / rows.length;
  const expectedAgreement = LABELS.reduce((sum, label) => {
    const human = rows.filter((row) => row.expected === label).length / rows.length;
    const judge = rows.filter((row) => row.predicted === label).length / rows.length;
    return sum + human * judge;
  }, 0);
  const kappa = expectedAgreement === 1 ? 1 : (observed - expectedAgreement) / (1 - expectedAgreement);
  return { schema_version: "trueeval.citation_calibration_report.v0.1", sample_count: rows.length, exact_agreement: observed, cohen_kappa: kappa, eligible_for_official_metrics: rows.length >= 30 && kappa >= 0.8, minimum_samples: 30, minimum_kappa: 0.8 };
}

export async function calibrateCitationFile(filePath: string): Promise<CitationCalibrationReport> {
  const lines = (await readFile(filePath, "utf8")).split(/\r?\n/).filter(Boolean);
  const rows = lines.map((line, index) => {
    const row = JSON.parse(line) as { expected: string; verdict: unknown };
    const verdict = CitationVerdictSchema.parse(row.verdict);
    if (typeof row.expected !== "string") throw new Error(`Calibration row ${index + 1} has no expected label`);
    return { expected: row.expected, predicted: verdict.verdict };
  });
  return calculateCitationCalibration(rows);
}
