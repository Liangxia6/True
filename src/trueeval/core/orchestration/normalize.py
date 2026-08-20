"""Shared Research Answer normalization helpers. Adapters must not invent missing evidence."""

from __future__ import annotations

import re
from typing import Any

from trueeval.core.errors import ErrorInfo, FailureCategory
from trueeval.core.schemas.artifact import (
    ArtifactPointers,
    Citation,
    Claim,
    ResearchAnswer,
    SUTIdentity,
    Usage,
)
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.run import RunManifest
from trueeval.core.schemas.sut import RawSUTResult

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def usage_from_raw(raw: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=_as_int(raw.get("input_tokens") or raw.get("prompt_tokens")),
        output_tokens=_as_int(raw.get("output_tokens") or raw.get("completion_tokens")),
        search_calls=_as_int(raw.get("search_calls")),
        latency_ms=_as_int(raw.get("latency_ms")),
        cost_usd=_as_float(raw.get("cost_usd")),
    )


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))


def naive_claims(text: str, citations: list[Citation]) -> list[Claim]:
    if not text.strip():
        return []
    parts = [p.strip() for p in SENTENCE_RE.split(text) if p.strip()]
    cite_ids = [c.citation_id for c in citations]
    claims: list[Claim] = []
    for idx, part in enumerate(parts, start=1):
        claims.append(Claim(claim_id=f"p{idx}", text=part, citation_ids=list(cite_ids)))
    return claims


def citations_from_raw(items: list[dict[str, Any]] | None) -> list[Citation]:
    if not items:
        return []
    out: list[Citation] = []
    for idx, item in enumerate(items, start=1):
        out.append(
            Citation(
                citation_id=str(item.get("citation_id") or item.get("id") or f"src{idx}"),
                url=item.get("url"),
                title=item.get("title"),
                quoted_text=item.get("quoted_text"),
                observable=bool(item.get("url")),
            )
        )
    return out


def research_answer_from_raw(
    *,
    raw: RawSUTResult,
    task: TaskSpec,
    manifest: RunManifest,
    pointers: ArtifactPointers,
    execution_id: str,
    repeat_index: int,
) -> ResearchAnswer:
    status = _map_status(raw.status, raw.error)
    final = raw.final_answer
    citations = citations_from_raw(raw.citations)
    if not citations and isinstance(final, str):
        citations = [
            Citation(citation_id=f"src{i}", url=url, observable=True)
            for i, url in enumerate(extract_urls(final), start=1)
        ]
    claims = naive_claims(final or "", citations) if final else []
    usage = usage_from_raw(raw.usage)
    return ResearchAnswer(
        run_id=manifest.run_id,
        execution_id=execution_id,
        task_id=task.task_id,
        repeat_index=repeat_index,
        status=status,  # type: ignore[arg-type]
        final_answer=final,
        claims=claims,
        citations=citations,
        artifacts=pointers,
        usage=usage,
        sut=SUTIdentity(
            provider=manifest.sut.provider,
            product=manifest.sut.product,
            model=manifest.sut.model,
            endpoint_family=manifest.sut.endpoint_family,
            channel=manifest.sut.channel,
            parameters=dict(manifest.sut.parameters),
        ),
        error=raw.error,
        channel=manifest.sut.channel,
    )


def _map_status(raw_status: str, error: ErrorInfo | None) -> str:
    mapping = {
        "completed": "completed",
        "timeout": "timeout",
        "rate_limited": "rate_limited",
        "provider_error": "provider_error",
        "policy_refusal": "policy_refusal",
        "parse_error": "parse_error",
        "cancelled": "cancelled",
    }
    if raw_status in mapping:
        return mapping[raw_status]
    if error:
        cat = error.category
        if cat == FailureCategory.TIMEOUT:
            return "timeout"
        if cat == FailureCategory.RATE_LIMITED:
            return "rate_limited"
        if cat == FailureCategory.POLICY_REFUSAL:
            return "policy_refusal"
        if cat == FailureCategory.PARSE_ERROR:
            return "parse_error"
        if cat == FailureCategory.CANCELLED:
            return "cancelled"
        return "provider_error"
    return "provider_error"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
