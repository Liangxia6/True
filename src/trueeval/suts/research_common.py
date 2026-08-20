"""Shared helpers for official Research SUT adapters.

These adapters take a benchmark prompt and return a RawSUTResult that
FileBenchmarkAdapter can normalize into research_answer.v0.1 for grading.
Secrets stay in environment variables.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from trueeval.core.errors import FailureCategory, TrueEvalError, classify_http_status
from trueeval.core.ids import uuid7
from trueeval.core.orchestration.normalize import extract_urls
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


def resolve_api_key(auth_env: str, fallbacks: list[str] | None = None) -> str:
    names = [auth_env, *(fallbacks or [])]
    for name in names:
        key = os.environ.get(name)
        if key:
            return key
    raise TrueEvalError(
        f"missing API key; set {auth_env}" + (f" or {fallbacks[0]}" if fallbacks else ""),
        category=FailureCategory.AUTH_ERROR,
        code="missing_api_key",
        retryable=False,
    )


def auth_headers(auth_env: str, fallbacks: list[str] | None = None) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {resolve_api_key(auth_env, fallbacks)}",
    }


def raise_for_status(response: httpx.Response, op: str) -> None:
    if response.status_code < 400:
        return
    category, retryable = classify_http_status(response.status_code)
    text = response.text[:500]
    if contains_secret(text):
        text = "[redacted]"
    raise TrueEvalError(
        f"{op} failed with HTTP {response.status_code}: {text}",
        category=category,
        code=f"http_{response.status_code}",
        retryable=retryable,
        provider_status=str(response.status_code),
        details={"op": op},
    )


def wrap_http_error(exc: BaseException, op: str) -> TrueEvalError:
    if isinstance(exc, TrueEvalError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return TrueEvalError(
            f"{op} timed out",
            category=FailureCategory.TIMEOUT,
            code="http_timeout",
            retryable=True,
            cause=exc,
        )
    if isinstance(exc, httpx.HTTPError):
        return TrueEvalError(
            f"{op} network error",
            category=FailureCategory.NETWORK_ERROR,
            code="http_error",
            retryable=True,
            cause=exc,
        )
    return TrueEvalError(
        f"{op} failed",
        category=FailureCategory.PROVIDER_ERROR,
        code="provider_error",
        retryable=False,
        cause=exc,
    )


def citations_from_items(items: Any) -> list[dict[str, Any]]:
    if not items:
        return []
    if isinstance(items, dict):
        items = items.get("data") or items.get("webpages") or items.get("results") or [items]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or item.get("href")
        if not url or url in seen:
            continue
        seen.add(str(url))
        out.append(
            {
                "citation_id": str(item.get("citation_id") or item.get("id") or f"src{len(out) + 1}"),
                "url": str(url),
                "title": item.get("title") or item.get("name"),
                "quoted_text": item.get("snippet") or item.get("summary") or item.get("content"),
            }
        )
        if idx >= 50:
            break
    return out


def citations_from_text(text: str) -> list[dict[str, Any]]:
    return [{"citation_id": f"src{i}", "url": url} for i, url in enumerate(extract_urls(text), start=1)]


def merge_citations(*groups: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            url = str(item.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            row = dict(item)
            row["citation_id"] = f"src{len(merged) + 1}"
            merged.append(row)
    return merged


def message_text(message: dict[str, Any] | None) -> str:
    if not message:
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return ""


def parse_openai_completion(body: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    choices = body.get("choices") or []
    message = (choices[0] or {}).get("message") if choices else {}
    answer = message_text(message if isinstance(message, dict) else None)
    if not answer:
        answer = str(body.get("answer") or body.get("output") or body.get("text") or "")
    citations = merge_citations(
        citations_from_items(body.get("citations")),
        citations_from_items(body.get("web_search")),
        citations_from_items(body.get("search_results")),
        citations_from_items(body.get("references")),
        citations_from_items(body.get("webpages")),
        citations_from_items((message or {}).get("annotations") if isinstance(message, dict) else None),
        citations_from_text(answer),
    )
    usage = body.get("usage") or {}
    return answer, citations, usage if isinstance(usage, dict) else {}


def require_answer(answer: str, op: str) -> str:
    text = (answer or "").strip()
    if not text:
        raise TrueEvalError(
            f"{op} returned an empty answer",
            category=FailureCategory.PARSE_ERROR,
            code="empty_answer",
            retryable=False,
        )
    return text


class SyncChatResearchSUT:
    """Synchronous research SUT: submit stores the collected answer for poll/collect."""

    def __init__(
        self,
        *,
        sut_id: str,
        provider: str,
        product: str,
        model: str,
        endpoint_family: str,
        base_url: str,
        auth_env: str,
        timeout_seconds: float = 120.0,
        provider_idempotency: bool = False,
        submission_lookup: bool = False,
        client: httpx.AsyncClient | None = None,
        estimated_cost_usd: float = 1.0,
    ) -> None:
        self._spec = SUTSpec(
            sut_id=sut_id,
            provider=provider,
            product=product,
            model=model,
            endpoint_family=endpoint_family,
            channel="API_SYNC",
            provider_idempotency=provider_idempotency,
            submission_lookup=submission_lookup,
            estimated_cost_usd=estimated_cost_usd,
        )
        self.base_url = base_url.rstrip("/")
        self.auth_env = auth_env
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._results: dict[str, RawSUTResult] = {}
        self._by_idem: dict[str, Submission] = {}

    def spec(self) -> SUTSpec:
        return self._spec

    async def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            provider_idempotency=self._spec.provider_idempotency,
            submission_lookup=self._spec.submission_lookup,
            web_search=True,
            citations=True,
            search_results=True,
            sync=True,
        )

    async def start_session(self, task: TaskSpec, ctx: RunContext) -> SessionHandle:
        return SessionHandle(
            session_id=uuid7(),
            execution_id=str(ctx.extra.get("execution_id") or uuid7()),
        )

    async def submit(
        self,
        session: SessionHandle,
        input: InputPackage,
        idempotency_key: str,
    ) -> Submission:
        if idempotency_key in self._by_idem and self._spec.provider_idempotency:
            return self._by_idem[idempotency_key]
        started = time.perf_counter()
        answer, citations, usage, raw = await self._complete(input)
        usage = dict(usage)
        usage.setdefault("latency_ms", int((time.perf_counter() - started) * 1000))
        job_id = uuid7()
        self._results[job_id] = RawSUTResult(
            execution_id=session.execution_id,
            channel="API_SYNC",
            final_answer=require_answer(answer, self._spec.sut_id),
            raw_response=raw,
            citations=citations or None,
            search_results=citations or None,
            usage=usage,
            status="completed",
        )
        submission = Submission(
            submission_id=uuid7(),
            execution_id=session.execution_id,
            idempotency_key=idempotency_key,
            external_job_id=job_id,
            channel="API_SYNC",
            lookup_available=self._spec.submission_lookup,
        )
        self._by_idem[idempotency_key] = submission
        return submission

    async def lookup(self, idempotency_key: str) -> Submission | None:
        return self._by_idem.get(idempotency_key)

    async def poll(self, submission: Submission) -> JobStatus:
        job_id = submission.external_job_id or ""
        if job_id in self._results:
            return JobStatus(phase="completed", external_job_id=job_id)
        return JobStatus(phase="not_found", external_job_id=job_id)

    async def collect(self, session: SessionHandle, submission: Submission) -> RawSUTResult:
        result = self._results.get(submission.external_job_id or "")
        if result is None:
            raise TrueEvalError(
                "result missing at collect",
                category=FailureCategory.PROVIDER_ERROR,
                code="missing_result",
                retryable=False,
            )
        return result.model_copy(update={"execution_id": session.execution_id})

    async def close(self, session: SessionHandle) -> None:
        session.metadata["closed"] = True

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def _complete(
        self,
        input: InputPackage,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        raise NotImplementedError

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path


def load_json_or_text(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise TrueEvalError(
            "provider returned non-JSON",
            category=FailureCategory.PARSE_ERROR,
            code="invalid_json",
            retryable=False,
            cause=exc,
        ) from exc
    if not isinstance(body, dict):
        raise TrueEvalError(
            "provider JSON must be an object",
            category=FailureCategory.PARSE_ERROR,
            code="invalid_json_object",
            retryable=False,
        )
    return body
