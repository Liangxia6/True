"""Deterministic format and completeness checks."""

from __future__ import annotations

from trueeval.core.ids import uuid7
from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.score import ScoreRecord


class FormatCompletenessGrader:
    def spec(self) -> GraderSpec:
        return GraderSpec(
            grader_id="format-completeness",
            version="0.1.0",
            kind="hard",
            metrics=["trueeval.format_completeness"],
        )

    def supports(self, artifact: ArtifactRef | ResearchAnswer, task: TaskSpec) -> bool:
        return isinstance(artifact, ResearchAnswer)

    async def grade(
        self,
        task: TaskSpec,
        artifacts: list[ResearchAnswer],
        ctx: GradeContext,
    ) -> list[ScoreRecord]:
        answer = artifacts[0]
        checks = {
            "has_final_answer": bool(answer.final_answer and answer.final_answer.strip()),
            "completed": answer.status == "completed",
            "citation_ok": (not task.expected_output.citation_required) or bool(answer.citations),
        }
        score = 1.0 if all(checks.values()) else 0.0
        coverage = 1.0 if answer.status == "completed" else 0.0
        return [
            ScoreRecord(
                score_id=uuid7(),
                run_id=ctx.run_id,
                execution_id=ctx.execution_id,
                task_id=task.task_id,
                repeat_index=answer.repeat_index,
                grading_job_id=ctx.grading_job_id,
                grader_id="format-completeness",
                grader_version="0.1.0",
                metric="trueeval.format_completeness",
                raw_value=score,
                normalized_value=score,
                coverage=coverage,
                rationale=str(checks),
                grader_config_hash=ctx.grader_config_hash,
                input_artifact_hash=ctx.input_artifact_hash,
                status="scored" if coverage else "excluded",
            )
        ]
