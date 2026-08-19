import { z } from "zod";

const NullableString = z.string().nullable();

export const ArtifactRefSchema = z
  .object({
    artifact_id: z.string().min(1),
    kind: z.string().min(1),
    uri: z.string().min(1),
    media_type: z.string().min(1),
    sha256: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    size_bytes: z.number().int().nonnegative(),
  })
  .strict();

export type ArtifactRef = z.infer<typeof ArtifactRefSchema>;

export const ResearchTrackSchema = z.enum(["short_fact", "long_form"]);
export type ResearchTrack = z.infer<typeof ResearchTrackSchema>;

export const TaskSpecSchema = z
  .object({
    schema_version: z.literal("trueeval.task.v0.1"),
    task_id: z.string().min(1),
    benchmark_id: z.string().min(1),
    split: z.string().min(1),
    domain: z.literal("research"),
    track: ResearchTrackSchema,
    input: z
      .object({
        prompt: z.string().min(1),
        language: z.string().min(1),
        as_of: NullableString,
        attachments: z.array(ArtifactRefSchema),
      })
      .strict(),
    expected_output: z
      .object({
        answer_form: z.enum(["short_text", "list", "structured_json", "report"]),
        citation_required: z.boolean(),
      })
      .strict(),
    required_capabilities: z.array(z.string().min(1)),
    constraints: z
      .object({
        timeout_seconds: z.number().int().positive(),
        internet_required: z.boolean(),
        max_attempts: z.number().int().positive(),
      })
      .strict(),
    evaluation_profile: z
      .object({
        official_grader: NullableString,
        overlays: z.array(z.literal("citation_reliability")),
      })
      .strict(),
    provenance: z.record(z.string(), z.unknown()),
  })
  .strict();

export type TaskSpec = z.infer<typeof TaskSpecSchema>;

export const SourceResearchTaskSchema = z
  .object({
    schema_version: z.literal("trueeval.research_task.v0.1"),
    task_id: z.string().min(1),
    benchmark_id: z.string().min(1),
    upstream_task_id: z.string().min(1),
    split: z.string().min(1),
    task_family: z.string().min(1),
    input: z.object({
      prompt: z.string().min(1),
      language: z.string().min(1),
      as_of: NullableString,
      attachments: z.array(z.unknown()),
    }),
    expected_output: z.object({
      answer_form: z.enum(["short_text", "list", "structured_json", "report"]),
      citation_required: z.boolean(),
    }),
    constraints: z.object({
      internet_required: z.boolean(),
      timeout_seconds: z.number().int().positive(),
    }),
    provenance: z.record(z.string(), z.unknown()),
  })
  .passthrough();

export type SourceResearchTask = z.infer<typeof SourceResearchTaskSchema>;

export const SUTSpecSchema = z
  .object({
    schema_version: z.literal("trueeval.sut.v0.1"),
    sut_id: z.string().min(1),
    provider: z.string().min(1),
    product: z.string().min(1),
    channel: z.enum(["web", "api", "process", "manual", "fake"]),
    adapter_id: z.string().min(1),
    adapter_version: z.string().min(1),
    account_tier: NullableString,
    capabilities: z
      .object({
        research_mode: z.boolean(),
        short_fact: z.boolean(),
        long_form: z.boolean(),
        visible_citations: z.boolean(),
        citation_urls: z.enum(["full", "visible_only", "none"]),
        file_output: z.boolean(),
      })
      .strict(),
    concurrency: z
      .object({
        max_workers: z.number().int().positive(),
        account_scoped: z.boolean(),
      })
      .strict(),
  })
  .strict();

export type SUTSpec = z.infer<typeof SUTSpecSchema>;

