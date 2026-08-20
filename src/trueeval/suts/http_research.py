"""Configurable HTTP Research SUT (sync or async poll). Secrets stay in env vars."""

from __future__ import annotations

import os

import httpx

from trueeval.core.errors import FailureCategory, TrueEvalError, classify_http_status
from trueeval.core.ids import uuid7
from trueeval.core.protocols import RunContext
from trueeval.core.redact import contains_secret
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

DEFAULT_STATUS_MAP = {
    "queued": "waiting",
    "pending": "waiting",
    "running": "running",
    "in_progress": "running",
    "succeeded": "completed",
    "success": "completed",
    "completed": "completed",
    "failed": "failed",
    "error": "failed",
    "timeout": "timeout",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "not_found": "not_found",
}


class HTTPResearchSUTAdapter:
    """Generic Research Agent API.

    Configuration is injected; API keys are read from the environment at call time
    and never written into artifacts.
    """

    def __init__(
        self,
        *,
        sut_id: str = "http-research",
        provider: str = "generic",
        product: str = "research-api",
        model: str = "pinned-model-id",
        endpoint_family: str = "http_json",
        channel: str = "API_ASYNC",
        base_url: str | None = None,
        submit_path: str = "/v1/research/jobs",
        poll_path: str = "/v1/research/jobs/{job_id}",
        collect_path: str = "/v1/research/jobs/{job_id}/result",
        lookup_path: str | None = "/v1/research/jobs?idempotency_key={idempotency_key}",
        idempotency_header: str = "Idempotency-Key",
        auth_env: str = "TRUEEVAL_SUT_API_KEY",
        timeout_seconds: float = 60.0,
        provider_idempotency: bool = True,
        submission_lookup: bool = True,
        status_map: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._spec = SUTSpec(
            sut_id=sut_id,
            provider=provider,
            product=product,
            model=model,
            endpoint_family=endpoint_family,
            channel=channel,  # type: ignore[arg-type]
            provider_idempotency=provider_idempotency,
            submission_lookup=submission_lookup,
        )
        self.base_url = (base_url or os.environ.get("TRUEEVAL_SUT_BASE_URL") or "").rstrip("/")
        self.submit_path = submit_path
        self.poll_path = poll_path
        self.collect_path = collect_path
        self.lookup_path = lookup_path
        self.idempotency_header = idempotency_header
        self.auth_env = auth_env
        self.timeout_seconds = timeout_seconds
        self.status_map = {**DEFAULT_STATUS_MAP, **(status_map or {})}
        self._client = client
        self._owns_client = client is None

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
        client = await self._http()
        payload = {
            "model": self._spec.model,
            "prompt": input.prompt,
            "language": input.language,
            "as_of": input.as_of,
            "constraints": input.constraints,
        }
        try:
            response = await client.post(
                self._url(self.submit_path),
                json=payload,
                headers=self._headers(idempotency_key),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TrueEvalError(
                "submit timed out",
                category=FailureCategory.TIMEOUT,
                code="http_timeout",
                retryable=True,
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise TrueEvalError(
                "submit network error",
                category=FailureCategory.NETWORK_ERROR,
                code="http_error",
                retryable=True,
                cause=exc,
            ) from exc
        self._raise_for_status(response, "submit")
        body = response.json()
        job_id = body.get("id") or body.get("job_id") or body.get("external_job_id")
        if self._spec.channel == "API_SYNC":
            session.metadata["sync_result"] = body
        return Submission(
            submission_id=uuid7(),
            execution_id=session.execution_id,
            idempotency_key=idempotency_key,
            external_job_id=None if job_id is None else str(job_id),
            channel=self._spec.channel,
            lookup_available=self._spec.submission_lookup,
        )

    async def lookup(self, idempotency_key: str) -> Submission | None:
        if not self.lookup_path:
            return None
        client = await self._http()
        path = self.lookup_path.format(idempotency_key=idempotency_key)
        try:
            response = await client.get(self._url(path), headers=self._headers(), timeout=self.timeout_seconds)
        except httpx.HTTPError:
            return None
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            return None
        body = response.json()
        item = body[0] if isinstance(body, list) and body else body
        job_id = item.get("id") or item.get("job_id")
        if not job_id:
            return None
        return Submission(
            submission_id=uuid7(),
            execution_id="unknown",
            idempotency_key=idempotency_key,
            external_job_id=str(job_id),
            channel=self._spec.channel,
            lookup_available=True,
        )

    async def poll(self, submission: Submission) -> JobStatus:
        if self._spec.channel == "API_SYNC":
            return JobStatus(phase="completed", external_job_id=submission.external_job_id)
        if not submission.external_job_id:
            return JobStatus(phase="unknown", message="missing external job id")
        client = await self._http()
        path = self.poll_path.format(job_id=submission.external_job_id)
        try:
            response = await client.get(self._url(path), headers=self._headers(), timeout=self.timeout_seconds)
        except httpx.TimeoutException as exc:
            raise TrueEvalError(
                "poll timed out",
                category=FailureCategory.TIMEOUT,
                code="http_timeout",
                retryable=True,
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise TrueEvalError(
                "poll network error",
                category=FailureCategory.NETWORK_ERROR,
                code="http_error",
                retryable=True,
                cause=exc,
            ) from exc
        if response.status_code == 404:
            return JobStatus(phase="not_found", external_job_id=submission.external_job_id)
        self._raise_for_status(response, "poll")
        body = response.json()
        raw_status = str(body.get("status") or body.get("state") or "unknown").lower()
        phase = self.status_map.get(raw_status, "unknown")
        return JobStatus(
            phase=phase,  # type: ignore[arg-type]
            external_job_id=submission.external_job_id,
            retryable=phase in {"waiting", "running", "unknown"},
            provider_status=raw_status,
            raw=body if isinstance(body, dict) else {},
        )

    async def collect(self, session: SessionHandle, submission: Submission) -> RawSUTResult:
        if session.metadata.get("sync_result"):
            body = session.metadata["sync_result"]
        else:
            client = await self._http()
            path = self.collect_path.format(job_id=submission.external_job_id or "")
            try:
                response = await client.get(self._url(path), headers=self._headers(), timeout=self.timeout_seconds)
            except httpx.HTTPError as exc:
                raise TrueEvalError(
                    "collect network error",
                    category=FailureCategory.NETWORK_ERROR,
                    code="http_error",
                    retryable=True,
                    cause=exc,
                ) from exc
            self._raise_for_status(response, "collect")
            body = response.json()
        text = body.get("final_answer") or body.get("answer") or body.get("output") or body.get("content")
        if isinstance(text, dict):
            text = text.get("text")
        return RawSUTResult(
            execution_id=session.execution_id,
            channel=self._spec.channel,
            final_answer=str(text) if text is not None else None,
            raw_response=body,
            search_results=body.get("search_results"),
            citations=body.get("citations"),
            trajectory=body.get("trajectory"),
            usage=body.get("usage") or {},
            status="completed",
        )

    async def close(self, session: SessionHandle) -> None:
        session.metadata["closed"] = True

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not self.base_url:
            raise TrueEvalError(
                "TRUEEVAL_SUT_BASE_URL is not set",
                category=FailureCategory.INVALID_ARGUMENT,
                code="missing_base_url",
                retryable=False,
            )
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        key = os.environ.get(self.auth_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if idempotency_key:
            headers[self.idempotency_header] = idempotency_key
        return headers

    def _raise_for_status(self, response: httpx.Response, op: str) -> None:
        if response.status_code < 400:
            return
        category, retryable = classify_http_status(response.status_code)
        text = response.text[:500]
        if contains_secret(text):
            text = "[redacted]"
        raise TrueEvalError(
            f"{op} failed with HTTP {response.status_code}",
            category=category,
            code=f"http_{response.status_code}",
            retryable=retryable,
            provider_status=str(response.status_code),
            details={"op": op},
        )
