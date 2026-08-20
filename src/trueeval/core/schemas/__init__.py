"""Pydantic schemas for TrueEval Research MVP."""

from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import BenchmarkSpec, GoldRecord, TaskSpec
from trueeval.core.schemas.config import RunConfig
from trueeval.core.schemas.events import EventRecord
from trueeval.core.schemas.gate import GateDecision, GateRecord
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.manual import ManualImportPackage, ManualImportSpec, ValidationResult
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
from trueeval.core.schemas.task import TaskRun

__all__ = [
    "ArtifactRef",
    "BenchmarkSpec",
    "CapabilitySet",
    "EventRecord",
    "GateDecision",
    "GateRecord",
    "GoldRecord",
    "GradeContext",
    "GraderSpec",
    "InputPackage",
    "JobStatus",
    "ManualImportPackage",
    "ManualImportSpec",
    "RawSUTResult",
    "ResearchAnswer",
    "RunConfig",
    "RunManifest",
    "RunSummary",
    "ScoreRecord",
    "SessionHandle",
    "Submission",
    "SUTSpec",
    "TaskRun",
    "TaskSpec",
    "ValidationResult",
]
