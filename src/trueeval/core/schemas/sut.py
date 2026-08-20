"""SUT, session, submission, and raw result schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from trueeval.core.errors import ErrorInfo
from trueeval.core.schemas.common import VersionedModel
from trueeval.core.timeutil import utc_now

Channel = Literal["API_SYNC", "API_ASYNC", "MANUAL_IMPORT"]
JobPhase = Literal[
    "queued",
    "running",
    "waiting",
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "unknown",
    "not_found",
]


class CapabilitySet(VersionedModel):
    schema_version: str = "trueeval.capability_set.v0.1"
    provider_idempotency: bool = False
    submission_lookup: bool = False
    web_search: bool = False
    browser: bool = False
    citations: bool = False
    search_results: bool = False
    trajectory: bool = False
    sync: bool = False
    async_jobs: bool = False
    extras: list[str] = Field(default_factory=list)

    def has(self, name: str) -> bool:
        if hasattr(self, name):
            value = getattr(self, name)
            if isinstance(value, bool):
                return value
        return name in self.extras


class SUTSpec(VersionedModel):
    """Adapter identity and declared capabilities. Secrets are never stored here."""

    schema_version: str = "trueeval.sut_spec.v0.1"
    sut_id: str
    provider: str
    product: str
    model: str
    endpoint_family: str
    channel: Channel
    provider_idempotency: bool
    submission_lookup: bool
    parameters: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_usd: float = 1.0


class SessionHandle(VersionedModel):
    schema_version: str = "trueeval.session_handle.v0.1"
    session_id: str
    execution_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class InputPackage(VersionedModel):
    schema_version: str = "trueeval.input_package.v0.1"
    task_id: str
    prompt: str
    language: str = "en"
    as_of: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    attachments: list[Any] = Field(default_factory=list)
    input_hash: str


class Submission(VersionedModel):
    schema_version: str = "trueeval.submission.v0.1"
    submission_id: str
    execution_id: str
    idempotency_key: str
    external_job_id: str | None = None
    channel: Channel
    submitted_at: datetime = Field(default_factory=utc_now)
    request_uri: str | None = None
    response_uri: str | None = None
    lookup_available: bool = False


class JobStatus(VersionedModel):
    schema_version: str = "trueeval.job_status.v0.1"
    phase: JobPhase
    external_job_id: str | None = None
    retryable: bool = False
    provider_status: str | None = None
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RawSUTResult(VersionedModel):
    """Immutable raw collect output. Normalization must not mutate this object."""

    schema_version: str = "trueeval.raw_sut_result.v0.1"
    execution_id: str
    channel: Channel
    final_answer: str | None = None
    raw_response: dict[str, Any] | str | None = None
    search_results: list[dict[str, Any]] | None = None
    citations: list[dict[str, Any]] | None = None
    trajectory: list[dict[str, Any]] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    status: str = "completed"
    error: ErrorInfo | None = None
    collected_at: datetime = Field(default_factory=utc_now)
