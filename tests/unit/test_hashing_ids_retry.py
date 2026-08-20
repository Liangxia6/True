from __future__ import annotations

from pathlib import Path

import pytest

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.hashing import sha256_text
from trueeval.core.ids import idempotency_key, safe_path_component, uuid7
from trueeval.core.orchestration.retry import RetryPolicy, backoff_seconds, is_retryable
from trueeval.core.paths import assert_inside


def test_uuid7_format() -> None:
    value = uuid7(clock_ms=1_700_000_000_000, random_bytes=b"\x01" * 10)
    assert value.count("-") == 4
    assert value[14] == "7"


def test_idempotency_key_stable() -> None:
    a = idempotency_key(
        run_id="r", execution_id="e", task_id="t", repeat_index=0, attempt=1, sut_id="fake"
    )
    b = idempotency_key(
        run_id="r", execution_id="e", task_id="t", repeat_index=0, attempt=1, sut_id="fake"
    )
    c = idempotency_key(
        run_id="r", execution_id="e", task_id="t", repeat_index=1, attempt=1, sut_id="fake"
    )
    assert a == b
    assert a != c
    assert a.startswith("te-")


def test_path_sanitization_and_escape(tmp_path: Path) -> None:
    assert "/" not in safe_path_component("job/../../etc")
    with pytest.raises(TrueEvalError):
        assert_inside(tmp_path, tmp_path.parent / "outside")


def test_retry_classification() -> None:
    retryable = TrueEvalError("x", category=FailureCategory.RATE_LIMITED, code="http_429", retryable=True)
    fatal = TrueEvalError("x", category=FailureCategory.AUTH_ERROR, code="auth_failed", retryable=False)
    unknown = TrueEvalError("x", category=FailureCategory.UNKNOWN_SUBMISSION, code="unknown_submission", retryable=False)
    assert is_retryable(retryable)
    assert not is_retryable(fatal)
    assert not is_retryable(unknown)
    delay = backoff_seconds(2, RetryPolicy(jitter=0), None)
    assert delay == 2.0


def test_sha256_text() -> None:
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")
