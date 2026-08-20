"""Official-style exact match against frozen gold. Used when upstream is deterministic."""

from __future__ import annotations

from trueeval.core.errors import ErrorInfo, FailureCategory
from trueeval.core.ids import uuid7
from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.score import ScoreRecord


def normalize_answer(text: str) -> str:
    return " ".join(text.strip().lower().split())


class ExactMatchGrader:
    def spec(self) -> GraderSpec:
        return GraderSpec(
            grader_id="exact-match",
            version="0.1.0",
            kind="official",
            metrics=["official.answer_accuracy"],
            requires_gold=True,
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
        if answer.status != "completed":
            return [
                ScoreRecord(
                    score_id=uuid7(),
                    run_id=ctx.run_id,
                    execution_id=ctx.execution_id,
                    task_id=task.task_id,
                    repeat_index=answer.repeat_index,
                    grading_job_id=ctx.grading_job_id,
                    grader_id="exact-match",
                    grader_version="0.1.0",
                    metric="official.answer_accuracy",
                    coverage=0.0,
                    rationale=f"excluded: answer status {answer.status}",
                    grader_config_hash=ctx.grader_config_hash,
                    input_artifact_hash=ctx.input_artifact_hash,
                    status="excluded",
                )
            ]
        if ctx.gold is None or not ctx.gold.reference_answer:
            return [
                ScoreRecord(
                    score_id=uuid7(),
                    run_id=ctx.run_id,
                    execution_id=ctx.execution_id,
                    task_id=task.task_id,
                    repeat_index=answer.repeat_index,
                    grading_job_id=ctx.grading_job_id,
                    grader_id="exact-match",
                    grader_version="0.1.0",
                    metric="official.answer_accuracy",
                    grader_config_hash=ctx.grader_config_hash,
                    input_artifact_hash=ctx.input_artifact_hash,
                    status="grader_error",
                    error=ErrorInfo(
                        category=FailureCategory.GRADER_ERROR,
                        code="missing_gold",
                        message="gold reference_answer is required",
                        retryable=False,
                    ),
                )
            ]
        prediction = normalize_answer(answer.final_answer or "")
        candidates = [ctx.gold.reference_answer, *ctx.gold.acceptable_answers]
        matched = any(prediction == normalize_answer(c) for c in candidates if c)
        value = 1.0 if matched else 0.0
        return [
            ScoreRecord(
                score_id=uuid7(),
                run_id=ctx.run_id,
                execution_id=ctx.execution_id,
                task_id=task.task_id,
                repeat_index=answer.repeat_index,
                grading_job_id=ctx.grading_job_id,
                grader_id="exact-match",
                grader_version="0.1.0",
                metric="official.answer_accuracy",
                raw_value=value,
                normalized_value=value,
                coverage=1.0,
                rationale="exact match against frozen gold",
                grader_config_hash=ctx.grader_config_hash,
                input_artifact_hash=ctx.input_artifact_hash,
                status="scored",
            )
        ]
