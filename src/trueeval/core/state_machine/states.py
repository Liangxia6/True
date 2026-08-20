"""TaskRun lifecycle states."""

from __future__ import annotations

from enum import StrEnum


class TaskRunState(StrEnum):
    CREATED = "CREATED"
    MATERIALIZED = "MATERIALIZED"
    READY = "READY"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    COMPLETED_SYNC = "COMPLETED_SYNC"
    RUNNING = "RUNNING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    WAITING_IMPORT = "WAITING_IMPORT"
    COMPLETED = "COMPLETED"
    COLLECTED = "COLLECTED"
    NORMALIZED = "NORMALIZED"
    GRADING = "GRADING"
    SCORED = "SCORED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    RETRYING = "RETRYING"
    FAILED_FINAL = "FAILED_FINAL"
    TIMED_OUT = "TIMED_OUT"
    UNSUPPORTED = "UNSUPPORTED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset(
    {
        TaskRunState.SCORED,
        TaskRunState.FAILED_FINAL,
        TaskRunState.TIMED_OUT,
        TaskRunState.UNSUPPORTED,
        TaskRunState.CANCELLED,
    }
)

GENERATION_DONE_STATES = frozenset(
    {
        TaskRunState.NORMALIZED,
        TaskRunState.GRADING,
        TaskRunState.SCORED,
        TaskRunState.FAILED_FINAL,
        TaskRunState.TIMED_OUT,
        TaskRunState.UNSUPPORTED,
        TaskRunState.CANCELLED,
    }
)
