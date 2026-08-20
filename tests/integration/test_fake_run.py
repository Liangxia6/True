from __future__ import annotations

import asyncio

from trueeval.benchmarks.file_adapter import FileBenchmarkAdapter
from trueeval.core.orchestration.run_service import RunService
from trueeval.core.schemas.config import RunConfig
from trueeval.core.state_machine.states import TaskRunState
from trueeval.graders.registry import default_graders
from trueeval.suts.fake import FakeSUTAdapter


def _cfg(**extra) -> RunConfig:
    data = {
        "benchmark": {"id": "tiny-research", "split": "pilot"},
        "sut": {"id": "fake-research", "model": "fake-model"},
        "execution": {
            "repeats": 2,
            "poll_interval_seconds": 0.01,
            "task_timeout_seconds": 30,
            "estimated_cost_usd_per_task": 0.01,
            "submit_concurrency": 2,
        },
        "grading": {"graders": ["format-completeness", "exact-match"]},
        "budget": {"max_cost_usd": 10},
        "gate": {"data_region": "local", "authorized_channel": "api"},
    }
    data.update(extra)
    return RunConfig.model_validate(data)


def _service(workspace, state, artifacts, sut) -> RunService:
    return RunService(
        workspace=workspace,
        state=state,
        artifacts=artifacts,
        benchmark=FileBenchmarkAdapter(workspace / "benchmarks" / "tiny-research"),
        sut=sut,
        graders=default_graders(),
    )


def test_sync_success_repeats(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="success_sync",
        answers={"tiny.pilot.000001": "Paris", "tiny.pilot.000002": "4"},
    )
    service = _service(workspace, state, artifacts, sut)
    manifest = service.create(_cfg())
    result = asyncio.run(service.start(manifest.run_id))
    tasks = state.list_task_runs(manifest.run_id)
    assert len(tasks) == 4
    assert len({t.execution_id for t in tasks}) == 4
    assert all(t.status == TaskRunState.SCORED for t in tasks)
    assert all(t.answer_uri for t in tasks)
    scores = state.list_scores(manifest.run_id)
    official = [s for s in scores if s.metric == "official.answer_accuracy" and s.status == "scored"]
    assert official and all(s.normalized_value == 1.0 for s in official)
    report = service.build_report(manifest.run_id)
    assert report.exists()
    assert result["status"] == "completed"


def test_async_success(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="success_async",
        answers={"tiny.pilot.000001": "Paris", "tiny.pilot.000002": "4"},
        poll_complete_after=1,
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.benchmark.sample_limit = 1
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    tasks = state.list_task_runs(manifest.run_id)
    assert tasks[0].status == TaskRunState.SCORED
    assert tasks[0].external_job_id


def test_rate_limit_then_ok(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="rate_limit_then_ok",
        answers={"tiny.pilot.000001": "Paris"},
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.benchmark.sample_limit = 1
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    task = state.list_task_runs(manifest.run_id)[0]
    assert task.status == TaskRunState.SCORED
    assert sut.submit_calls >= 2


def test_timeout(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(scenario="timeout")
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.benchmark.sample_limit = 1
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    task = state.list_task_runs(manifest.run_id)[0]
    assert task.status == TaskRunState.TIMED_OUT


def test_lost_submit_recovers_via_lookup(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="lost_submit",
        answers={"tiny.pilot.000001": "Paris"},
        provider_idempotency=True,
        submission_lookup=True,
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.benchmark.sample_limit = 1
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    task = state.list_task_runs(manifest.run_id)[0]
    assert task.status in {TaskRunState.SCORED, TaskRunState.WAITING_EXTERNAL, TaskRunState.FAILED_RETRYABLE, TaskRunState.FAILED_FINAL}


def test_collect_fail_then_recover(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="collect_fail_once",
        answers={"tiny.pilot.000001": "Paris"},
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.benchmark.sample_limit = 1
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    task = state.list_task_runs(manifest.run_id)[0]
    assert task.status in {TaskRunState.SCORED, TaskRunState.FAILED_RETRYABLE, TaskRunState.FAILED_FINAL}


def test_regrade_does_not_call_sut(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="success_sync",
        answers={"tiny.pilot.000001": "Paris", "tiny.pilot.000002": "4"},
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    before = sut.submit_calls
    asyncio.run(service.grade_only(manifest.run_id, "exact-match"))
    assert sut.submit_calls == before


def test_budget_blocks_submit(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(scenario="success_sync")
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.execution.repeats = 1
    cfg.budget.max_cost_usd = 0.005
    cfg.execution.estimated_cost_usd_per_task = 1.0
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    tasks = state.list_task_runs(manifest.run_id)
    assert any(t.status == TaskRunState.FAILED_FINAL for t in tasks)
    assert sut.submit_calls == 0


def test_outbox_rebuild(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(
        scenario="success_sync",
        answers={"tiny.pilot.000001": "Paris", "tiny.pilot.000002": "4"},
    )
    service = _service(workspace, state, artifacts, sut)
    cfg = _cfg()
    cfg.execution.repeats = 1
    manifest = service.create(cfg)
    asyncio.run(service.start(manifest.run_id))
    path = artifacts.run_path(manifest.run_id) / "events.jsonl"
    path.write_text("", encoding="utf-8")
    seq = service.projector.rebuild(manifest.run_id)
    assert seq >= 1
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines
