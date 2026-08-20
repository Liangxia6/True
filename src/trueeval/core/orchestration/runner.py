"""Per-execution runner. Network I/O is never done inside a database transaction."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from trueeval.core.errors import ErrorInfo, FailureCategory, TrueEvalError, from_exception
from trueeval.core.hashing import sha256_json
from trueeval.core.ids import idempotency_key, uuid7
from trueeval.core.logging import get_logger
from trueeval.core.orchestration.grader_router import GraderRouter
from trueeval.core.orchestration.rate_limit import CapacityPool
from trueeval.core.orchestration.retry import RetryPolicy, backoff_seconds, is_retryable
from trueeval.core.protocols import BenchmarkAdapter, RunContext, SUTAdapter
from trueeval.core.schemas.artifact import ArtifactPointers, ResearchAnswer
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.common import dump_canonical
from trueeval.core.schemas.grader import GraderSpec
from trueeval.core.schemas.run import RunManifest
from trueeval.core.schemas.sut import (
    InputPackage,
    JobStatus,
    RawSUTResult,
    SessionHandle,
    Submission,
)
from trueeval.core.schemas.task import TaskRun
from trueeval.core.state_machine.states import TERMINAL_STATES, TaskRunState
from trueeval.core.timeutil import Clock, SystemClock, to_iso
from trueeval.storage.artifacts import ArtifactStore
from trueeval.storage.events import EventProjector
from trueeval.storage.state import StateStore

log = get_logger("runner")


class ExecutionRunner:
    def __init__(
        self,
        *,
        manifest: RunManifest,
        state: StateStore,
        artifacts: ArtifactStore,
        projector: EventProjector,
        benchmark: BenchmarkAdapter,
        sut: SUTAdapter,
        graders: GraderRouter,
        grader_specs: list[GraderSpec],
        pool: CapacityPool,
        clock: Clock | None = None,
        retry: RetryPolicy | None = None,
        tasks: dict[str, TaskSpec],
    ) -> None:
        self.manifest = manifest
        self.state = state
        self.artifacts = artifacts
        self.projector = projector
        self.benchmark = benchmark
        self.sut = sut
        self.graders = graders
        self.grader_specs = grader_specs
        self.pool = pool
        self.clock = clock or SystemClock()
        self.retry = retry or RetryPolicy(max_attempts=manifest.execution.max_attempts)
        self.tasks = tasks
        self.ctx = RunContext(manifest=manifest)

    async def run(self, execution_id: str) -> TaskRun:
        task_run = self._require(execution_id)
        if task_run.status in TERMINAL_STATES:
            return task_run
        try:
            task_run = await self._advance(task_run)
        except TrueEvalError as exc:
            task_run = self._fail(task_run, exc)
        except Exception as exc:
            task_run = self._fail(task_run, from_exception(exc))
        self.projector.project(self.manifest.run_id)
        return self._require(execution_id)

    async def _advance(self, task_run: TaskRun) -> TaskRun:
        spec = self.tasks[task_run.task_id]
        for _ in range(12):
            task_run = self._require(task_run.execution_id)
            if task_run.status in TERMINAL_STATES:
                return task_run
            if task_run.status == TaskRunState.CREATED:
                task_run = await self._materialize(task_run, spec)
                continue
            if task_run.status == TaskRunState.MATERIALIZED:
                if self.manifest.sut.channel == "MANUAL_IMPORT":
                    return self.state.transition(
                        task_run.execution_id,
                        TaskRunState.WAITING_IMPORT,
                        event_type="task.waiting_import",
                    )
                task_run = self.state.transition(
                    task_run.execution_id,
                    TaskRunState.READY,
                    event_type="task.ready",
                )
                continue
            if task_run.status == TaskRunState.WAITING_IMPORT:
                return task_run
            if task_run.status == TaskRunState.FAILED_RETRYABLE:
                task_run = await self._retry_or_finalize(task_run)
                continue
            if task_run.status == TaskRunState.READY:
                task_run = await self._submit_flow(task_run, spec)
                continue
            if task_run.status in {
                TaskRunState.SUBMITTING,
                TaskRunState.SUBMITTED,
                TaskRunState.RUNNING,
                TaskRunState.WAITING_EXTERNAL,
            }:
                if task_run.status == TaskRunState.SUBMITTING and not task_run.external_job_id:
                    if task_run.last_error and task_run.last_error.category == FailureCategory.UNKNOWN_SUBMISSION:
                        return task_run
                    task_run = await self._submit_flow(task_run, spec)
                    continue
                task_run = await self._poll_until_done(task_run)
                continue
            if task_run.status in {TaskRunState.COMPLETED, TaskRunState.COMPLETED_SYNC}:
                task_run = await self._collect_normalize_grade(task_run, spec)
                continue
            if task_run.status == TaskRunState.COLLECTED:
                task_run = await self._normalize_and_grade(task_run, spec)
                continue
            if task_run.status in {TaskRunState.NORMALIZED, TaskRunState.GRADING}:
                task_run = await self._grade(task_run, spec)
                continue
            return task_run
        return self._require(task_run.execution_id)

    async def _materialize(self, task_run: TaskRun, spec: TaskSpec) -> TaskRun:
        package = self.benchmark.build_input(spec, self.ctx)
        rel = (
            f"runs/{self.manifest.run_id}/artifacts/{task_run.execution_id}/input.json"
        )
        ref = self.artifacts.write_json(rel, dump_canonical(package), kind="input")
        deadline = self.clock.now() + timedelta(seconds=self.manifest.execution.task_timeout_seconds)
        return self.state.transition(
            task_run.execution_id,
            TaskRunState.MATERIALIZED,
            event_type="task.materialized",
            updates={
                "input_uri": ref.uri,
                "deadline": to_iso(deadline),
            },
            payload={"input_hash": package.input_hash},
        )

    async def _submit_flow(self, task_run: TaskRun, spec: TaskSpec) -> TaskRun:
        if task_run.external_job_id:
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.WAITING_EXTERNAL,
                event_type="task.resume_existing_job",
                payload={"external_job_id": task_run.external_job_id},
            )
        reservation_id = None
        try:
            reservation_id = self.state.reserve_budget(
                self.manifest.run_id,
                task_run.execution_id,
                self.manifest.execution.estimated_cost_usd_per_task,
                self.manifest.budget.max_cost_usd,
            )
        except TrueEvalError as exc:
            if exc.category == FailureCategory.BUDGET_EXCEEDED:
                return self.state.transition(
                    task_run.execution_id,
                    TaskRunState.FAILED_FINAL,
                    event_type="task.budget_blocked",
                    error=exc.to_info(),
                )
            raise
        task_run.extra["reservation_id"] = reservation_id
        self.state.patch_task(task_run.execution_id, extra_json=__import__("json").dumps(task_run.extra))

        self.ctx.extra["execution_id"] = task_run.execution_id
        self.ctx.extra["repeat_index"] = task_run.repeat_index
        session = await self.sut.start_session(spec, self.ctx)
        attempt = task_run.attempt_count + 1
        self.state.add_attempt(task_run.execution_id, attempt)
        key = task_run.idempotency_key or idempotency_key(
            run_id=self.manifest.run_id,
            execution_id=task_run.execution_id,
            task_id=task_run.task_id,
            repeat_index=task_run.repeat_index,
            attempt=attempt,
            sut_id=self.manifest.sut.sut_id,
        )
        self.state.patch_task(
            task_run.execution_id,
            session_id=session.session_id,
            attempt_count=attempt,
            idempotency_key=key,
        )
        task_run = self.state.transition(
            task_run.execution_id,
            TaskRunState.SUBMITTING,
            event_type="task.submitting",
            payload={"idempotency_key": key, "attempt": attempt},
            updates={"idempotency_key": key, "session_id": session.session_id, "attempt_count": attempt},
        )
        package = InputPackage.model_validate(self.artifacts.read_json(task_run.input_uri or ""))
        try:
            async with self.pool.submit, self.pool.provider_submit(self.manifest.sut.provider):
                await self.pool.bucket(self.manifest.sut.provider).acquire()
                submission = await self.sut.submit(session, package, key)
        except TrueEvalError as exc:
            return await self._handle_submit_failure(task_run, exc, key)
        except Exception as exc:
            return await self._handle_submit_failure(task_run, from_exception(exc), key)

        self._write_submission_artifacts(task_run, package, submission)
        self.state.add_submission(submission)
        updates: dict[str, Any] = {
            "submitted_at": to_iso(self.clock.now()),
            "external_job_id": submission.external_job_id,
            "idempotency_key": submission.idempotency_key,
        }
        if self.manifest.sut.channel == "API_SYNC" or submission.external_job_id is None and self.sut.spec().channel == "API_SYNC":
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.COMPLETED_SYNC,
                event_type="task.completed_sync",
                updates=updates,
            )
        return self.state.transition(
            task_run.execution_id,
            TaskRunState.SUBMITTED if submission.external_job_id else TaskRunState.WAITING_EXTERNAL,
            event_type="task.submitted",
            updates=updates,
            payload={"external_job_id": submission.external_job_id},
        )

    async def _handle_submit_failure(self, task_run: TaskRun, error: TrueEvalError, key: str) -> TaskRun:
        caps = await self.sut.capabilities()
        if caps.submission_lookup:
            found = await self.sut.lookup(key)
            if found and found.external_job_id:
                self.state.add_submission(found)
                return self.state.transition(
                    task_run.execution_id,
                    TaskRunState.WAITING_EXTERNAL,
                    event_type="task.submit_recovered_via_lookup",
                    updates={"external_job_id": found.external_job_id, "idempotency_key": key},
                )
        if (
            not caps.provider_idempotency
            and not caps.submission_lookup
            and error.category
            in {
                FailureCategory.NETWORK_ERROR,
                FailureCategory.TIMEOUT,
                FailureCategory.UNKNOWN_SUBMISSION,
            }
        ):
            error = TrueEvalError(
                "submit result unknown; provider cannot look up or honor idempotency — "
                f"manual disposition required ({error.info.category}: {error.info.message})",
                category=FailureCategory.UNKNOWN_SUBMISSION,
                code="unknown_submission",
                retryable=False,
                cause=error,
                details={"original_category": error.info.category, "original_code": error.info.code},
            )
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.WAITING_EXTERNAL,
                event_type="task.unknown_submission",
                error=error.to_info(),
            )
        if is_retryable(error):
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.FAILED_RETRYABLE,
                event_type="task.submit_retryable",
                error=error.to_info(),
            )
        return self.state.transition(
            task_run.execution_id,
            TaskRunState.FAILED_FINAL,
            event_type="task.submit_failed",
            error=error.to_info(),
        )

    async def _poll_until_done(self, task_run: TaskRun) -> TaskRun:
        if task_run.deadline and self.clock.now() > task_run.deadline:
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.TIMED_OUT,
                event_type="task.timed_out",
                error=ErrorInfo(
                    category=FailureCategory.TIMEOUT,
                    code="deadline",
                    message="task deadline exceeded",
                    retryable=False,
                ),
            )
        submission = self._submission_from_task(task_run)
        if task_run.status == TaskRunState.SUBMITTED:
            task_run = self.state.transition(
                task_run.execution_id,
                TaskRunState.RUNNING,
                event_type="task.running",
            )
        while True:
            current = self._require(task_run.execution_id)
            if current.status in TERMINAL_STATES:
                return current
            if current.deadline and self.clock.now() > current.deadline:
                return self.state.transition(
                    current.execution_id,
                    TaskRunState.TIMED_OUT,
                    event_type="task.timed_out",
                    error=ErrorInfo(
                        category=FailureCategory.TIMEOUT,
                        code="deadline",
                        message="task deadline exceeded",
                        retryable=False,
                    ),
                )
            if current.status == TaskRunState.WAITING_EXTERNAL and not current.external_job_id:
                # unknown submission: do not poll or resubmit
                return current
            try:
                async with self.pool.poll:
                    status = await self.sut.poll(submission)
            except TrueEvalError as exc:
                if is_retryable(exc):
                    await asyncio.sleep(self.manifest.execution.poll_interval_seconds)
                    continue
                return self.state.transition(
                    current.execution_id,
                    TaskRunState.FAILED_FINAL,
                    event_type="task.poll_failed",
                    error=exc.to_info(),
                )
            task_run = self._apply_poll(current, status)
            if task_run.status in {
                TaskRunState.COMPLETED,
                TaskRunState.COMPLETED_SYNC,
                TaskRunState.FAILED_FINAL,
                TaskRunState.FAILED_RETRYABLE,
                TaskRunState.TIMED_OUT,
                TaskRunState.CANCELLED,
            }:
                return task_run
            await asyncio.sleep(self.manifest.execution.poll_interval_seconds)

    def _apply_poll(self, task_run: TaskRun, status: JobStatus) -> TaskRun:
        if status.phase == "completed":
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.COMPLETED,
                event_type="task.completed",
            )
        if status.phase in {"queued", "waiting", "unknown"}:
            if task_run.status != TaskRunState.WAITING_EXTERNAL:
                return self.state.transition(
                    task_run.execution_id,
                    TaskRunState.WAITING_EXTERNAL,
                    event_type="task.waiting_external",
                    payload={"provider_status": status.provider_status},
                )
            return task_run
        if status.phase == "running":
            if task_run.status != TaskRunState.RUNNING:
                return self.state.transition(
                    task_run.execution_id,
                    TaskRunState.RUNNING,
                    event_type="task.running",
                )
            return task_run
        if status.phase == "timeout":
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.TIMED_OUT,
                event_type="task.timed_out",
                error=ErrorInfo(
                    category=FailureCategory.TIMEOUT,
                    code="provider_timeout",
                    message=status.message or "provider timeout",
                    retryable=False,
                    provider_status=status.provider_status,
                ),
            )
        if status.phase == "cancelled":
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.CANCELLED,
                event_type="task.cancelled",
            )
        if status.phase == "not_found":
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.FAILED_RETRYABLE if self.sut.spec().provider_idempotency else TaskRunState.WAITING_EXTERNAL,
                event_type="task.job_not_found",
                error=ErrorInfo(
                    category=FailureCategory.UNKNOWN_SUBMISSION,
                    code="job_not_found",
                    message="provider reports job not found",
                    retryable=self.sut.spec().provider_idempotency,
                ),
            )
        if status.phase == "failed":
            target = TaskRunState.FAILED_RETRYABLE if status.retryable else TaskRunState.FAILED_FINAL
            return self.state.transition(
                task_run.execution_id,
                target,
                event_type="task.provider_failed",
                error=ErrorInfo(
                    category=FailureCategory.PROVIDER_ERROR,
                    code="provider_failed",
                    message=status.message or "provider failed",
                    retryable=status.retryable,
                    provider_status=status.provider_status,
                ),
            )
        return task_run

    async def _collect_normalize_grade(self, task_run: TaskRun, spec: TaskSpec) -> TaskRun:
        session = SessionHandle(
            session_id=task_run.session_id or task_run.execution_id,
            execution_id=task_run.execution_id,
        )
        submission = self._submission_from_task(task_run)
        try:
            async with self.pool.collect:
                raw = await self.sut.collect(session, submission)
        except TrueEvalError as exc:
            target = TaskRunState.FAILED_RETRYABLE if is_retryable(exc) else TaskRunState.FAILED_FINAL
            return self.state.transition(
                task_run.execution_id,
                target,
                event_type="task.collect_failed",
                error=exc.to_info(),
            )
        except Exception as exc:
            error = from_exception(exc)
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.FAILED_RETRYABLE if is_retryable(error) else TaskRunState.FAILED_FINAL,
                event_type="task.collect_failed",
                error=error.to_info(),
            )
        finally:
            try:
                await self.sut.close(session)
                await self.sut.close(session)
            except Exception:
                log.warning("session close failed", extra={"execution_id": task_run.execution_id})

        raw_ref = self.artifacts.write_protected(
            self.manifest.run_id,
            task_run.execution_id,
            "raw_response.enc",
            dump_canonical(raw),
            kind="raw_response",
        )
        eval_raw = self.artifacts.write_evaluation_json(
            self.manifest.run_id,
            task_run.execution_id,
            "raw_result.json",
            dump_canonical(raw),
            kind="raw_response",
            source_sha256=raw_ref.sha256,
        )
        reservation = task_run.extra.get("reservation_id")
        if reservation:
            actual = None
            if isinstance(raw.usage, dict):
                actual = raw.usage.get("cost_usd")
            self.state.settle_budget(str(reservation), float(actual) if actual is not None else None)
        task_run = self.state.transition(
            task_run.execution_id,
            TaskRunState.COLLECTED,
            event_type="artifact.raw_collected",
            updates={"raw_result_uri": eval_raw.uri, "output_uri": raw_ref.uri},
        )
        return await self._normalize_and_grade(task_run, spec, raw=raw)

    async def _normalize_and_grade(
        self,
        task_run: TaskRun,
        spec: TaskSpec,
        raw: RawSUTResult | None = None,
    ) -> TaskRun:
        if raw is None:
            if not task_run.raw_result_uri:
                raise TrueEvalError(
                    "missing raw result for normalize",
                    category=FailureCategory.PARSE_ERROR,
                    code="missing_raw",
                    retryable=False,
                )
            raw = RawSUTResult.model_validate(self.artifacts.read_json(task_run.raw_result_uri))
        try:
            answer = self.benchmark.normalize(raw, spec, self.ctx)
        except TrueEvalError as exc:
            target = TaskRunState.FAILED_RETRYABLE if is_retryable(exc) else TaskRunState.FAILED_FINAL
            return self.state.transition(
                task_run.execution_id,
                target,
                event_type="task.normalize_failed",
                error=exc.to_info(),
            )
        pointers = ArtifactPointers(
            raw_response_uri=task_run.raw_result_uri,
            raw_request_uri=task_run.input_uri,
        )
        answer.artifacts = pointers
        if raw.search_results:
            search_ref = self.artifacts.write_evaluation_json(
                self.manifest.run_id,
                task_run.execution_id,
                "search_results.json",
                {"results": raw.search_results},
                kind="search_results",
            )
            answer.artifacts.search_results_uri = search_ref.uri
        if answer.final_answer:
            report_ref = self.artifacts.write_text(
                f"runs/{self.manifest.run_id}/artifacts/{task_run.execution_id}/evaluation/report.md",
                answer.final_answer,
                kind="report",
                media_type="text/markdown",
            )
            answer.artifacts.report_uri = report_ref.uri
        answer_ref = self.artifacts.write_evaluation_json(
            self.manifest.run_id,
            task_run.execution_id,
            "research_answer.json",
            dump_canonical(answer),
            kind="research_answer",
        )
        task_run = self.state.transition(
            task_run.execution_id,
            TaskRunState.NORMALIZED,
            event_type="task.normalized",
            updates={"answer_uri": answer_ref.uri},
        )
        return await self._grade(task_run, spec, answer=answer)

    async def _grade(
        self,
        task_run: TaskRun,
        spec: TaskSpec,
        answer: ResearchAnswer | None = None,
    ) -> TaskRun:
        if answer is None:
            if not task_run.answer_uri:
                return self.state.transition(
                    task_run.execution_id,
                    TaskRunState.FAILED_FINAL,
                    event_type="task.missing_answer",
                    error=ErrorInfo(
                        category=FailureCategory.PARSE_ERROR,
                        code="missing_answer",
                        message="no research answer artifact",
                        retryable=False,
                    ),
                )
            answer = ResearchAnswer.model_validate(self.artifacts.read_json(task_run.answer_uri))
        task_run = self.state.transition(
            task_run.execution_id,
            TaskRunState.GRADING,
            event_type="task.grading",
        )
        gold = self.benchmark.load_gold(spec.task_id)
        await self.graders.grade_execution(
            run_id=self.manifest.run_id,
            execution_id=task_run.execution_id,
            task=spec,
            answer=answer,
            gold=gold,
            specs=self.grader_specs,
            select=True,
        )
        return self.state.transition(
            task_run.execution_id,
            TaskRunState.SCORED,
            event_type="task.scored",
        )

    async def _retry_or_finalize(self, task_run: TaskRun) -> TaskRun:
        if task_run.attempt_count >= self.retry.max_attempts:
            return self.state.transition(
                task_run.execution_id,
                TaskRunState.FAILED_FINAL,
                event_type="task.retry_exhausted",
                error=task_run.last_error,
            )
        delay = backoff_seconds(task_run.attempt_count, self.retry)
        await asyncio.sleep(delay)
        target = TaskRunState.RUNNING if task_run.external_job_id else TaskRunState.READY
        self.state.transition(
            task_run.execution_id,
            TaskRunState.RETRYING,
            event_type="task.retrying",
        )
        return self.state.transition(
            task_run.execution_id,
            target,
            event_type="task.retry_resume",
        )

    def apply_import(self, execution_id: str, raw: RawSUTResult) -> TaskRun:
        self._require(execution_id)
        raw_ref = self.artifacts.write_protected(
            self.manifest.run_id,
            execution_id,
            "raw_response.enc",
            dump_canonical(raw),
            kind="raw_response",
        )
        eval_raw = self.artifacts.write_evaluation_json(
            self.manifest.run_id,
            execution_id,
            "raw_result.json",
            dump_canonical(raw),
            kind="raw_response",
            source_sha256=raw_ref.sha256,
        )
        return self.state.transition(
            execution_id,
            TaskRunState.COLLECTED,
            event_type="import.collected",
            updates={"raw_result_uri": eval_raw.uri, "output_uri": raw_ref.uri},
        )

    async def finish_imported(self, execution_id: str) -> TaskRun:
        task_run = self._require(execution_id)
        spec = self.tasks[task_run.task_id]
        return await self._normalize_and_grade(task_run, spec)

    def _write_submission_artifacts(
        self,
        task_run: TaskRun,
        package: InputPackage,
        submission: Submission,
    ) -> None:
        request = {
            "idempotency_key": submission.idempotency_key,
            "input_hash": package.input_hash,
            "task_id": package.task_id,
        }
        self.artifacts.write_protected(
            self.manifest.run_id,
            task_run.execution_id,
            "raw_request.enc",
            request,
            kind="raw_request",
        )
        self.artifacts.write_evaluation_json(
            self.manifest.run_id,
            task_run.execution_id,
            "request.json",
            request,
            kind="raw_request",
        )

    def _submission_from_task(self, task_run: TaskRun) -> Submission:
        return Submission(
            submission_id=task_run.extra.get("submission_id") or uuid7(),
            execution_id=task_run.execution_id,
            idempotency_key=task_run.idempotency_key or "",
            external_job_id=task_run.external_job_id,
            channel=self.manifest.sut.channel,  # type: ignore[arg-type]
        )

    def _fail(self, task_run: TaskRun, error: TrueEvalError) -> TaskRun:
        target = TaskRunState.FAILED_RETRYABLE if is_retryable(error) else TaskRunState.FAILED_FINAL
        if task_run.status in TERMINAL_STATES:
            return task_run
        try:
            return self.state.transition(
                task_run.execution_id,
                target,
                event_type="task.failed",
                error=error.to_info(),
            )
        except TrueEvalError:
            return task_run

    def _require(self, execution_id: str) -> TaskRun:
        loaded = self.state.get_task_run(execution_id)
        if loaded is None:
            raise TrueEvalError(
                f"missing task run {execution_id}",
                category=FailureCategory.STATE_ERROR,
                code="missing_task_run",
                retryable=False,
            )
        return loaded


def input_hash_for(package_fields: dict[str, Any]) -> str:
    return sha256_json(package_fields)
