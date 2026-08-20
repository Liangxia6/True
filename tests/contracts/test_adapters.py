from __future__ import annotations

import asyncio

from trueeval.benchmarks.file_adapter import FileBenchmarkAdapter
from trueeval.core.protocols import RunContext
from trueeval.core.schemas.run import (
    BenchmarkPin,
    BudgetPin,
    ExecutionPin,
    RetentionPin,
    RunManifest,
    SUTPin,
)
from trueeval.graders.exact_match import ExactMatchGrader
from trueeval.graders.format import FormatCompletenessGrader
from trueeval.suts.fake import FakeSUTAdapter


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="run-1",
        benchmark=BenchmarkPin(
            benchmark_id="tiny-research",
            version="fixture-0.1",
            split="pilot",
            commit_sha="0" * 40,
            data_hash="sha256:0",
            license="MIT",
            task_count=2,
        ),
        sut=SUTPin(
            sut_id="fake-research",
            provider="fake",
            product="fake-research",
            model="fake-model",
            endpoint_family="in_process",
            channel="API_SYNC",
            provider_idempotency=True,
            submission_lookup=True,
        ),
        execution=ExecutionPin(
            repeats=1,
            submit_concurrency=1,
            poll_concurrency=1,
            collect_concurrency=1,
            fetch_concurrency=1,
            judge_concurrency=1,
            poll_interval_seconds=0.01,
            task_timeout_seconds=30,
            allow_regeneration=False,
            max_attempts=2,
            seed=0,
            estimated_cost_usd_per_task=0.01,
        ),
        budget=BudgetPin(max_cost_usd=10, hard_stop=True),
        retention=RetentionPin(artifact_days=30, protected_days=30, evaluation_days=30),
        seed=0,
        created_by="test",
    )


def test_file_benchmark_contract(workspace) -> None:
    adapter = FileBenchmarkAdapter(workspace / "benchmarks" / "tiny-research")
    spec = adapter.spec()
    assert spec.benchmark_id == "tiny-research"
    assert spec.upstream.license
    tasks = adapter.load_tasks("pilot")
    assert [t.task_id for t in tasks] == sorted(t.task_id for t in tasks)
    assert len(tasks) == 2
    first = tasks[0]
    assert "Paris" not in first.input.prompt or first.task_id.endswith("000001")
    assert adapter.load_gold(first.task_id) is not None
    ctx = RunContext(manifest=_manifest())
    package = adapter.build_input(first, ctx)
    again = adapter.build_input(first, ctx)
    assert package.input_hash == again.input_hash
    graders = adapter.required_graders()
    assert any(g.grader_id == "exact-match" for g in graders)


def test_fake_sut_contract() -> None:
    sut = FakeSUTAdapter(scenario="success_sync", answers={"tiny.pilot.000001": "Paris"})
    spec = sut.spec()
    assert spec.provider_idempotency
    assert spec.submission_lookup

    async def _run() -> None:
        caps = await sut.capabilities()
        assert caps.provider_idempotency and caps.submission_lookup
        from trueeval.core.schemas.benchmark import TaskInput, TaskSpec

        task = TaskSpec(
            task_id="tiny.pilot.000001",
            benchmark_id="tiny-research",
            upstream_task_id="1",
            split="pilot",
            input=TaskInput(prompt="q"),
        )
        ctx = RunContext(manifest=_manifest(), extra={"execution_id": "e1"})
        session = await sut.start_session(task, ctx)
        from trueeval.core.schemas.sut import InputPackage

        pkg = InputPackage(task_id=task.task_id, prompt="q", input_hash="sha256:0")
        first = await sut.submit(session, pkg, "key-1")
        second = await sut.submit(session, pkg, "key-1")
        assert first.external_job_id == second.external_job_id
        found = await sut.lookup("key-1")
        assert found is not None
        status = await sut.poll(first)
        assert status.phase == "completed"
        raw = await sut.collect(session, first)
        assert raw.final_answer == "Paris"
        await sut.close(session)
        await sut.close(session)

    asyncio.run(_run())


def test_grader_cache_key_fields() -> None:
    spec = ExactMatchGrader().spec()
    assert spec.grader_id == "exact-match"
    assert FormatCompletenessGrader().spec().kind == "hard"
