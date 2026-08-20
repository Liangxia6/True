"""TaskRun and related runtime records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from trueeval.core.errors import ErrorInfo
from trueeval.core.schemas.common import VersionedModel
from trueeval.core.state_machine.states import TaskRunState
from trueeval.core.timeutil import utc_now


class TaskRun(VersionedModel):
    """One independent execution of one task inside a Run."""

    schema_version: str = "trueeval.task_run.v0.1"
    run_id: str
    execution_id: str
    task_id: str
    repeat_index: int
    status: TaskRunState = TaskRunState.CREATED
    attempt_count: int = 0
    idempotency_key: str | None = None
    external_job_id: str | None = None
    deadline: datetime | None = None
    last_error: ErrorInfo | None = None
    input_uri: str | None = None
    output_uri: str | None = None
    raw_result_uri: str | None = None
    answer_uri: str | None = None
    evidence_uris: list[str] = Field(default_factory=list)
    session_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)
    extra: dict[str, Any] = Field(default_factory=dict)