export const RunManifestSchema = z
  .object({
    schema_version: z.literal("trueeval.run_manifest.v0.1"),
    run_id: z.string().min(1).nullable().default(null),
    name: z.string().min(1),
    benchmark: z
      .object({
        id: z.string().min(1),
        version: z.string().min(1),
        root: z.string().min(1),
        split: z.string().min(1),
        task_selector: z
          .object({
            ids: z.array(z.string().min(1)).default([]),
            limit: z.number().int().positive().nullable().default(null),
            seed: z.number().int().default(20260819),
          })
          .strict(),
      })
      .strict(),
    sut: z
      .object({
        id: z.string().min(1),
        adapter: z.enum(["fake", "doubao_web", "process", "http_api"]),
        options: z.record(z.string(), z.unknown()).default({}),
      })
      .strict(),
    execution: z
      .object({
        worker: z.enum(["fake", "browser", "process"]),
        concurrency: z.number().int().positive().default(1),
        max_attempts: z.number().int().positive().default(1),
        headless: z.boolean().default(false),
        keep_worker_open: z.boolean().default(true),
        new_session_per_task: z.literal(true),
        timeout_seconds: z.number().int().positive(),
      })
      .strict(),
    evaluation: z
      .object({
        run_official: z.boolean().default(true),
        overlays: z.array(z.literal("citation_reliability")).default([]),
        grader_versions_locked: z.boolean().default(true),
        judge_profile: z.string().min(1).nullable().default(null),
        official_grader_command: z.array(z.string().min(1)).nullable().default(null),
      })
      .strict(),
    artifacts: z
      .object({
        root: z.string().min(1).default("artifacts/runs"),
        retain_raw_html: z.boolean().default(true),
        retain_screenshots: z.boolean().default(true),
      })
      .strict(),
    state: z
      .object({
        database: z.string().min(1).default(".trueeval/state.db"),
      })
      .strict()
      .default({ database: ".trueeval/state.db" }),
  })
  .strict();

export type RunManifest = z.infer<typeof RunManifestSchema>;

export const ExecutionStatusSchema = z.enum([
  "completed",
  "timeout",
  "rate_limited",
  "provider_error",
  "policy_refusal",
  "parse_error",
  "cancelled",
  "submission_unconfirmed",
  "collection_failed",
]);

export type ExecutionStatus = z.infer<typeof ExecutionStatusSchema>;

export const ErrorRecordSchema = z
  .object({
    code: z.string().min(1),
    message: z.string().min(1),
    retryable: z.boolean(),
  })
  .strict();

export const RawCitationSchema = z
  .object({
    citation_id: z.string().min(1),
    url: NullableString,
    title: NullableString,
  })
  .passthrough();

export const RawSUTResultSchema = z
  .object({
    schema_version: z.literal("trueeval.raw_sut_result.v0.1"),
    run_id: z.string().min(1),
    case_id: z.string().min(1),
    attempt_id: z.string().min(1),
    task_id: z.string().min(1),
    sut_id: z.string().min(1),
    status: ExecutionStatusSchema,
    submitted_at: NullableString,
    completed_at: NullableString,
    raw_answer_text: NullableString,
    raw_citations: z.array(RawCitationSchema),
    raw_response: ArtifactRefSchema.nullable(),
    screenshots: z.array(ArtifactRefSchema),
    events: ArtifactRefSchema.nullable(),
    usage: z
      .object({
        latency_ms: z.number().int().nonnegative(),
        input_tokens: z.number().int().nonnegative().nullable(),
        output_tokens: z.number().int().nonnegative().nullable(),
        search_calls: z.number().int().nonnegative().nullable(),
        cost_usd: z.number().nonnegative().nullable(),
      })
      .strict(),
    collection: z
      .object({
        answer_status: z.enum(["complete", "partial", "not_observable"]),
        citation_status: z.enum([
          "collected",
          "product_absent",
          "adapter_failed",
          "not_observable",
        ]),
      })
      .strict(),
    error: ErrorRecordSchema.nullable(),
  })
  .strict();

export type RawSUTResult = z.infer<typeof RawSUTResultSchema>;

export const CitationRecordSchema = z
  .object({
    citation_id: z.string().min(1),
    display_text: NullableString,
    visible_url: NullableString,
    resolved_url: NullableString,
    quoted_text: NullableString,
    claim_ids: z.array(z.string().min(1)),
    collection_status: z.enum([
      "resolved",
      "visible_only",
      "product_absent",
      "adapter_failed",
      "unresolvable",
    ]),
  })
  .strict();

export type CitationRecord = z.infer<typeof CitationRecordSchema>;

export const ClaimRecordSchema = z
  .object({
    claim_id: z.string().min(1),
    text: z.string().min(1),
    source_span: z
      .object({
        start: z.number().int().nonnegative(),
        end: z.number().int().nonnegative(),
      })
      .strict(),
    importance: z.enum(["major", "minor"]),
    verifiability: z.enum(["externally_verifiable", "opinion", "non_verifiable"]),
    citation_ids: z.array(z.string().min(1)),
  })
  .strict()
  .refine((claim) => claim.source_span.end >= claim.source_span.start, {
    message: "claim source span end must not precede start",
  });

