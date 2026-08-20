"""Create, plan, start, resume, and cancel Runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.hashing import sha256_json
from trueeval.core.ids import execution_id, run_id
from trueeval.core.logging import get_logger
from trueeval.core.orchestration.gate import assert_gate_allows, evaluate_gate
from trueeval.core.orchestration.grader_router import GraderRouter
from trueeval.core.orchestration.rate_limit import CapacityPool
from trueeval.core.orchestration.runner import ExecutionRunner
from trueeval.core.protocols import BenchmarkAdapter, SUTAdapter
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.common import dump_canonical
from trueeval.core.schemas.config import RunConfig
from trueeval.core.schemas.grader import GraderSpec
from trueeval.core.schemas.run import (
    BenchmarkPin,
    BudgetPin,
    ExecutionPin,
    GraderPin,
    RetentionPin,
    RunManifest,
    SUTPin,
)
from trueeval.core.schemas.task import TaskRun
from trueeval.core.state_machine.states import TERMINAL_STATES, TaskRunState
from trueeval.core.timeutil import Clock, SystemClock
from trueeval.reporting.aggregator import aggregate_run
from trueeval.reporting.reporter import write_report
from trueeval.storage.artifacts import ArtifactStore
from trueeval.storage.events import EventProjector
from trueeval.storage.state import StateStore

log = get_logger("run_service")


class RunService:
    def __init__(
        self,
        *,
        workspace: Path,
        state: StateStore,
        artifacts: ArtifactStore,
        benchmark: BenchmarkAdapter,
        sut: SUTAdapter,
        graders: dict[str, object],
        clock: Clock | None = None,
        code_commit_sha: str | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.state = state
        self.artifacts = artifacts
        self.benchmark = benchmark
        self.sut = sut
        self.graders = graders
        self.clock = clock or SystemClock()
        self.code_commit_sha = code_commit_sha
        self.projector = EventProjector(state, artifacts)

    def plan(self, config: RunConfig) -> dict[str, Any]:
        """Dry-run: no external SUT calls."""
        spec = self.benchmark.spec()
        tasks = self._select_tasks(config)
        gate = evaluate_gate(config, spec)
        sut = self.sut.spec()
        missing = [
            cap
            for cap in (self.benchmark.required_capabilities() or spec.required_capabilities or spec.default_execution.allowed_tools)
            if cap not in {"web_search", "browser", "citations"} or not getattr(sut, "provider_idempotency", True)
        ]
        _ = missing
        estimated = config.execution.estimated_cost_usd_per_task * len(tasks) * config.execution.repeats
        return {
            "schema_version": "trueeval.run_plan.v0.1",
            "benchmark_id": spec.benchmark_id,
            "split": config.benchmark.split,
            "sut_id": sut.sut_id,
            "n_tasks": len(tasks),
            "repeats": config.execution.repeats,
            "n_executions": len(tasks) * config.execution.repeats,
            "estimated_cost_usd": estimated,
            "budget_usd": config.budget.max_cost_usd,
            "gate": dump_canonical(gate),
            "channel": sut.channel,
            "provider_idempotency": sut.provider_idempotency,
            "submission_lookup": sut.submission_lookup,
            "allow_regeneration": config.execution.allow_regeneration,
        }

    def create(self, config: RunConfig) -> RunManifest:
        spec = self.benchmark.spec()
        gate = evaluate_gate(config, spec)
        assert_gate_allows(gate)
        tasks = self._select_tasks(config)
        if not tasks:
            raise TrueEvalError(
                "no tasks selected",
                category=FailureCategory.INVALID_ARGUMENT,
                code="empty_split",
                retryable=False,
            )
        capabilities = _capability_names(self.sut.spec())
        required = self.benchmark.required_capabilities() or spec.default_execution.allowed_tools
        unsupported = [c for c in required if c not in capabilities and c not in {"web_search", "browser"}]
        # capability negotiation is recorded; hard UNSUPPORTED is applied per-task later if needed
        _ = unsupported
        rid = run_id()
        grader_specs = self._resolve_graders(config)
        manifest = self._build_manifest(rid, config, spec, tasks, grader_specs, gate.gate_id)
        self.artifacts.run_path(rid)
        gate.run_id = rid
        gate_ref = self.artifacts.write_json(
            f"runs/{rid}/gate.json",
            dump_canonical(gate),
            kind="gate_record",
        )
        manifest.gate_record_uri = gate_ref.uri
        snapshot = [dump_canonical(t) for t in tasks]
        self.artifacts.write_jsonl(f"runs/{rid}/tasks.snapshot.jsonl", snapshot)
        manifest_ref = self.artifacts.write_json(
            f"runs/{rid}/manifest.json",
            dump_canonical(manifest),
            kind="gate_record",
        )
        self.state.create_run(
            run_id=rid,
            manifest_uri=manifest_ref.uri,
            manifest_hash=manifest_ref.sha256,
            created_by=config.created_by,
        )
        self.state.set_run_status(rid, "frozen", {"manifest_hash": manifest_ref.sha256})
        task_runs = []
        now = self.clock.now()
        for task in tasks:
            for repeat in range(config.execution.repeats):
                task_runs.append(
                    TaskRun(
                        run_id=rid,
                        execution_id=execution_id(),
                        task_id=task.task_id,
                        repeat_index=repeat,
                        status=TaskRunState.CREATED,
                        created_at=now,
                        updated_at=now,
                    )
                )
        self.state.insert_task_runs(task_runs)
        self.projector.project(rid)
        return manifest

    async def start(self, run_id_value: str) -> dict[str, Any]:
        manifest = self.load_manifest(run_id_value)
        self.state.set_run_status(run_id_value, "running")
        result = await self._drive(manifest)
        self.projector.project(run_id_value)
        return result

    async def resume(self, run_id_value: str) -> dict[str, Any]:
        manifest = self.load_manifest(run_id_value)
        pending = self.state.list_nonterminal(run_id_value)
        for task in pending:
            if task.status == TaskRunState.SUBMITTING and not task.external_job_id:
                self.state.transition(
                    task.execution_id,
                    TaskRunState.WAITING_EXTERNAL,
                    event_type="task.recovery_unknown_submit",
                    error=TrueEvalError(
                        "process restarted while submitting; waiting for provider lookup or manual disposition",
                        category=FailureCategory.UNKNOWN_SUBMISSION,
                        code="unknown_submission",
                        retryable=False,
                    ).to_info(),
                )
        self.state.set_run_status(run_id_value, "running")
        result = await self._drive(manifest)
        self.projector.project(run_id_value)
        return result

    def cancel(self, run_id_value: str) -> None:
        pending = self.state.list_nonterminal(run_id_value)
        for task in pending:
            if task.status not in TERMINAL_STATES:
                try:
                    self.state.transition(
                        task.execution_id,
                        TaskRunState.CANCELLED,
                        event_type="task.cancelled",
                    )
                except TrueEvalError:
                    continue
        self.state.set_run_status(run_id_value, "cancelled")
        self.projector.project(run_id_value)

    def status(self, run_id_value: str) -> dict[str, Any]:
        run = self.state.get_run(run_id_value)
        if run is None:
            raise TrueEvalError(
                f"run {run_id_value} not found",
                category=FailureCategory.INVALID_ARGUMENT,
                code="run_not_found",
                retryable=False,
            )
        tasks = self.state.list_task_runs(run_id_value)
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        return {
            "run_id": run_id_value,
            "status": run["status"],
            "n_task_runs": len(tasks),
            "status_counts": counts,
            "budget_used_usd": self.state.budget_used(run_id_value),
            "updated_at": run["updated_at"],
        }

    def load_manifest(self, run_id_value: str) -> RunManifest:
        data = self.artifacts.read_json(f"runs/{run_id_value}/manifest.json")
        return RunManifest.model_validate(data)

    def load_tasks(self, run_id_value: str) -> list[TaskSpec]:
        path = self.artifacts.run_path(run_id_value) / "tasks.snapshot.jsonl"
        tasks: list[TaskSpec] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                tasks.append(TaskSpec.model_validate_json(line))
        return tasks

    async def grade_only(self, run_id_value: str, grader_id: str | None = None) -> list[str]:
        """Re-grade existing artifacts. Never calls the SUT."""
        manifest = self.load_manifest(run_id_value)
        tasks = {t.task_id: t for t in self.load_tasks(run_id_value)}
        specs = self._resolve_graders_from_manifest(manifest)
        if grader_id:
            specs = [s for s in specs if s.grader_id == grader_id]
        router = GraderRouter(self.graders, state=self.state, artifacts=self.artifacts)
        job_ids: list[str] = []
        for task_run in self.state.list_task_runs(run_id_value):
            if not task_run.answer_uri:
                continue
            from trueeval.core.schemas.artifact import ResearchAnswer

            answer = ResearchAnswer.model_validate(self.artifacts.read_json(task_run.answer_uri))
            gold = self.benchmark.load_gold(task_run.task_id)
            scores = await router.grade_execution(
                run_id=run_id_value,
                execution_id=task_run.execution_id,
                task=tasks[task_run.task_id],
                answer=answer,
                gold=gold,
                specs=specs,
                select=True,
            )
            job_ids.extend(sorted({s.grading_job_id for s in scores}))
        self.projector.project(run_id_value)
        return job_ids

    def build_report(self, run_id_value: str) -> Path:
        manifest = self.load_manifest(run_id_value)
        tasks = self.state.list_task_runs(run_id_value)
        scores = self.state.list_scores(run_id_value, selected_only=True)
        if not scores:
            scores = self.state.list_scores(run_id_value, selected_only=False)
        answers = []
        for task in tasks:
            if task.answer_uri:
                from trueeval.core.schemas.artifact import ResearchAnswer

                answers.append(ResearchAnswer.model_validate(self.artifacts.read_json(task.answer_uri)))
        summary = aggregate_run(manifest, tasks, scores, answers)
        return write_report(self.artifacts, manifest, summary, tasks, scores)

    async def _drive(self, manifest: RunManifest) -> dict[str, Any]:
        tasks = {t.task_id: t for t in self.load_tasks(manifest.run_id)}
        router = GraderRouter(self.graders, state=self.state, artifacts=self.artifacts)
        pool = CapacityPool(
            submit=manifest.execution.submit_concurrency,
            poll=manifest.execution.poll_concurrency,
            collect=manifest.execution.collect_concurrency,
            fetch=manifest.execution.fetch_concurrency,
            judge=manifest.execution.judge_concurrency,
        )
        runner = ExecutionRunner(
            manifest=manifest,
            state=self.state,
            artifacts=self.artifacts,
            projector=self.projector,
            benchmark=self.benchmark,
            sut=self.sut,
            graders=router,
            grader_specs=self._resolve_graders_from_manifest(manifest),
            pool=pool,
            clock=self.clock,
            tasks=tasks,
        )
        pending = [t for t in self.state.list_task_runs(manifest.run_id) if t.status not in TERMINAL_STATES]
        sem = asyncio.Semaphore(manifest.execution.submit_concurrency)

        async def _one(execution: str) -> None:
            async with sem:
                await runner.run(execution)

        await asyncio.gather(*[_one(t.execution_id) for t in pending])
        remaining = self.state.list_nonterminal(manifest.run_id)
        status = "completed" if not remaining else "paused"
        self.state.set_run_status(manifest.run_id, status)
        return self.status(manifest.run_id)

    def _select_tasks(self, config: RunConfig) -> list[TaskSpec]:
        tasks = self.benchmark.load_tasks(config.benchmark.split)
        if config.benchmark.task_ids:
            wanted = set(config.benchmark.task_ids)
            tasks = [t for t in tasks if t.task_id in wanted]
        if config.benchmark.sample_limit is not None:
            tasks = tasks[: config.benchmark.sample_limit]
        return tasks

    def _resolve_graders(self, config: RunConfig) -> list[GraderSpec]:
        required = list(self.benchmark.required_graders())
        by_id = {g.grader_id: g for g in required}
        names = config.grading.graders or [g.grader_id for g in required]
        resolved: list[GraderSpec] = []
        for name in names:
            if name in by_id:
                resolved.append(by_id[name])
            elif name in self.graders:
                resolved.append(self.graders[name].spec())  # type: ignore[attr-defined]
            else:
                raise TrueEvalError(
                    f"unknown grader {name}",
                    category=FailureCategory.INVALID_ARGUMENT,
                    code="unknown_grader",
                    retryable=False,
                )
        if config.grading.judge_provider or config.grading.judge_model:
            resolved = [
                spec.model_copy(
                    update={
                        "judge_provider": config.grading.judge_provider,
                        "judge_model": config.grading.judge_model,
                    }
                )
                for spec in resolved
            ]
        return resolved

    def _resolve_graders_from_manifest(self, manifest: RunManifest) -> list[GraderSpec]:
        specs: list[GraderSpec] = []
        for pin in manifest.graders:
            adapter = self.graders.get(pin.grader_id)
            if adapter is None:
                continue
            specs.append(adapter.spec())  # type: ignore[attr-defined]
        return specs

    def _build_manifest(
        self,
        rid: str,
        config: RunConfig,
        spec: Any,
        tasks: list[TaskSpec],
        grader_specs: list[GraderSpec],
        gate_id: str,
    ) -> RunManifest:
        snapshot_hash = sha256_json([dump_canonical(t) for t in tasks])
        sut = self.sut.spec()
        return RunManifest(
            run_id=rid,
            benchmark=BenchmarkPin(
                benchmark_id=spec.benchmark_id,
                version=spec.benchmark_version,
                split=config.benchmark.split,
                commit_sha=spec.upstream.commit_sha,
                data_hash=snapshot_hash,
                license=spec.upstream.license,
                task_count=len(tasks),
            ),
            sut=SUTPin(
                sut_id=sut.sut_id,
                provider=sut.provider,
                product=sut.product,
                model=config.sut.model or sut.model,
                endpoint_family=sut.endpoint_family,
                channel=config.sut.channel or sut.channel,
                parameters=dict(config.sut.parameters),
                provider_idempotency=sut.provider_idempotency,
                submission_lookup=sut.submission_lookup,
            ),
            graders=[
                GraderPin(
                    grader_id=g.grader_id,
                    version=g.version,
                    prompt_hash=g.prompt_hash,
                    config_hash=sha256_json(dump_canonical(g)),
                    config=dict(g.config),
                )
                for g in grader_specs
            ],
            execution=ExecutionPin(
                repeats=config.execution.repeats,
                submit_concurrency=config.execution.submit_concurrency,
                poll_concurrency=config.execution.poll_concurrency,
                collect_concurrency=config.execution.collect_concurrency,
                fetch_concurrency=config.execution.fetch_concurrency,
                judge_concurrency=config.execution.judge_concurrency,
                poll_interval_seconds=config.execution.poll_interval_seconds,
                task_timeout_seconds=config.execution.task_timeout_seconds,
                allow_regeneration=config.execution.allow_regeneration,
                max_attempts=config.execution.max_attempts,
                seed=config.execution.seed,
                estimated_cost_usd_per_task=config.execution.estimated_cost_usd_per_task,
            ),
            budget=BudgetPin(max_cost_usd=config.budget.max_cost_usd, hard_stop=config.budget.hard_stop),
            retention=RetentionPin(
                artifact_days=config.retention.artifact_days,
                protected_days=config.retention.protected_days,
                evaluation_days=config.retention.evaluation_days,
            ),
            seed=config.execution.seed,
            created_at=self.clock.now(),
            created_by=config.created_by,
            code_commit_sha=self.code_commit_sha,
            resolved_config=json.loads(config.model_dump_json()),
            workspace=str(self.workspace),
        )


def _capability_names(spec: Any) -> set[str]:
    names = {"provider_idempotency", "submission_lookup"}
    if spec.channel == "API_SYNC":
        names.add("sync")
    if spec.channel == "API_ASYNC":
        names.add("async_jobs")
    return names
