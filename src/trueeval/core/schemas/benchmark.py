"""Benchmark, task, and gold schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from trueeval.core.schemas.common import VersionedModel

TaskFamily = Literal[
    "factoid_research",
    "multi_hop_research",
    "list_research",
    "comparative_research",
    "report_research",
    "temporal_research",
    "insufficient_evidence",
]


class UpstreamRef(VersionedModel):
    schema_version: str = "trueeval.benchmark.upstream.v0.1"
    repo_url: str
    commit_sha: str
    dataset_path: str
    evaluator_path: str
    license: str
    homepage: str | None = None
    usage_restriction: str | None = None

    @field_validator("commit_sha", mode="before")
    @classmethod
    def _sha_as_str(cls, value: object) -> str:
        return str(value)


class SplitSpec(VersionedModel):
    schema_version: str = "trueeval.benchmark.split.v0.1"
    name: str
    public_questions: bool = False
    public_gold: bool = False
    task_count: int = 0
    notes: str | None = None
    mvp: bool | None = None


class DefaultExecution(VersionedModel):
    schema_version: str = "trueeval.benchmark.default_execution.v0.1"
    mode: str = "submission"
    timeout_seconds: int = 900
    max_attempts: int = 1
    internet_required: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    output_contract: str = "research_answer.v0.1"
    required_capabilities: list[str] = Field(default_factory=lambda: ["web_search"])


class BenchmarkSpec(VersionedModel):
    """Frozen benchmark metadata loaded from benchmark.yaml."""

    schema_version: str = "trueeval.research_benchmark.v0.1"
    benchmark_id: str
    name: str
    benchmark_version: str
    domain: str = "research"
    task_family: TaskFamily = "factoid_research"
    upstream: UpstreamRef
    splits: list[SplitSpec] = Field(default_factory=list)
    default_execution: DefaultExecution = Field(default_factory=DefaultExecution)
    official_metrics: list[str] = Field(default_factory=list)
    trueeval_metrics: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    notes: str | None = None
    track: str | None = None
    data_hash: str | None = None
    root_dir: str | None = None


class TaskInput(VersionedModel):
    schema_version: str = "trueeval.research_task.input.v0.1"
    prompt: str
    language: str = "en"
    as_of: str | None = None
    attachments: list[Any] = Field(default_factory=list)


class ExpectedOutput(VersionedModel):
    schema_version: str = "trueeval.research_task.expected_output.v0.1"
    answer_form: Literal["short_text", "list", "structured_json", "report"] = "short_text"
    citation_required: bool = False
    structured_fields: list[str] = Field(default_factory=list)


class TaskConstraints(VersionedModel):
    schema_version: str = "trueeval.research_task.constraints.v0.1"
    internet_required: bool = True
    timeout_seconds: int = 900
    max_search_calls: int | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_domains: list[str] = Field(default_factory=list)
    required_domains: list[str] = Field(default_factory=list)


class Provenance(VersionedModel):
    schema_version: str = "trueeval.provenance.v0.1"
    source_file: str
    source_row: int | None = None
    source_hash: str | None = None
    extraction_version: str | None = None
    extracted_at: str | None = None


class TaskSpec(VersionedModel):
    """Public task. Must not contain gold answers."""

    schema_version: str = "trueeval.research_task.v0.1"
    task_id: str
    benchmark_id: str
    upstream_task_id: str
    split: str
    task_family: TaskFamily = "factoid_research"
    input: TaskInput
    expected_output: ExpectedOutput = Field(default_factory=ExpectedOutput)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    provenance: Provenance | None = None
    tags: list[str] = Field(default_factory=list)


class GoldClaim(VersionedModel):
    schema_version: str = "trueeval.research_gold.claim.v0.1"
    claim_id: str
    statement: str
    importance: str = "required"
    accepted_values: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class GoldRecord(VersionedModel):
    """Private gold. Never passed to SUT adapters."""

    schema_version: str = "trueeval.research_gold.v0.1"
    task_id: str
    answer_type: str = "short_text"
    reference_answer: str | None = None
    acceptable_answers: list[str] = Field(default_factory=list)
    unacceptable_answers: list[str] = Field(default_factory=list)
    claims: list[GoldClaim] = Field(default_factory=list)
    official_grader_payload: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance | None = None
    temporal_scope: dict[str, Any] | None = None
