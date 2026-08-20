"""Resolve a BenchmarkAdapter from an on-disk catalog."""

from __future__ import annotations

from pathlib import Path

from trueeval.benchmarks.file_adapter import FileBenchmarkAdapter
from trueeval.core.errors import FailureCategory, TrueEvalError


def default_catalog(workspace: Path) -> Path:
    return workspace / "benchmarks"


def load_benchmark(benchmark_id: str, *, workspace: Path) -> FileBenchmarkAdapter:
    root = default_catalog(workspace) / benchmark_id
    if not root.exists():
        raise TrueEvalError(
            f"benchmark {benchmark_id} not found at {root}",
            category=FailureCategory.INVALID_ARGUMENT,
            code="unknown_benchmark",
            retryable=False,
        )
    return FileBenchmarkAdapter(root)
