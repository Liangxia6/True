"""Legal TaskRun transitions. All runtime changes go through this service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from trueeval.core.errors import ErrorInfo, IllegalTransitionError
from trueeval.core.state_machine.states import TERMINAL_STATES, TaskRunState

ALLOWED: dict[TaskRunState, frozenset[TaskRunState]] = {
    TaskRunState.CREATED: frozenset({TaskRunState.MATERIALIZED, TaskRunState.CANCELLED}),
    TaskRunState.MATERIALIZED: frozenset(
        {
            TaskRunState.READY,
            TaskRunState.WAITING_IMPORT,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
            TaskRunState.UNSUPPORTED,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.READY: frozenset(
        {
            TaskRunState.SUBMITTING,
            TaskRunState.UNSUPPORTED,
            TaskRunState.CANCELLED,
            TaskRunState.FAILED_FINAL,
        }
    ),
    TaskRunState.SUBMITTING: frozenset(
        {
            TaskRunState.SUBMITTED,
            TaskRunState.COMPLETED_SYNC,
            TaskRunState.WAITING_EXTERNAL,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.SUBMITTED: frozenset(
        {
            TaskRunState.RUNNING,
            TaskRunState.WAITING_EXTERNAL,
            TaskRunState.COMPLETED,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
            TaskRunState.TIMED_OUT,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.COMPLETED_SYNC: frozenset({TaskRunState.COLLECTED, TaskRunState.FAILED_FINAL}),
    TaskRunState.RUNNING: frozenset(
        {
            TaskRunState.WAITING_EXTERNAL,
            TaskRunState.COMPLETED,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
            TaskRunState.TIMED_OUT,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.WAITING_EXTERNAL: frozenset(
        {
            TaskRunState.RUNNING,
            TaskRunState.COMPLETED,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
            TaskRunState.TIMED_OUT,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.WAITING_IMPORT: frozenset(
        {
            TaskRunState.COLLECTED,
            TaskRunState.FAILED_FINAL,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.COMPLETED: frozenset(
        {
            TaskRunState.COLLECTED,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
        }
    ),
    TaskRunState.COLLECTED: frozenset(
        {
            TaskRunState.NORMALIZED,
            TaskRunState.FAILED_RETRYABLE,
            TaskRunState.FAILED_FINAL,
        }
    ),
    TaskRunState.NORMALIZED: frozenset({TaskRunState.GRADING, TaskRunState.FAILED_FINAL}),
    TaskRunState.GRADING: frozenset({TaskRunState.SCORED, TaskRunState.FAILED_FINAL}),
    TaskRunState.FAILED_RETRYABLE: frozenset(
        {
            TaskRunState.RETRYING,
            TaskRunState.FAILED_FINAL,
            TaskRunState.CANCELLED,
        }
    ),
    TaskRunState.RETRYING: frozenset(
        {
            TaskRunState.RUNNING,
            TaskRunState.SUBMITTING,
            TaskRunState.READY,
            TaskRunState.FAILED_FINAL,
            TaskRunState.CANCELLED,
        }
    ),
}


def validate_transition(current: TaskRunState, target: TaskRunState) -> None:
    if current == target:
        return
    if current in TERMINAL_STATES:
        raise IllegalTransitionError(current.value, target.value)
    allowed = ALLOWED.get(current, frozenset())
    if target not in allowed:
        raise IllegalTransitionError(current.value, target.value)


class StateTransitionService:
    """Validates and records a TaskRun status change inside a caller-owned transaction."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self._now = now

    def apply(
        self,
        *,
        current: TaskRunState,
        target: TaskRunState,
        error: ErrorInfo | None = None,
    ) -> tuple[TaskRunState, datetime]:
        validate_transition(current, target)
        return target, self._now()
