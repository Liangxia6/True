"""Grader specification and grading context."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from trueeval.core.schemas.benchmark import GoldRecord, TaskSpec
from trueeval.core.schemas.common import VersionedModel

GraderKind = Literal["hard", "official", "citation", "llm_judge", "diagnostic"]


class GraderSpec(VersionedModel):
    schema_version: str = "trueeval.grader_spec.v0.1"
    grader_id: str
    version: str
    kind: GraderKind = "official"
    metrics: list[str] = Field(default_factory=list)
    prompt_id: str | None = None
    prompt_hash: str | None = None
    judge_provider: str | None = None
    judge_model: str | None = None
    judge_region: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    requires_gold: bool = False
    requires_network: bool = False


class GradeContext(VersionedModel):
    schema_version: str = "trueeval.grade_context.v0.1"
    run_id: str
    execution_id: str
    grading_job_id: str
    task: TaskSpec
    gold: GoldRecord | None = None
    grader_config_hash: str
    input_artifact_hash: str
    judge_enabled: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)
