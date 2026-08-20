"""Manual research import package schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from trueeval.core.schemas.common import VersionedModel
from trueeval.core.timeutil import utc_now


class ManualImportSpec(VersionedModel):
    schema_version: str = "trueeval.manual_import_spec.v0.1"
    adapter_id: str = "manual-research-import"
    version: str = "0.1.0"
    requires: list[str] = Field(
        default_factory=lambda: ["operator", "executed_at", "sop_version", "report", "evidence"]
    )


class EvidenceItem(VersionedModel):
    schema_version: str = "trueeval.manual_evidence.v0.1"
    path: str
    kind: str
    sha256: str | None = None
    notes: str | None = None


class ManualImportPackage(VersionedModel):
    schema_version: str = "trueeval.manual_import_package.v0.1"
    task_id: str
    execution_id: str | None = None
    operator: str
    executed_at: datetime
    sop_version: str
    report: str
    final_answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    search_results: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    notes: str | None = None
    imported_at: datetime = Field(default_factory=utc_now)


class ValidationIssue(VersionedModel):
    schema_version: str = "trueeval.validation_issue.v0.1"
    field: str
    code: str
    message: str
    blocking: bool = True


class ValidationResult(VersionedModel):
    schema_version: str = "trueeval.validation_result.v0.1"
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
