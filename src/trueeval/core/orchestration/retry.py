"""Retry classification and jittered exponential backoff."""

from __future__ import annotations

import random
from dataclasses import dataclass

from trueeval.core.errors import FailureCategory, TrueEvalError

RETRYABLE_CATEGORIES = {
    FailureCategory.NETWORK_ERROR,
    FailureCategory.RATE_LIMITED,
    FailureCategory.TIMEOUT,
    FailureCategory.PROVIDER_ERROR,
}

NON_RETRYABLE_CODES = {
    "auth_failed",
    "invalid_argument",
    "unsupported",
    "policy_refusal",
    "lost_job_id",
    "regeneration",
}


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_seconds: float = 1.0
    max_seconds: float = 60.0
    jitter: float = 0.2


def is_retryable(error: TrueEvalError) -> bool:
    if error.info.code in NON_RETRYABLE_CODES:
        return False
    if error.category in {
        FailureCategory.AUTH_ERROR,
        FailureCategory.INVALID_ARGUMENT,
        FailureCategory.UNSUPPORTED,
        FailureCategory.POLICY_REFUSAL,
        FailureCategory.UNKNOWN_SUBMISSION,
        FailureCategory.BUDGET_EXCEEDED,
        FailureCategory.GATE_DENIED,
        FailureCategory.CANCELLED,
    }:
        return False
    return error.retryable or error.category in RETRYABLE_CATEGORIES


def backoff_seconds(attempt: int, policy: RetryPolicy, rng: random.Random | None = None) -> float:
    rng = rng or random.Random()
    expo = min(policy.max_seconds, policy.base_seconds * (2 ** max(0, attempt - 1)))
    delta = expo * policy.jitter
    return max(0.0, expo + rng.uniform(-delta, delta))
