"""Wrap the official Cited-but-Not-Verified pipeline. Do not fuse the three scores."""

from __future__ import annotations

from trueeval.cited_not_verified.pipeline import evaluate_report
from trueeval.core.errors import ErrorInfo, FailureCategory
from trueeval.core.ids import uuid7
from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.score import ScoreRecord


class CitedNotVerifiedGrader:
    def __init__(self, *, fetch: bool = False, judge: object | None = None) -> None:
        self.fetch = fetch
        self.judge = judge

    def spec(self) -> GraderSpec:
        return GraderSpec(
            grader_id="cited-not-verified",
            version="0.1.0",
            kind="citation",
            metrics=["official.link_works", "official.relevant_content", "official.fact_check"],
            requires_network=self.fetch,
            prompt_id="FACTUAL_SUPPORT+SOURCE_RELEVANCE",
            config={"fuse_scores": False, "fetch": self.fetch},
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
        markdown = answer.final_answer or ""
        if not markdown.strip():
            return self._not_observable(task, answer, ctx, "empty final_answer")
        try:
            doc = evaluate_report(
                markdown,
                query=task.input.prompt,
                judge=self.judge,  # type: ignore[arg-type]
                fetch=self.fetch,
                score_llm_dims=self.judge is not None,
            )
        except Exception as exc:
            return [
                self._error(task, answer, ctx, "official.fact_check", str(exc)),
                self._error(task, answer, ctx, "official.link_works", str(exc)),
                self._error(task, answer, ctx, "official.relevant_content", str(exc)),
            ]
        agg = doc.aggregate()
        records = []
        for metric, key in (
            ("official.link_works", "link_works"),
            ("official.relevant_content", "relevant_content"),
            ("official.fact_check", "fact_check"),
        ):
            value = agg.get(key)
            if value is None:
                records.append(self._not_observable(task, answer, ctx, f"{key} not observable", metric=metric)[0])
                continue
            records.append(
                ScoreRecord(
                    score_id=uuid7(),
                    run_id=ctx.run_id,
                    execution_id=ctx.execution_id,
                    task_id=task.task_id,
                    repeat_index=answer.repeat_index,
                    grading_job_id=ctx.grading_job_id,
                    grader_id="cited-not-verified",
                    grader_version="0.1.0",
                    metric=metric,
                    raw_value=float(value),
                    normalized_value=float(value),
                    coverage=1.0 if agg.get("n_pairs") else 0.0,
                    rationale=f"n_pairs={agg.get('n_pairs')} fuse_scores=false",
                    grader_config_hash=ctx.grader_config_hash,
                    input_artifact_hash=ctx.input_artifact_hash,
                    status="scored" if agg.get("n_pairs") else "not_observable",
                )
            )
        return records

    def _not_observable(
        self,
        task: TaskSpec,
        answer: ResearchAnswer,
        ctx: GradeContext,
        why: str,
        metric: str = "official.fact_check",
    ) -> list[ScoreRecord]:
        return [
            ScoreRecord(
                score_id=uuid7(),
                run_id=ctx.run_id,
                execution_id=ctx.execution_id,
                task_id=task.task_id,
                repeat_index=answer.repeat_index,
                grading_job_id=ctx.grading_job_id,
                grader_id="cited-not-verified",
                grader_version="0.1.0",
                metric=metric,
                coverage=0.0,
                rationale=why,
                grader_config_hash=ctx.grader_config_hash,
                input_artifact_hash=ctx.input_artifact_hash,
                status="not_observable",
            )
        ]

    def _error(self, task: TaskSpec, answer: ResearchAnswer, ctx: GradeContext, metric: str, message: str) -> ScoreRecord:
        return ScoreRecord(
            score_id=uuid7(),
            run_id=ctx.run_id,
            execution_id=ctx.execution_id,
            task_id=task.task_id,
            repeat_index=answer.repeat_index,
            grading_job_id=ctx.grading_job_id,
            grader_id="cited-not-verified",
            grader_version="0.1.0",
            metric=metric,
            grader_config_hash=ctx.grader_config_hash,
            input_artifact_hash=ctx.input_artifact_hash,
            status="grader_error",
            error=ErrorInfo(
                category=FailureCategory.GRADER_ERROR,
                code="pipeline_error",
                message=message,
                retryable=False,
            ),
        )
