from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from trueeval.core.orchestration.normalize import research_answer_from_raw
from trueeval.core.protocols import RunContext
from trueeval.core.schemas.artifact import ArtifactPointers
from trueeval.core.schemas.benchmark import TaskInput, TaskSpec
from trueeval.core.schemas.grader import GradeContext
from trueeval.core.schemas.run import (
    BenchmarkPin,
    BudgetPin,
    ExecutionPin,
    RetentionPin,
    RunManifest,
    SUTPin,
)
from trueeval.core.schemas.sut import InputPackage
from trueeval.graders.format import FormatCompletenessGrader
from trueeval.suts.kimi_research import KimiResearchSUT
from trueeval.suts.metaso_research import MetasoResearchSUT
from trueeval.suts.qwen_deep_research import QwenDeepResearchSUT
from trueeval.suts.registry import load_sut
from trueeval.suts.zhipu_qingyan import ZhipuQingyanSUT

REPO = Path(__file__).resolve().parents[2]


def _manifest(sut_id: str) -> RunManifest:
    return RunManifest(
        run_id="run-research",
        benchmark=BenchmarkPin(
            benchmark_id="tiny-research",
            version="fixture-0.1",
            split="pilot",
            commit_sha="0" * 40,
            data_hash="sha256:0",
            license="MIT",
            task_count=1,
        ),
        sut=SUTPin(
            sut_id=sut_id,
            provider=sut_id,
            product=sut_id,
            model="test-model",
            endpoint_family="test",
            channel="API_SYNC",
            provider_idempotency=False,
            submission_lookup=False,
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
            max_attempts=1,
            seed=0,
            estimated_cost_usd_per_task=0.01,
        ),
        budget=BudgetPin(max_cost_usd=10, hard_stop=True),
        retention=RetentionPin(artifact_days=30, protected_days=30, evaluation_days=30),
        seed=0,
        created_by="test",
    )


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="tiny.pilot.000001",
        benchmark_id="tiny-research",
        upstream_task_id="1",
        split="pilot",
        input=TaskInput(prompt="What is the capital of France?"),
    )


async def _roundtrip(sut) -> None:
    task = _task()
    ctx = RunContext(manifest=_manifest(sut.spec().sut_id), extra={"execution_id": "e1"})
    session = await sut.start_session(task, ctx)
    pkg = InputPackage(task_id=task.task_id, prompt=task.input.prompt, input_hash="sha256:0")
    submission = await sut.submit(session, pkg, "key-1")
    status = await sut.poll(submission)
    assert status.phase == "completed"
    raw = await sut.collect(session, submission)
    assert raw.final_answer == "Paris"
    assert raw.status == "completed"
    answer = research_answer_from_raw(
        raw=raw,
        task=task,
        manifest=ctx.manifest,
        pointers=ArtifactPointers(),
        execution_id="e1",
        repeat_index=0,
    )
    scores = await FormatCompletenessGrader().grade(
        task,
        [answer],
        GradeContext(
            run_id="run-research",
            execution_id="e1",
            grading_job_id="g1",
            task=task,
            grader_config_hash="sha256:0",
            input_artifact_hash="sha256:0",
        ),
    )
    assert scores[0].normalized_value == 1.0
    await sut.close(session)


def _chat_payload(answer: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 1},
        "citations": [{"url": "https://example.com/paris", "title": "Paris"}],
    }


def test_kimi_and_metaso_and_zhipu_score(monkeypatch) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.setenv("METASO_API_KEY", "test-key")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        messages = payload.get("messages") or []
        if any(isinstance(m, dict) and m.get("role") == "tool" for m in messages):
            return httpx.Response(200, json=_chat_payload("Paris"))
        if "moonshot" in str(request.url) and payload.get("tools"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "function": {
                                            "name": "$web_search",
                                            "arguments": '{"query":"capital of France"}',
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                },
            )
        return httpx.Response(200, json=_chat_payload("Paris"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def _run() -> None:
        await _roundtrip(KimiResearchSUT(client=client))
        await _roundtrip(MetasoResearchSUT(client=client))
        await _roundtrip(ZhipuQingyanSUT(client=client))

    asyncio.run(_run())


def test_qwen_sse_score(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    sse = (
        'data: {"output":{"message":{"phase":"WebResearch","content":"searching"}}}\n\n'
        'data: {"output":{"message":{"phase":"answer","content":"Paris","extra":'
        '{"references":[{"url":"https://example.com/paris","title":"Paris"}]}}},'
        '"usage":{"input_tokens":3,"output_tokens":1}}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse.encode("utf-8"),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    asyncio.run(_roundtrip(QwenDeepResearchSUT(client=client)))


def test_registry_loads_four_research_suts(workspace) -> None:
    configs = workspace / "configs" / "suts"
    configs.mkdir(parents=True, exist_ok=True)
    for name in (
        "kimi-research.yaml",
        "metaso-research.yaml",
        "qwen-deep-research.yaml",
        "zhipu-qingyan.yaml",
    ):
        configs.joinpath(name).write_bytes((REPO / "configs" / "suts" / name).read_bytes())
    for sut_id in ("kimi-research", "metaso-research", "qwen-deep-research", "zhipu-qingyan"):
        adapter = load_sut(sut_id, workspace=workspace)
        assert adapter.spec().sut_id == sut_id
        assert adapter.spec().channel == "API_SYNC"
