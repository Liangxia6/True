"""In-process SUT used for contract and integration tests. Never a production score."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.ids import uuid7
from trueeval.core.protocols import RunContext
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.sut import (
    CapabilitySet,
    InputPackage,
    JobStatus,
    RawSUTResult,
    SessionHandle,
    Submission,
    SUTSpec,
)

Scenario = Literal[
    "success_sync",
    "success_async",
    "rate_limit_then_ok",
    "timeout",
    "lost_submit",
    "collect_fail_once",
    "provider_error",
    "policy_refusal",
]


class FakeSUTAdapter:
    def __init__(
        self,
        *,
        scenario: Scenario = "success_sync",
        answers: dict[str, str] | None = None,
        provider_idempotency: bool = True,
        submission_lookup: bool = True,
        poll_complete_after: int = 1,
    ) -> None:
        self.scenario = scenario
        self.answers = answers or {}
        self._spec = SUTSpec(
            sut_id="fake-research",
            provider="fake",
            product="fake-research",
            model="fake-model",
            endpoint_family="in_process",
            channel="API_SYNC" if scenario == "success_sync" else "API_ASYNC",
            provider_idempotency=provider_idempotency,
            submission_lookup=submission_lookup,
            estimated_cost_usd=0.01,
        )
        self.jobs: dict[str, dict[str, Any]] = {}
        self.by_idem: dict[str, Submission] = {}
        self.submit_calls = 0
        self.poll_counts: dict[str, int] = {}
        self.collect_calls = 0
        self.closed: set[str] = set()
        self.poll_complete_after = poll_complete_after

    def spec(self) -> SUTSpec:
        return self._spec

    async def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            provider_idempotency=self._spec.provider_idempotency,
            submission_lookup=self._spec.submission_lookup,
            web_search=True,
            citations=True,
            search_results=True,
            sync=self._spec.channel == "API_SYNC",
            async_jobs=self._spec.channel == "API_ASYNC",
        )

    async def start_session(self, task: TaskSpec, ctx: RunContext) -> SessionHandle:
        return SessionHandle(session_id=uuid7(), execution_id=str(ctx.extra.get("execution_id") or uuid7()))

    async def submit(
        self,
        session: SessionHandle,
        input: InputPackage,
        idempotency_key: str,
    ) -> Submission:
        if idempotency_key in self.by_idem and self._spec.provider_idempotency:
            return self.by_idem[idempotency_key]
        self.submit_calls += 1
        if self.scenario == "lost_submit" and self.submit_calls == 1:
            raise TrueEvalError(
                "simulated lost submit response",
                category=FailureCategory.NETWORK_ERROR,
                code="connection_lost",
                retryable=True,
            )
        if self.scenario == "rate_limit_then_ok" and self.submit_calls == 1:
            raise TrueEvalError(
                "rate limited",
                category=FailureCategory.RATE_LIMITED,
                code="http_429",
                retryable=True,
                provider_status="429",
            )
        if self.scenario == "policy_refusal":
            raise TrueEvalError(
                "policy refusal",
                category=FailureCategory.POLICY_REFUSAL,
                code="policy_refusal",
                retryable=False,
            )
        job_id = f"job-{uuid7()}"
        answer = self.answers.get(input.task_id, f"answer for {input.task_id}")
        self.jobs[job_id] = {
            "answer": answer,
            "input": input.model_dump(),
            "status": "completed" if self.scenario == "success_sync" else "queued",
        }
        submission = Submission(
            submission_id=uuid7(),
            execution_id=session.execution_id,
            idempotency_key=idempotency_key,
            external_job_id=job_id,
            channel=self._spec.channel,
            lookup_available=self._spec.submission_lookup,
        )
        self.by_idem[idempotency_key] = submission
        return submission

    async def lookup(self, idempotency_key: str) -> Submission | None:
        return self.by_idem.get(idempotency_key)

    async def poll(self, submission: Submission) -> JobStatus:
        job_id = submission.external_job_id or ""
        self.poll_counts[job_id] = self.poll_counts.get(job_id, 0) + 1
        if self.scenario == "timeout":
            return JobStatus(phase="timeout", external_job_id=job_id, message="fake timeout")
        if self.scenario == "provider_error":
            return JobStatus(phase="failed", external_job_id=job_id, retryable=False, message="boom")
        if job_id not in self.jobs:
            return JobStatus(phase="not_found", external_job_id=job_id)
        if self.poll_counts[job_id] >= self.poll_complete_after or self.scenario == "success_sync":
            self.jobs[job_id]["status"] = "completed"
            return JobStatus(phase="completed", external_job_id=job_id)
        return JobStatus(phase="running", external_job_id=job_id)

    async def collect(self, session: SessionHandle, submission: Submission) -> RawSUTResult:
        self.collect_calls += 1
        if self.scenario == "collect_fail_once" and self.collect_calls == 1:
            raise TrueEvalError(
                "collect failed once",
                category=FailureCategory.NETWORK_ERROR,
                code="collect_timeout",
                retryable=True,
            )
        job = self.jobs.get(submission.external_job_id or "")
        if job is None:
            raise TrueEvalError(
                "job missing at collect",
                category=FailureCategory.PROVIDER_ERROR,
                code="missing_job",
                retryable=False,
            )
        await asyncio.sleep(0)
        answer = str(job["answer"])
        return RawSUTResult(
            execution_id=session.execution_id,
            channel=self._spec.channel,
            final_answer=answer,
            raw_response={"answer": answer},
            search_results=[{"url": "https://example.com/source", "title": "Example"}],
            citations=[{"citation_id": "src1", "url": "https://example.com/source", "title": "Example"}],
            usage={"latency_ms": 12, "cost_usd": 0.01, "search_calls": 1, "input_tokens": 10, "output_tokens": 20},
            status="completed",
        )

    async def close(self, session: SessionHandle) -> None:
        self.closed.add(session.session_id)
