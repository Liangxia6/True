"""Safe artifact path helpers. External IDs never enter paths unsanitized."""

from __future__ import annotations

from pathlib import Path

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.ids import safe_path_component


def run_dir(root: Path, run_id: str) -> Path:
    return root / "runs" / safe_path_component(run_id, max_len=80)


def execution_artifact_dir(root: Path, run_id: str, execution_id: str) -> Path:
    return run_dir(root, run_id) / "artifacts" / safe_path_component(execution_id)


def score_dir(root: Path, run_id: str, grading_job_id: str) -> Path:
    return run_dir(root, run_id) / "scores" / safe_path_component(grading_job_id)


def assert_inside(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise TrueEvalError(
            "path escapes storage root",
            category=FailureCategory.STORAGE_ERROR,
            code="path_escape",
            retryable=False,
            details={"root": str(resolved_root), "path": str(resolved)},
            cause=exc,
        ) from exc
    return resolved
