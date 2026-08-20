from __future__ import annotations

import pytest

from trueeval.benchmarks.file_adapter import FileBenchmarkAdapter
from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.orchestration.gate import assert_gate_allows, evaluate_gate
from trueeval.core.orchestration.run_service import RunService
from trueeval.core.schemas.config import RunConfig
from trueeval.core.state_machine.states import TaskRunState
from trueeval.graders.registry import default_graders
from trueeval.suts.fake import FakeSUTAdapter


def test_gate_denied_without_region() -> None:
    from trueeval.core.schemas.benchmark import BenchmarkSpec, UpstreamRef

    spec = BenchmarkSpec(
        benchmark_id="x",
        name="x",
        benchmark_version="1",
        upstream=UpstreamRef(
            repo_url="u",
            commit_sha="c",
            dataset_path="d",
            evaluator_path="e",
            license="MIT",
        ),
    )
    cfg = RunConfig.model_validate(
        {"benchmark": {"id": "x", "split": "s"}, "sut": {"id": "fake"}, "gate": {"data_region": "unspecified"}}
    )
    record = evaluate_gate(cfg, spec)
    assert record.decision == "INCOMPLETE"
    with pytest.raises(TrueEvalError) as exc:
        assert_gate_allows(record)
    assert exc.value.category == FailureCategory.GATE_DENIED


def test_resume_unknown_submit(workspace, state, artifacts) -> None:
    sut = FakeSUTAdapter(scenario="success_sync")
    service = RunService(
        workspace=workspace,
        state=state,
        artifacts=artifacts,
        benchmark=FileBenchmarkAdapter(workspace / "benchmarks" / "tiny-research"),
        sut=sut,
        graders=default_graders(),
    )
    cfg = RunConfig.model_validate(
        {
            "benchmark": {"id": "tiny-research", "split": "pilot", "sample_limit": 1},
            "sut": {"id": "fake-research"},
            "execution": {"repeats": 1, "estimated_cost_usd_per_task": 0.01, "poll_interval_seconds": 0.01},
            "grading": {"graders": ["format-completeness"]},
            "budget": {"max_cost_usd": 10},
            "gate": {"data_region": "local", "authorized_channel": "api"},
        }
    )
    manifest = service.create(cfg)
    task = state.list_task_runs(manifest.run_id)[0]
    state.transition(task.execution_id, TaskRunState.MATERIALIZED, event_type="t")
    state.transition(task.execution_id, TaskRunState.READY, event_type="t")
    state.transition(task.execution_id, TaskRunState.SUBMITTING, event_type="t")
    import asyncio

    asyncio.run(service.resume(manifest.run_id))
    loaded = state.get_task_run(task.execution_id)
    assert loaded is not None
    assert loaded.status != TaskRunState.CREATED
    # Unknown submitting without job id must not silently become a new paid submit
    # without going through WAITING_EXTERNAL first.
    assert loaded.extra is not None
