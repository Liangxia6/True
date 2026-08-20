from __future__ import annotations

import pytest

from trueeval.core.errors import IllegalTransitionError
from trueeval.core.state_machine.states import TaskRunState
from trueeval.core.state_machine.transitions import validate_transition


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (TaskRunState.CREATED, TaskRunState.MATERIALIZED),
        (TaskRunState.MATERIALIZED, TaskRunState.READY),
        (TaskRunState.MATERIALIZED, TaskRunState.WAITING_IMPORT),
        (TaskRunState.READY, TaskRunState.SUBMITTING),
        (TaskRunState.SUBMITTING, TaskRunState.WAITING_EXTERNAL),
        (TaskRunState.COMPLETED, TaskRunState.COLLECTED),
        (TaskRunState.NORMALIZED, TaskRunState.GRADING),
        (TaskRunState.GRADING, TaskRunState.SCORED),
        (TaskRunState.FAILED_RETRYABLE, TaskRunState.RETRYING),
    ],
)
def test_legal_transitions(src: TaskRunState, dst: TaskRunState) -> None:
    validate_transition(src, dst)


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (TaskRunState.SCORED, TaskRunState.READY),
        (TaskRunState.FAILED_FINAL, TaskRunState.RUNNING),
        (TaskRunState.CREATED, TaskRunState.SCORED),
        (TaskRunState.CANCELLED, TaskRunState.SUBMITTING),
    ],
)
def test_illegal_transitions(src: TaskRunState, dst: TaskRunState) -> None:
    with pytest.raises(IllegalTransitionError):
        validate_transition(src, dst)
