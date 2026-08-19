import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import {
  ArtifactRefSchema,
  CitationVerdictSchema,
  DeepResearchOfficialVerdictSchema,
  EvidenceSnapshotSchema,
  FixtureJudgeVerdictSchema,
  GoldRecordSchema,
  JudgeJobSchema,
  JudgeProfileSchema,
  LongFormJudgeVerdictSchema,
  RawSUTResultSchema,
  ResearchSubmissionSchema,
  RunManifestSchema,
  ScoreRecordSchema,
  ShortFactJudgeVerdictSchema,
  SUTSpecSchema,
  TaskSpecSchema,
} from "./contracts.js";

const schemas = {
  artifact_ref: ArtifactRefSchema,
  citation_verdict: CitationVerdictSchema,
  deepresearch_official_verdict: DeepResearchOfficialVerdictSchema,
  evidence_snapshot: EvidenceSnapshotSchema,
  fixture_judge_verdict: FixtureJudgeVerdictSchema,
  gold_record: GoldRecordSchema,
  judge_job: JudgeJobSchema,
  judge_profile: JudgeProfileSchema,
  long_form_judge_verdict: LongFormJudgeVerdictSchema,
  raw_sut_result: RawSUTResultSchema,
  research_submission: ResearchSubmissionSchema,
  run_manifest: RunManifestSchema,
  score: ScoreRecordSchema,
  short_fact_judge_verdict: ShortFactJudgeVerdictSchema,
  sut: SUTSpecSchema,
  task: TaskSpecSchema,
};

const outputDir = path.resolve("src/schemas/generated");
await mkdir(outputDir, { recursive: true });

for (const [name, schema] of Object.entries(schemas)) {
  const jsonSchema = z.toJSONSchema(schema, { target: "draft-7" });
  await writeFile(
    path.join(outputDir, `${name}.schema.json`),
    `${JSON.stringify(jsonSchema, null, 2)}\n`,
    "utf8",
  );
}

process.stdout.write(`Generated ${Object.keys(schemas).length} schemas in ${outputDir}\n`);
