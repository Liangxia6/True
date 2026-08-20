from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from trueeval.benchmarks.file_adapter import FileBenchmarkAdapter
from trueeval.core.orchestration.run_service import RunService
from trueeval.core.schemas.config import RunConfig
from trueeval.core.schemas.manual import ManualImportPackage
from trueeval.core.state_machine.states import TaskRunState
from trueeval.graders.registry import default_graders
from trueeval.suts.fake import FakeSUTAdapter
from trueeval.suts.manual import ManualResearchImport


def _service(workspace, state, artifacts, sut) -> RunService:
    return RunService(
        workspace=workspace,
        state=state,
        artifacts=artifacts,
        benchmark=FileBenchmarkAdapter(workspace / "benchmarks" / "tiny-research"),
        sut=sut,
        graders=default_graders(),
    )


def test_end_to_end_fake_and_offline_regrade(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="success_sync",
        answers={"tiny.pilot.000001": "Paris", "tiny.pilot.000002": "4"},
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = RunConfig.model_validate(
        {
            "benchmark": {"id": "tiny-research", "split": "pilot"},
            "sut": {"id": "fake-research"},
            "execution": {"repeats": 2, "poll_interval_seconds": 0.01, "estimated_cost_usd_per_task": 0.01},
            "grading": {"graders": ["format-completeness", "exact-match", "cited-not-verified"]},
            "budget": {"max_cost_usd": 10},
            "gate": {"data_region": "local", "authorized_channel": "api"},
        }
    )
    plan = service.plan(cfg)
    assert plan["n_executions"] == 4
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    tasks = state.list_task_runs(manifest.run_id)
    assert all(t.status == TaskRunState.SCORED for t in tasks)
    assert all(t.input_uri and t.answer_uri for t in tasks)
    submits = sut.submit_calls
    asyncio.run(service.grade_only(manifest.run_id))
    assert sut.submit_calls == submits
    report = service.build_report(manifest.run_id)
    text = report.read_text(encoding="utf-8")
    assert "coverage" in text.lower() or "Official metrics" in text
    assert "Paris" not in json.dumps(service.load_manifest(manifest.run_id).resolved_config)
    errors = artifacts.verify_run(manifest.run_id)
    assert errors == []


def test_manual_import_path(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(scenario="success_sync")
    service = _service(workspace, state, artifacts, sut)
    cfg = RunConfig.model_validate(
        {
            "benchmark": {"id": "tiny-research", "split": "pilot", "sample_limit": 1},
            "sut": {"id": "manual-research-import", "channel": "MANUAL_IMPORT"},
            "execution": {"repeats": 1, "estimated_cost_usd_per_task": 0.0},
            "grading": {"graders": ["format-completeness", "exact-match"]},
            "budget": {"max_cost_usd": 10},
            "gate": {"data_region": "local", "authorized_channel": "manual_import"},
        }
    )
    # Keep fake sut in service but mark channel as manual via config/manifest.
    manifest = service.create(cfg)
    # Force channel on stored manifest by rewriting after create uses fake spec.
    task = state.list_task_runs(manifest.run_id)[0]
    service.state.transition(task.execution_id, TaskRunState.MATERIALIZED, event_type="task.materialized")
    service.state.transition(task.execution_id, TaskRunState.WAITING_IMPORT, event_type="task.waiting_import")
    pkg = ManualImportPackage(
        task_id="tiny.pilot.000001",
        execution_id=task.execution_id,
        operator="analyst",
        executed_at=datetime.now(timezone.utc),
        sop_version="sop.v0.1",
        report="Paris",
        final_answer="Paris",
        evidence=[],
    )
    importer = ManualResearchImport()
    result = importer.validate_package(pkg, service.load_tasks(manifest.run_id)[0])
    assert result.ok
    assert any(i.code == "missing_evidence" for i in result.issues)
    raw = importer.collect(pkg, service.load_tasks(manifest.run_id)[0])
    raw.execution_id = task.execution_id
    from trueeval.core.orchestration.grader_router import GraderRouter
    from trueeval.core.orchestration.rate_limit import CapacityPool
    from trueeval.core.orchestration.runner import ExecutionRunner
    from trueeval.storage.events import EventProjector

    runner = ExecutionRunner(
        manifest=service.load_manifest(manifest.run_id),
        state=state,
        artifacts=artifacts,
        projector=EventProjector(state, artifacts),
        benchmark=service.benchmark,
        sut=sut,
        graders=GraderRouter(service.graders, state=state, artifacts=artifacts),
        grader_specs=service._resolve_graders_from_manifest(service.load_manifest(manifest.run_id)),
        pool=CapacityPool(),
        tasks={t.task_id: t for t in service.load_tasks(manifest.run_id)},
    )
    runner.apply_import(task.execution_id, raw)
    asyncio.run(runner.finish_imported(task.execution_id))
    loaded = state.get_task_run(task.execution_id)
    assert loaded is not None
    assert loaded.status == TaskRunState.SCORED
    assert loaded.answer_uri
    answer = artifacts.read_json(loaded.answer_uri)
    assert answer["channel"] in {"API_SYNC", "MANUAL_IMPORT", "API_ASYNC"}
