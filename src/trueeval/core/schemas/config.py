"""Run configuration loaded from YAML. Secrets never live in this file."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from trueeval.core.errors import SchemaVersionError
from trueeval.core.schemas.common import VersionedModel

SUPPORTED_RUN_CONFIG = ("trueeval.run_config.v0.1",)


class BenchmarkRef(VersionedModel):
    schema_version: str = "trueeval.run_config.benchmark.v0.1"
    id: str
    split: str
    version: str | None = None
    sample_limit: int | None = None
    task_ids: list[str] | None = None


class SUTRef(VersionedModel):
    schema_version: str = "trueeval.run_config.sut.v0.1"
    id: str
    model: str | None = None
    channel: Literal["API_SYNC", "API_ASYNC", "MANUAL_IMPORT"] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecutionConfig(VersionedModel):
    schema_version: str = "trueeval.run_config.execution.v0.1"
    repeats: int = 1
    submit_concurrency: int = 2
    poll_concurrency: int = 4
    collect_concurrency: int = 2
    fetch_concurrency: int = 4
    judge_concurrency: int = 2
    poll_interval_seconds: float = 10.0
    task_timeout_seconds: int = 3600
    allow_regeneration: bool = False
    max_attempts: int = 3
    seed: int = 0
    estimated_cost_usd_per_task: float = 1.0


class GradingConfig(VersionedModel):
    schema_version: str = "trueeval.run_config.grading.v0.1"
    graders: list[str] = Field(default_factory=list)
    judge_provider: str | None = None
    judge_model: str | None = None
    judge_region: str | None = None
    fetch_citations: bool = False


class BudgetConfig(VersionedModel):
    schema_version: str = "trueeval.run_config.budget.v0.1"
    max_cost_usd: float = 100.0
    hard_stop: bool = True


class RetentionConfig(VersionedModel):
    schema_version: str = "trueeval.run_config.retention.v0.1"
    artifact_days: int = 365
    protected_days: int = 365
    evaluation_days: int = 730


class GateConfig(VersionedModel):
    schema_version: str = "trueeval.run_config.gate.v0.1"
    data_region: str = "unspecified"
    authorized_channel: str = "api"
    allow_decrypt_upload: bool = False
    allow_pii_outbound: bool = False
    operator: str = "local"


class RunConfig(VersionedModel):
    """User-facing run configuration. Resolved values are written to Manifest."""

    schema_version: str = "trueeval.run_config.v0.1"
    benchmark: BenchmarkRef
    sut: SUTRef
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    grading: GradingConfig = Field(default_factory=GradingConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    gate: GateConfig = Field(default_factory=GateConfig)
    workspace: str = "."
    created_by: str = "local"

    @field_validator("schema_version")
    @classmethod
    def _supported(cls, value: str) -> str:
        if value not in SUPPORTED_RUN_CONFIG:
            raise SchemaVersionError(value, list(SUPPORTED_RUN_CONFIG))
        return value
