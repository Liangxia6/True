export type RunStatus =
  | "completed"
  | "probe_completed"
  | "login_required"
  | "timeout"
  | "provider_error"
  | "ui_changed"
  | "submission_unconfirmed"
  | "result_extraction_failed";

export interface RunnerOptions {
  prompt: string;
  taskId: string;
  profileDir: string;
  artifactsDir: string;
  timeoutSeconds: number;
  loginTimeoutSeconds: number;
  pollIntervalMs: number;
  stablePolls: number;
  headless: boolean;
  keepOpen: boolean;
  researchMode: boolean;
  browserChannel?: string;
  probeOnly: boolean;
  allowAnonymous: boolean;
}

export interface Citation {
  citation_id: string;
  url: string;
  title: string | null;
  retrieved_at: string;
}

export interface RunEvent {
  at: string;
  state: string;
  detail?: Record<string, unknown>;
}

export interface DoubaoRunResult {
  schema_version: "trueeval.research_answer.v0.1";
  run_id: string;
  task_id: string;
  status: RunStatus;
  final_answer: string | null;
  citations: Citation[];
  artifacts: {
    result_dir: string;
    raw_html_uri: string | null;
    final_markdown_uri: string | null;
    screenshot_uri: string | null;
    events_uri: string;
  };
  usage: {
    latency_ms: number;
    input_tokens: null;
    output_tokens: null;
    search_calls: null;
    cost_usd: null;
  };
  sut: {
    provider: "doubao";
    product: "web_deep_research" | "web_chat";
    model: null;
    endpoint_family: "browser_ui";
    parameters: {
      entry_url: string;
      browser_channel: string | null;
      research_mode_requested: boolean;
    };
  };
  error: {
    code: string;
    message: string;
  } | null;
}
