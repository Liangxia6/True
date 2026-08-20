"""RunManifest and related frozen run identity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from trueeval.core.schemas.common import VersionedModel
from trueeval.core.schemas.score import RunSummary
from trueeval.core.timeutil import utc_now


class BenchmarkPin(VersionedModel):
    schema_version: str = "trueeval.manifest.benchmark.v0.1"
    benchmark_id: str
    version: str
    split: str
    commit_sha: str
    data_hash: str
    license: str
    task_count: int


class SUTPin(VersionedModel):
    schema_version: str = "trueeval.manifest.sut.v0.1"
    sut_id: str
    provider: str
    product: str
    model: str
    endpoint_family: str
    channel: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    provider_idempotency: bool
    submission_lookup: bool


class GraderPin(VersionedModel):
    schema_version: str = "trueeval.manifest.grader.v0.1"
    grader_id: str
    version: str
    prompt_hash: str | None = None
    config_hash: str
    config: dict[str, Any] = Field(default_factory=dict)


class ExecutionPin(VersionedModel):
    schema_version: str = "trueeval.manifest.execution.v0.1"
    repeats: int
    submit_concurrency: int
    poll_concurrency: int
    collect_concurrency: int
    fetch_concurrency: int
    judge_concurrency: int
    poll_interval_seconds: float
    task_timeout_seconds: int
    allow_regeneration: bool
    max_attempts: int
    seed: int
    estimated_cost_usd_per_task: float


class BudgetPin(VersionedModel):
    schema_version: str = "trueeval.manifest.budget.v0.1"
    max_cost_usd: float
    hard_stop: bool


class RetentionPin(VersionedModel):
    schema_version: str = "trueeval.manifest.retention.v0.1"
    artifact_days: int
    protected_days: int
    evaluation_days: int


class RunManifest(VersionedModel):
    """Immutable run identity. Configuration changes require a new Run."""

    schema_version: str = "trueeval.run_manifest.v0.1"
    run_id: str
    benchmark: BenchmarkPin
    sut: SUTPin
    graders: list[GraderPin] = Field(default_factory=list)
    execution: ExecutionPin
    budget: BudgetPin
    retention: RetentionPin
    seed: int
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str
    code_commit_sha: str | None = None
    gate_record_uri: str | None = None
    resolved_config: dict[str, Any] = Field(default_factory=dict)
    workspace: str = "."


__all__ = ["BudgetPin", "BenchmarkPin", "ExecutionPin", "GraderPin", "RetentionPin", "RunManifest", "RunSummary", "SUTPin"]
