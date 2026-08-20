"""Unified TrueEval error types and failure categories."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FailureCategory(StrEnum):
    """System-failure categories that must not be counted as wrong answers."""

    UNSUPPORTED = "UNSUPPORTED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    POLICY_REFUSAL = "POLICY_REFUSAL"
    ADAPTER_ERROR = "ADAPTER_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    GRADER_ERROR = "GRADER_ERROR"
    IMPORT_INCOMPLETE = "IMPORT_INCOMPLETE"
    AUTH_ERROR = "AUTH_ERROR"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    GATE_DENIED = "GATE_DENIED"
    CANCELLED = "CANCELLED"
    UNKNOWN_SUBMISSION = "UNKNOWN_SUBMISSION"
    NETWORK_ERROR = "NETWORK_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    STATE_ERROR = "STATE_ERROR"


class ErrorInfo(BaseModel):
    """Structured error recorded on TaskRun, Artifact, and ScoreRecord."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "trueeval.error.v0.1"
    category: FailureCategory
    code: str
    message: str
    retryable: bool
    provider_status: str | None = None
    details_uri: str | None = None
    cause_type: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TrueEvalError(Exception):
    """Base exception. Network, file, and DB errors convert to this type."""

    def __init__(
        self,
        message: str,
        *,
        category: FailureCategory,
        code: str,
        retryable: bool,
        provider_status: str | None = None,
        details_uri: str | None = None,
        cause_type: str | None = None,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.info = ErrorInfo(
            category=category,
            code=code,
            message=message,
            retryable=retryable,
            provider_status=provider_status,
            details_uri=details_uri,
            cause_type=cause_type or (type(cause).__name__ if cause else None),
            details=details or {},
        )
        self.__cause__ = cause

    @property
    def category(self) -> FailureCategory:
        return self.info.category

    @property
    def retryable(self) -> bool:
        return self.info.retryable

    def to_info(self) -> ErrorInfo:
        return self.info


class IllegalTransitionError(TrueEvalError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"illegal state transition: {current} -> {target}",
            category=FailureCategory.STATE_ERROR,
            code="illegal_transition",
            retryable=False,
            details={"current": current, "target": target},
        )


class SchemaVersionError(TrueEvalError):
    def __init__(self, found: str, supported: list[str]) -> None:
        super().__init__(
            f"unrecognized schema_version {found!r}",
            category=FailureCategory.PARSE_ERROR,
            code="unsupported_schema_version",
            retryable=False,
            details={"found": found, "supported": supported},
        )


class SecretLeakError(TrueEvalError):
    def __init__(self, location: str) -> None:
        super().__init__(
            "secret must not enter artifact, event, manifest, or log",
            category=FailureCategory.ADAPTER_ERROR,
            code="secret_leak",
            retryable=False,
            details={"location": location},
        )


def classify_http_status(status: int) -> tuple[FailureCategory, bool]:
    """Map HTTP status to failure category and retryability."""
    if status == 408 or status == 429:
        return FailureCategory.RATE_LIMITED if status == 429 else FailureCategory.TIMEOUT, True
    if status == 401 or status == 403:
        return FailureCategory.AUTH_ERROR, False
    if 400 <= status < 500:
        return FailureCategory.INVALID_ARGUMENT, False
    if status >= 500:
        return FailureCategory.PROVIDER_ERROR, True
    return FailureCategory.PROVIDER_ERROR, False


def from_exception(exc: BaseException, *, default_code: str = "internal") -> TrueEvalError:
    if isinstance(exc, TrueEvalError):
        return exc
    return TrueEvalError(
        str(exc) or type(exc).__name__,
        category=FailureCategory.ADAPTER_ERROR,
        code=default_code,
        retryable=False,
        cause=exc,
        cause_type=type(exc).__name__,
    )
