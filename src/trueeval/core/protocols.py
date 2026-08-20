"""Stable Adapter protocols. Orchestrator depends only on these interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import BenchmarkSpec, GoldRecord, TaskSpec
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.manual import (
    ManualImportPackage,
    ManualImportSpec,
    ValidationResult,
)
from trueeval.core.schemas.run import RunManifest, RunSummary
from trueeval.core.schemas.score import ScoreRecord
from trueeval.core.schemas.sut import (
    CapabilitySet,
    InputPackage,
    JobStatus,
    RawSUTResult,
    SessionHandle,
    Submission,
    SUTSpec,
)


class RunContext:
    """Typed context passed between stages. Adapters must not mutate orchestrator state."""

    def __init__(
        self,
        *,
        manifest: RunManifest,
        extra: dict[str, object] | None = None,
    ) -> None:
        self.manifest = manifest
        self.extra = extra or {}


@runtime_checkable
class BenchmarkAdapter(Protocol):
    """Loads tasks, builds deterministic inputs, and normalizes SUT output."""

    def spec(self) -> BenchmarkSpec: ...

    def load_tasks(self, split: str) -> list[TaskSpec]: ...

    def load_gold(self, task_id: str) -> GoldRecord | None: ...

    def build_input(self, task: TaskSpec, ctx: RunContext) -> InputPackage: ...

    def normalize(
        self,
        raw: RawSUTResult,
        task: TaskSpec,
        ctx: RunContext,
    ) -> ResearchAnswer: ...

    def required_graders(self) -> list[GraderSpec]: ...

    def required_capabilities(self) -> list[str]: ...

    def aggregate(self, scores: list[ScoreRecord]) -> RunSummary: ...


@runtime_checkable
class SUTAdapter(Protocol):
    """Talks to a research product. Does not grade and does not swallow provider errors."""

    def spec(self) -> SUTSpec: ...

    async def capabilities(self) -> CapabilitySet: ...

    async def start_session(self, task: TaskSpec, ctx: RunContext) -> SessionHandle: ...

    async def submit(
        self,
        session: SessionHandle,
        input: InputPackage,
        idempotency_key: str,
    ) -> Submission: ...

    async def lookup(self, idempotency_key: str) -> Submission | None: ...

    async def poll(self, submission: Submission) -> JobStatus: ...

    async def collect(
        self,
        session: SessionHandle,
        submission: Submission,
    ) -> RawSUTResult: ...

    async def close(self, session: SessionHandle) -> None: ...


@runtime_checkable
class ManualResearchImportAdapter(Protocol):
    """Validates and collects a frozen SOP import package. No submit/poll."""

    def spec(self) -> ManualImportSpec: ...

    def validate_package(
        self,
        package: ManualImportPackage,
        task: TaskSpec,
    ) -> ValidationResult: ...

    def collect(
        self,
        package: ManualImportPackage,
        task: TaskSpec,
    ) -> RawSUTResult: ...


@runtime_checkable
class GraderAdapter(Protocol):
    """Reads frozen Task + Artifact only. Must not mutate inputs or invent a 0 on failure."""

    def spec(self) -> GraderSpec: ...

    def supports(self, artifact: ArtifactRef | ResearchAnswer, task: TaskSpec) -> bool: ...

    async def grade(
        self,
        task: TaskSpec,
        artifacts: list[ResearchAnswer],
        ctx: GradeContext,
    ) -> list[ScoreRecord]: ...