export const ResearchSubmissionSchema = z
  .object({
    schema_version: z.literal("trueeval.research_submission.v0.1"),
    run_id: z.string().min(1),
    case_id: z.string().min(1),
    attempt_id: z.string().min(1),
    task_id: z.string().min(1),
    track: ResearchTrackSchema,
    final_answer: z.string(),
    sections: z.array(
      z
        .object({
          section_id: z.string().min(1),
          heading: NullableString,
          text: z.string(),
        })
        .strict(),
    ),
    claims: z.array(ClaimRecordSchema),
    citations: z.array(CitationRecordSchema),
    attachments: z.array(ArtifactRefSchema),
    normalization: z
      .object({
        normalizer_id: z.string().min(1),
        normalizer_version: z.string().min(1),
        source_artifact_sha256: z.string().regex(/^sha256:[a-f0-9]{64}$/),
        citation_collection_status: z.enum([
          "collected",
          "product_absent",
          "adapter_failed",
          "not_observable",
        ]),
      })
      .strict(),
  })
  .strict();

export type ResearchSubmission = z.infer<typeof ResearchSubmissionSchema>;

export const ScoreRecordSchema = z
  .object({
    schema_version: z.literal("trueeval.score.v0.1"),
    run_id: z.string().min(1),
    case_id: z.string().min(1),
    attempt_id: z.string().min(1),
    task_id: z.string().min(1),
    namespace: z.enum(["official", "trueeval"]),
    metric_id: z.string().min(1),
    role: z.enum(["gate", "score", "diagnostic"]),
    value: z.union([z.number(), z.string(), z.boolean()]).nullable(),
    status: z.enum(["scored", "failed", "not_observable", "not_applicable"]),
    grader: z
      .object({
        id: z.string().min(1),
        version: z.string().min(1),
        config_hash: z.string().regex(/^sha256:[a-f0-9]{64}$/),
      })
      .strict(),
    evidence_refs: z.array(ArtifactRefSchema),
    detail: z.record(z.string(), z.unknown()),
  })
  .strict();

export type ScoreRecord = z.infer<typeof ScoreRecordSchema>;

export const GoldRecordSchema = z
  .object({
    schema_version: z.literal("trueeval.research_gold.v0.1"),
    task_id: z.string().min(1),
    answer_type: z.string().min(1),
    reference_answer: z.string().nullable(),
    acceptable_answers: z.array(z.string()),
    unacceptable_answers: z.array(z.string()),
    claims: z.array(z.unknown()),
    temporal_scope: z.record(z.string(), z.unknown()),
    official_grader_payload: z.record(z.string(), z.unknown()),
    provenance: z.record(z.string(), z.unknown()),
  })
  .passthrough();

export type GoldRecord = z.infer<typeof GoldRecordSchema>;

export const JudgeProfileSchema = z
  .object({
    schema_version: z.literal("trueeval.judge_profile.v0.1"),
    judge_profile_id: z.string().min(1),
    transport: z.enum(["openai_compatible", "process"]),
    base_url: z.string().url().optional(),
    api_key_env: z.string().min(1).optional(),
    command: z.array(z.string().min(1)).optional(),
    model: z.string().min(1),
    temperature: z.number().min(0).max(2).default(0),
    seed: z.number().int().nullable().default(null),
    max_output_tokens: z.number().int().positive().default(2048),
    timeout_seconds: z.number().int().positive().default(120),
    max_retries: z.number().int().min(0).max(5).default(2),
  })
  .strict()
  .superRefine((profile, context) => {
    if (profile.transport === "openai_compatible") {
      if (!profile.base_url) context.addIssue({ code: "custom", message: "base_url is required" });
      if (!profile.api_key_env) context.addIssue({ code: "custom", message: "api_key_env is required" });
    }
    if (profile.transport === "process" && (!profile.command || profile.command.length === 0)) {
      context.addIssue({ code: "custom", message: "command is required" });
    }
  });

export type JudgeProfile = z.infer<typeof JudgeProfileSchema>;

export const ShortFactJudgeVerdictSchema = z
  .object({
    schema_version: z.literal("trueeval.short_fact_judge_verdict.v0.1"),
    extracted_answer: z.string(),
    conclusion: z.enum(["correct", "incorrect"]),
    rationale: z.string().min(1),
    confidence: z.number().min(0).max(1).nullable(),
  })
  .strict();

export type ShortFactJudgeVerdict = z.infer<typeof ShortFactJudgeVerdictSchema>;

export const EvidenceSnapshotSchema = z
  .object({
    schema_version: z.literal("trueeval.evidence_snapshot.v0.1"),
    evidence_id: z.string().min(1),
    citation_id: z.string().min(1),
    requested_url: z.string().min(1),
    resolved_url: NullableString,
    redirect_chain: z.array(z.string()),
    retrieved_at: z.string().min(1),
    status: z.enum(["fetched", "paywalled", "login_required", "blocked", "not_found", "error"]),
    http_status: z.number().int().nullable(),
    title: NullableString,
    publisher: NullableString,
    published_at: NullableString,
    text_artifact: ArtifactRefSchema.nullable(),
    html_artifact: ArtifactRefSchema.nullable(),
    sha256: NullableString,
    error_code: NullableString,
  })
  .strict();

