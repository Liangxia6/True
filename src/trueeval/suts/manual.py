"""Manual research import. Missing evidence is recorded, never invented."""

from __future__ import annotations

from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.manual import (
    ManualImportPackage,
    ManualImportSpec,
    ValidationIssue,
    ValidationResult,
)
from trueeval.core.schemas.sut import RawSUTResult


class ManualResearchImport:
    def spec(self) -> ManualImportSpec:
        return ManualImportSpec()

    def validate_package(self, package: ManualImportPackage, task: TaskSpec) -> ValidationResult:
        issues: list[ValidationIssue] = []
        if package.task_id != task.task_id:
            issues.append(
                ValidationIssue(
                    field="task_id",
                    code="task_mismatch",
                    message=f"package task {package.task_id} != {task.task_id}",
                )
            )
        if not package.operator:
            issues.append(ValidationIssue(field="operator", code="missing", message="operator is required"))
        if not package.sop_version:
            issues.append(ValidationIssue(field="sop_version", code="missing", message="sop_version is required"))
        if not package.report and not package.final_answer:
            issues.append(
                ValidationIssue(
                    field="report",
                    code="missing",
                    message="report or final_answer is required",
                )
            )
        if not package.evidence:
            issues.append(
                ValidationIssue(
                    field="evidence",
                    code="missing_evidence",
                    message="evidence list is empty",
                    blocking=False,
                )
            )
        blocking = [i for i in issues if i.blocking]
        return ValidationResult(ok=not blocking, issues=issues)

    def collect(self, package: ManualImportPackage, task: TaskSpec) -> RawSUTResult:
        return RawSUTResult(
            execution_id=package.execution_id or task.task_id,
            channel="MANUAL_IMPORT",
            final_answer=package.final_answer or package.report,
            raw_response={
                "operator": package.operator,
                "sop_version": package.sop_version,
                "executed_at": package.executed_at.isoformat(),
                "notes": package.notes,
            },
            search_results=package.search_results or None,
            citations=package.citations or None,
            usage={},
            status="completed",
        )
