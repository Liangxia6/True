"""ScoreRecord, GradingJob, and report summary types."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from trueeval.core.errors import ErrorInfo
from trueeval.core.schemas.common import VersionedModel
from trueeval.core.timeutil import utc_now

ScoreStatus = Literal["scored", "not_observable", "excluded", "grader_error"]


class ScoreRecord(VersionedModel):
    schema_version: str = "trueeval.score_record.v0.1"
    score_id: str
    run_id: str
    execution_id: str
    task_id: str
    repeat_index: int
    grading_job_id: str
    grader_id: str
    grader_version: str
    metric: str
    raw_value: float | None = None
    normalized_value: float | None = None
    coverage: float | None = None
    rationale: str | None = None
    evidence_uri: str | None = None
    grader_config_hash: str
    input_artifact_hash: str
    status: ScoreStatus = "scored"
    error: ErrorInfo | None = None
    created_at: datetime = Field(default_factory=utc_now)


class GradingJob(VersionedModel):
    schema_version: str = "trueeval.grading_job.v0.1"
    grading_job_id: str
    run_id: str
    execution_id: str
    grader_id: str
    grader_version: str
    status: Literal["created", "running", "succeeded", "failed"] = "created"
    config_hash: str
    selected: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    extra: dict[str, Any] = Field(default_factory=dict)


class MetricSummary(VersionedModel):
    schema_version: str = "trueeval.metric_summary.v0.1"
    metric: str
    mean: float | None = None
    n: int = 0
    coverage: float = 0.0
    p50: float | None = None
    p95: float | None = None
    variance: float | None = None


class RunSummary(VersionedModel):
    schema_version: str = "trueeval.run_summary.v0.1"
    run_id: str
    total_tasks: int
    total_executions: int
    scorable_executions: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    answer_status_counts: dict[str, int] = Field(default_factory=dict)
    official_metrics: list[MetricSummary] = Field(default_factory=list)
    trueeval_metrics: list[MetricSummary] = Field(default_factory=list)
    latency_ms: dict[str, float | None] = Field(default_factory=dict)
    usage: dict[str, float | None] = Field(default_factory=dict)
    selected_grading_jobs: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    evidence_index_uri: str | None = None
