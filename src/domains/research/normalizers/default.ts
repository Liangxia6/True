import type { ResearchNormalizer } from "../contracts/adapters.js";
import {
  ResearchSubmissionSchema,
  type RawSUTResult,
  type ResearchSubmission,
  type TaskSpec,
} from "../../../schemas/contracts.js";

export class DefaultResearchNormalizer implements ResearchNormalizer {
  async normalize(raw: RawSUTResult, task: TaskSpec): Promise<ResearchSubmission> {
    if (raw.status !== "completed" || raw.raw_answer_text === null || raw.raw_response === null) {
      throw new Error(`Cannot normalize incomplete result for ${task.task_id}`);
    }
    return ResearchSubmissionSchema.parse({
      schema_version: "trueeval.research_submission.v0.1",
      run_id: raw.run_id,
      case_id: raw.case_id,
      attempt_id: raw.attempt_id,
      task_id: raw.task_id,
      track: task.track,
      final_answer: raw.raw_answer_text,
      sections: [
        {
          section_id: "section-1",
          heading: null,
          text: raw.raw_answer_text,
        },
      ],
      claims: [],
      citations: raw.raw_citations.map((citation) => ({
        citation_id: citation.citation_id,
        display_text: citation.title,
        visible_url: citation.url,
        resolved_url: null,
        quoted_text: null,
        claim_ids: [],
        collection_status: citation.url ? "visible_only" : "unresolvable",
      })),
      attachments: [],
      normalization: {
        normalizer_id: "trueeval.research.default",
        normalizer_version: "v0.1",
        source_artifact_sha256: raw.raw_response.sha256,
        citation_collection_status: raw.collection.citation_status,
      },
    });
  }
}
