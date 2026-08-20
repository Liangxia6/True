"""Route graders independently. One grader failure must not destroy artifacts or other scores."""

from __future__ import annotations

from collections.abc import Mapping

from trueeval.core.errors import ErrorInfo, FailureCategory, TrueEvalError, from_exception
from trueeval.core.hashing import sha256_json
from trueeval.core.ids import grading_job_id, uuid7
from trueeval.core.logging import get_logger
from trueeval.core.schemas.artifact import ResearchAnswer
from trueeval.core.schemas.benchmark import GoldRecord, TaskSpec
from trueeval.core.schemas.common import dump_canonical
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.score import GradingJob, ScoreRecord
from trueeval.core.timeutil import utc_now
from trueeval.storage.artifacts import ArtifactStore
from trueeval.storage.state import StateStore

log = get_logger("grader_router")

KIND_ORDER = {"hard": 0, "official": 1, "llm_judge": 2, "citation": 3, "diagnostic": 4}


class GraderRouter:
    def __init__(
        self,
        graders: Mapping[str, object],
        *,
        state: StateStore,
        artifacts: ArtifactStore,
        judge: object | None = None,
    ) -> None:
        self.graders = dict(graders)
        self.state = state
        self.artifacts = artifacts
        self.judge = judge
        if self.judge is None:
            for adapter in self.graders.values():
                found = getattr(adapter, "judge", None)
                if found is not None:
                    self.judge = found
                    break

    def ordered_specs(self, specs: list[GraderSpec]) -> list[GraderSpec]:
        return sorted(specs, key=lambda s: (KIND_ORDER.get(s.kind, 9), s.grader_id))

    async def grade_execution(
        self,
        *,
        run_id: str,
        execution_id: str,
        task: TaskSpec,
        answer: ResearchAnswer,
        gold: GoldRecord | None,
        specs: list[GraderSpec],
        select: bool = True,
    ) -> list[ScoreRecord]:
        all_scores: list[ScoreRecord] = []
        for spec in self.ordered_specs(specs):
            adapter = self.graders.get(spec.grader_id)
            if adapter is None:
                all_scores.append(
                    self._error_score(
                        run_id,
                        execution_id,
                        task,
                        spec,
                        "missing_grader",
                        f"grader {spec.grader_id} is not registered",
                    )
                )
                continue
            job_id = grading_job_id()
            config_hash = sha256_json(dump_canonical(spec))
            input_hash = sha256_json(dump_canonical(answer))
            job = GradingJob(
                grading_job_id=job_id,
                run_id=run_id,
                execution_id=execution_id,
                grader_id=spec.grader_id,
                grader_version=spec.version,
                status="running",
                config_hash=config_hash,
                selected=select,
            )
            self.state.add_grading_job(job)
            ctx = GradeContext(
                run_id=run_id,
                execution_id=execution_id,
                grading_job_id=job_id,
                task=task,
                gold=gold,
                grader_config_hash=config_hash,
                input_artifact_hash=input_hash,
                judge_enabled=bool(spec.judge_model or self.judge),
                extra={"judge": self.judge} if self.judge is not None else {},
            )
            try:
                if not adapter.supports(answer, task):  # type: ignore[attr-defined]
                    scores = [
                        ScoreRecord(
                            score_id=uuid7(),
                            run_id=run_id,
                            execution_id=execution_id,
                            task_id=task.task_id,
                            repeat_index=answer.repeat_index,
                            grading_job_id=job_id,
                            grader_id=spec.grader_id,
                            grader_version=spec.version,
                            metric=spec.metrics[0] if spec.metrics else spec.grader_id,
                            coverage=0.0,
                            grader_config_hash=config_hash,
                            input_artifact_hash=input_hash,
                            status="not_observable",
                            rationale="grader does not support this artifact",
                        )
                    ]
                else:
                    scores = await adapter.grade(task, [answer], ctx)  # type: ignore[attr-defined]
                for score in scores:
                    if score.grading_job_id != job_id:
                        score.grading_job_id = job_id
                self._persist_scores(run_id, job_id, scores)
                self.state.add_scores(scores)
                self.state.set_grading_job_status(job_id, "succeeded", selected=select)
                all_scores.extend(scores)
            except Exception as exc:
                error = from_exception(exc, default_code="grader_error")
                if error.category != FailureCategory.GRADER_ERROR:
                    error = TrueEvalError(
                        error.info.message,
                        category=FailureCategory.GRADER_ERROR,
                        code=error.info.code,
                        retryable=error.retryable,
                        cause=exc,
                    )
                log.error(
                    "grader failed",
                    extra={
                        "run_id": run_id,
                        "execution_id": execution_id,
                        "event": "grader_error",
                        "error_category": error.category.value,
                    },
                )
                failed = [
                    self._error_score(
                        run_id,
                        execution_id,
                        task,
                        spec,
                        error.info.code,
                        error.info.message,
                        job_id=job_id,
                        config_hash=config_hash,
                        input_hash=input_hash,
                        repeat_index=answer.repeat_index,
                        error=error.to_info(),
                    )
                ]
                self._persist_scores(run_id, job_id, failed)
                self.state.add_scores(failed)
                self.state.set_grading_job_status(job_id, "failed", selected=select)
                all_scores.extend(failed)
        return all_scores

    def _persist_scores(self, run_id: str, job_id: str, scores: list[ScoreRecord]) -> None:
        directory = self.artifacts.scores_dir(run_id, job_id)
        rel_manifest = f"runs/{run_id}/scores/{job_id}/manifest.json"
        rel_scores = f"runs/{run_id}/scores/{job_id}/scores.jsonl"
        self.artifacts.write_json(
            rel_manifest,
            {
                "schema_version": "trueeval.grading_job_manifest.v0.1",
                "grading_job_id": job_id,
                "run_id": run_id,
                "created_at": utc_now().isoformat().replace("+00:00", "Z"),
                "n_scores": len(scores),
            },
            kind="grader_output",
        )
        self.artifacts.write_jsonl(
            rel_scores,
            [dump_canonical(s) for s in scores],
        )
        _ = directory

    def _error_score(
        self,
        run_id: str,
        execution_id: str,
        task: TaskSpec,
        spec: GraderSpec,
        code: str,
        message: str,
        *,
        job_id: str | None = None,
        config_hash: str = "sha256:0",
        input_hash: str = "sha256:0",
        repeat_index: int = 0,
        error: ErrorInfo | None = None,
    ) -> ScoreRecord:
        return ScoreRecord(
            score_id=uuid7(),
            run_id=run_id,
            execution_id=execution_id,
            task_id=task.task_id,
            repeat_index=repeat_index,
            grading_job_id=job_id or grading_job_id(),
            grader_id=spec.grader_id,
            grader_version=spec.version,
            metric=spec.metrics[0] if spec.metrics else spec.grader_id,
            grader_config_hash=config_hash,
            input_artifact_hash=input_hash,
            status="grader_error",
            error=error
            or ErrorInfo(
                category=FailureCategory.GRADER_ERROR,
                code=code,
                message=message,
                retryable=False,
            ),
        )
