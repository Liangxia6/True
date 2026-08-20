from __future__ import annotations

import pytest
from pydantic import ValidationError

from trueeval.core.schemas.artifact import ResearchAnswer, SUTIdentity
from trueeval.core.schemas.config import RunConfig


def test_research_answer_current_version() -> None:
    answer = ResearchAnswer(
        run_id="r",
        execution_id="e",
        task_id="t",
        status="completed",
        sut=SUTIdentity(
            provider="fake",
            product="fake",
            model="m",
            endpoint_family="in_process",
            channel="API_SYNC",
        ),
        channel="API_SYNC",
    )
    assert answer.schema_version == "trueeval.research_answer.v0.1"


def test_unrecognized_run_config_version_fails() -> None:
    with pytest.raises((ValidationError, Exception)):
        RunConfig.model_validate(
            {
                "schema_version": "not-a-version",
                "benchmark": {"id": "a", "split": "b"},
                "sut": {"id": "c"},
            }
        )