export type EvidenceSnapshot = z.infer<typeof EvidenceSnapshotSchema>;

export const CitationVerdictSchema = z
  .object({
    schema_version: z.literal("trueeval.citation_verdict.v0.1"),
    claim_id: z.string().min(1),
    citation_id: z.string().min(1),
    verdict: z.enum([
      "supported",
      "partially_supported",
      "contradicted",
      "irrelevant",
      "insufficient_evidence",
      "evidence_unavailable",
    ]),
    score: z.number().min(0).max(1).nullable(),
    confidence: z.number().min(0).max(1),
    evidence_spans: z.array(
      z
        .object({
          artifact_id: z.string().min(1),
          start: z.number().int().nonnegative(),
          end: z.number().int().nonnegative(),
        })
        .strict(),
    ),
    rationale: z.string().min(1),
    flags: z.array(z.string()),
  })
  .strict();

export type CitationVerdict = z.infer<typeof CitationVerdictSchema>;

export const LongFormJudgeVerdictSchema = z
  .object({
    schema_version: z.literal("trueeval.long_form_judge_verdict.v0.1"),
    coverage: z.number().min(0).max(1),
    insight: z.number().min(0).max(1),
    instruction_following: z.number().min(0).max(1),
    clarity: z.number().min(0).max(1),
    factual_claims: z.array(
      z
        .object({
          claim: z.string().min(1),
          verdict: z.enum(["supported", "unsupported", "uncertain"]),
          rationale: z.string().min(1),
        })
        .strict(),
    ),
    confidence: z.number().min(0).max(1),
    rationale: z.string().min(1),
  })
  .strict();

export type LongFormJudgeVerdict = z.infer<typeof LongFormJudgeVerdictSchema>;

export const DeepResearchOfficialVerdictSchema = z
  .object({
    schema_version: z.literal("trueeval.deepresearch_official_verdict.v0.1"),
    upstream_commit: z.string().min(7),
    quality_score: z.number().min(0).max(10),
    quality_dimensions: z.record(z.string(), z.number().min(0).max(10)),
    fact_ratio: z.number().min(0).max(1).nullable(),
    right_count: z.number().int().nonnegative(),
    wrong_count: z.number().int().nonnegative(),
    unknown_count: z.number().int().nonnegative(),
    raw: z.record(z.string(), z.unknown()),
  })
  .strict();

export type DeepResearchOfficialVerdict = z.infer<typeof DeepResearchOfficialVerdictSchema>;

export const JudgeJobSchema = z
  .object({
    schema_version: z.literal("trueeval.judge_job.v0.1"),
    judge_job_id: z.string().min(1),
    run_id: z.string().min(1),
    case_id: z.string().min(1),
    attempt_id: z.string().min(1),
    grader_id: z.string().min(1),
    grader_version: z.string().min(1),
    purpose: z.enum([
      "claim_extraction",
      "claim_citation_mapping",
      "citation_entailment",
      "long_form_quality",
      "source_classification",
      "adjudication",
      "short_fact_accuracy",
      "fixture_quality",
    ]),
    input_refs: z.array(ArtifactRefSchema),
    allowed_input_fields: z.array(z.string().min(1)),
    judge_config: z
      .object({
        provider: z.string().min(1),
        model: z.string().min(1),
        model_version: NullableString,
        temperature: z.number().nonnegative(),
        seed: z.number().int().nullable(),
        max_output_tokens: z.number().int().positive(),
        prompt_id: z.string().min(1),
        prompt_version: z.string().min(1),
        prompt_sha256: z.string().regex(/^sha256:[a-f0-9]{64}$/),
        output_schema: z.string().min(1),
      })
      .strict(),
    cache_key: z.string().min(1),
    cache_source_job_id: NullableString,
    created_at: z.string().min(1),
  })
  .strict();

export type JudgeJob = z.infer<typeof JudgeJobSchema>;

export const FixtureJudgeVerdictSchema = z
  .object({
    schema_version: z.literal("trueeval.fixture_judge_verdict.v0.1"),
    judge_job_id: z.string().min(1),
    score: z.number().min(0).max(1),
    confidence: z.number().min(0).max(1),
    rationale: z.string().min(1),
  })
  .strict();

export type FixtureJudgeVerdict = z.infer<typeof FixtureJudgeVerdictSchema>;
