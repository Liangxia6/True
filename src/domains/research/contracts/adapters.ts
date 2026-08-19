import type {
  RawSUTResult,
  ResearchSubmission,
  RunManifest,
  SUTSpec,
  TaskSpec,
} from "../../../schemas/contracts.js";

export interface BenchmarkAdapter {
  listTasks(split: string): Promise<TaskSpec[]>;
}

export interface CaseIdentity {
  runId: string;
  caseId: string;
  attemptId: string;
}

export interface SUTRequest {
  identity: CaseIdentity;
  task: TaskSpec;
  timeoutSeconds: number;
  artifactDirectory: string;
  onSubmissionConfirmed(detail: Record<string, unknown>): Promise<void>;
}

export interface SUTAdapter {
  spec(): Promise<SUTSpec>;
  openWorker(): Promise<void>;
  execute(request: SUTRequest): Promise<RawSUTResult>;
  closeWorker(): Promise<void>;
}

export interface ResearchNormalizer {
  normalize(raw: RawSUTResult, task: TaskSpec): Promise<ResearchSubmission>;
}

export interface LoadedManifest {
  manifest: RunManifest;
  sourcePath: string;
}
