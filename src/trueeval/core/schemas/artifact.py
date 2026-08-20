"""Artifact references and the unified Research Answer Artifact."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from trueeval.core.errors import ErrorInfo
from trueeval.core.schemas.common import VersionedModel
from trueeval.core.timeutil import utc_now

AnswerStatus = Literal[
    "completed",
    "timeout",
    "rate_limited",
    "provider_error",
    "policy_refusal",
    "parse_error",
    "cancelled",
]

ArtifactKind = Literal[
    "input",
    "raw_request",
    "raw_response",
    "research_answer",
    "search_results",
    "report",
    "error",
    "grader_output",
    "gate_record",
    "manual_package",
]


class ArtifactRef(VersionedModel):
    schema_version: str = "trueeval.artifact_ref.v0.1"
    uri: str
    sha256: str
    kind: ArtifactKind
    media_type: str = "application/json"
    bytes: int = 0
    protected: bool = False
    source_sha256: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Claim(VersionedModel):
    schema_version: str = "trueeval.research_answer.claim.v0.1"
    claim_id: str
    text: str
    citation_ids: list[str] = Field(default_factory=list)


class Citation(VersionedModel):
    schema_version: str = "trueeval.research_answer.citation.v0.1"
    citation_id: str
    url: str | None = None
    title: str | None = None
    quoted_text: str | None = None
    retrieved_at: datetime | None = None
    observable: bool = True


class Usage(VersionedModel):
    schema_version: str = "trueeval.research_answer.usage.v0.1"
    input_tokens: int | None = None
    output_tokens: int | None = None
    search_calls: int | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None


class SUTIdentity(VersionedModel):
    schema_version: str = "trueeval.research_answer.sut.v0.1"
    provider: str
    product: str
    model: str
    endpoint_family: str
    channel: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ArtifactPointers(VersionedModel):
    schema_version: str = "trueeval.research_answer.artifacts.v0.1"
    raw_response_uri: str | None = None
    raw_request_uri: str | None = None
    search_results_uri: str | None = None
    trajectory_uri: str | None = None
    report_uri: str | None = None


class ResearchAnswer(VersionedModel):
    """Unified `trueeval.research_answer.v0.1` evaluation artifact."""

    schema_version: str = "trueeval.research_answer.v0.1"
    run_id: str
    execution_id: str
    task_id: str
    repeat_index: int = 0
    status: AnswerStatus
    final_answer: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    artifacts: ArtifactPointers = Field(default_factory=ArtifactPointers)
    usage: Usage = Field(default_factory=Usage)
    sut: SUTIdentity
    error: ErrorInfo | None = None
    channel: str
    created_at: datetime = Field(default_factory=utc_now)
