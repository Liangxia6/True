export const caseStates = [
  "CREATED",
  "QUEUED",
  "RESOURCE_LEASED",
  "WORKER_READY",
  "SESSION_CREATED",
  "SUBMITTING",
  "SUBMITTED",
  "RUNNING",
  "COMPLETED",
  "COLLECTED",
  "NORMALIZED",
  "READY_FOR_GRADING",
  "GRADING",
  "SCORED",
  "DONE",
  "NEEDS_LOGIN",
  "NEEDS_HUMAN_VERIFICATION",
  "CAPABILITY_MISMATCH",
  "UI_CHANGED",
  "SUBMISSION_UNCONFIRMED",
  "PROVIDER_ERROR",
  "TIMED_OUT",
  "COLLECTION_FAILED",
  "NORMALIZATION_FAILED",
  "GRADING_FAILED",
  "CANCELLED",
] as const;

export type CaseState = (typeof caseStates)[number];

const normalTransitions: Readonly<Record<CaseState, readonly CaseState[]>> = {
  CREATED: ["QUEUED"],
  QUEUED: ["RESOURCE_LEASED"],
  RESOURCE_LEASED: ["WORKER_READY"],
  WORKER_READY: ["SESSION_CREATED"],
  SESSION_CREATED: ["SUBMITTING"],
  SUBMITTING: ["SUBMITTED"],
  SUBMITTED: ["RUNNING", "COMPLETED"],
  RUNNING: ["COMPLETED"],
  COMPLETED: ["COLLECTED"],
  COLLECTED: ["NORMALIZED"],
  NORMALIZED: ["READY_FOR_GRADING"],
  READY_FOR_GRADING: ["GRADING"],
  GRADING: ["SCORED"],
  SCORED: ["DONE"],
  DONE: ["GRADING"],
  NEEDS_LOGIN: ["QUEUED", "CANCELLED"],
  NEEDS_HUMAN_VERIFICATION: ["QUEUED", "CANCELLED"],
  CAPABILITY_MISMATCH: [],
  UI_CHANGED: [],
  SUBMISSION_UNCONFIRMED: ["SUBMITTED", "NEEDS_HUMAN_VERIFICATION", "CANCELLED"],
  PROVIDER_ERROR: [],
  TIMED_OUT: [],
  COLLECTION_FAILED: ["COLLECTED", "CANCELLED"],
  NORMALIZATION_FAILED: ["NORMALIZED", "CANCELLED"],
  GRADING_FAILED: ["GRADING", "CANCELLED"],
  CANCELLED: [],
};

const failureStates = new Set<CaseState>([
  "NEEDS_LOGIN",
  "NEEDS_HUMAN_VERIFICATION",
  "CAPABILITY_MISMATCH",
  "UI_CHANGED",
  "SUBMISSION_UNCONFIRMED",
  "PROVIDER_ERROR",
  "TIMED_OUT",
  "COLLECTION_FAILED",
  "NORMALIZATION_FAILED",
  "GRADING_FAILED",
  "CANCELLED",
]);

export function canTransition(from: CaseState, to: CaseState): boolean {
  if (normalTransitions[from].includes(to)) return true;
  return !isTerminalState(from) && failureStates.has(to);
}

export function assertTransition(from: CaseState, to: CaseState): void {
  if (!canTransition(from, to)) {
    throw new Error(`Invalid case transition: ${from} -> ${to}`);
  }
}

export function isTerminalState(state: CaseState): boolean {
  return state === "DONE" || normalTransitions[state].length === 0;
}
