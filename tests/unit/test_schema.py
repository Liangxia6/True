from __future__ import annotations

import pytest
from pydantic import ValidationError

from trueeval.core.errors import SchemaVersionError
from trueeval.core.hashing import sha256_json
from trueeval.core.schemas.common import dump_canonical
from trueeval.core.schemas.config import RunConfig
from trueeval.core.schemas.score import ScoreRecord


def test_run_config_rejects_unknown_schema() -> None:
    with pytest.raises((ValidationError, SchemaVersionError)):
        RunConfig.model_validate(
            {
                "schema_version": "trueeval.run_config.v9.9",
                "benchmark": {"id": "x", "split": "y"},
                "sut": {"id": "z"},
            }
        )


def test_score_record_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ScoreRecord.model_validate(
            {
                "score_id": "s",
                "run_id": "r",
                "execution_id": "e",
                "task_id": "t",
                "repeat_index": 0,
                "grading_job_id": "g",
                "grader_id": "exact-match",
                "grader_version": "0.1.0",
                "metric": "official.answer_accuracy",
                "grader_config_hash": "sha256:0",
                "input_artifact_hash": "sha256:0",
                "mystery": True,
            }
        )


def test_canonical_dump_is_stable() -> None:
    cfg = RunConfig.model_validate(
        {"benchmark": {"id": "tiny-research", "split": "pilot"}, "sut": {"id": "fake-research"}}
    )
    a = sha256_json(dump_canonical(cfg))
    b = sha256_json(dump_canonical(cfg))
    assert a == b
    assert a.startswith("sha256:")
