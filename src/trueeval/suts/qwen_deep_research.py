"""千问深入研究 via DashScope HTTP SSE (qwen-deep-research)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.schemas.sut import InputPackage
from trueeval.suts.research_common import (
    SyncChatResearchSUT,
    auth_headers,
    citations_from_items,
    citations_from_text,
    merge_citations,
    raise_for_status,
    wrap_http_error,
)


class QwenDeepResearchSUT(SyncChatResearchSUT):
    def __init__(
        self,
        *,
        sut_id: str = "qwen-deep-research",
        provider: str = "qwen",
        product: str = "qwen-deep-research",
        model: str = "qwen-deep-research",
        endpoint_family: str = "dashscope_generation",
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        generate_path: str = "/services/aigc/text-generation/generation",
        auth_env: str = "DASHSCOPE_API_KEY",
        timeout_seconds: float = 900.0,
        enable_feedback: bool = False,
        client: httpx.AsyncClient | None = None,
        **_: Any,
    ) -> None:
        super().__init__(
            sut_id=sut_id,
            provider=provider,
            product=product,
            model=model,
            endpoint_family=endpoint_family,
            base_url=base_url,
            auth_env=auth_env,
            timeout_seconds=timeout_seconds,
            estimated_cost_usd=2.0,
            client=client,
        )
        self.generate_path = generate_path
        self.enable_feedback = enable_feedback

    async def _complete(
        self,
        input: InputPackage,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        headers = auth_headers(self.auth_env, ["ALIYUN_API_KEY"])
        headers["X-DashScope-SSE"] = "enable"
        payload = {
            "model": self._spec.model,
            "input": {"messages": [{"role": "user", "content": input.prompt}]},
            "parameters": {"enable_feedback": self.enable_feedback},
        }
        try:
            client = await self._http()
            async with client.stream(
                "POST",
                self._url(self.generate_path),
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            ) as response:
                raise_for_status(response, "qwen-deep-research")
                return await self._read_sse(response)
        except Exception as exc:
            raise wrap_http_error(exc, "qwen-deep-research") from exc

    async def _read_sse(
        self,
        response: httpx.Response,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        answer = ""
        citations: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        last_body: dict[str, Any] = {}
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            last_body = event
            if event.get("code") and event.get("status_code", 200) not in {200, None}:
                raise TrueEvalError(
                    str(event.get("message") or event.get("code")),
                    category=FailureCategory.PROVIDER_ERROR,
                    code=str(event.get("code")),
                    retryable=False,
                )
            output = event.get("output") or {}
            message = output.get("message") or {}
            phase = str(message.get("phase") or "")
            content = message.get("content") or output.get("text") or ""
            extra = message.get("extra") or output.get("extra") or {}
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            citations = merge_citations(
                citations,
                citations_from_items(extra.get("references") if isinstance(extra, dict) else None),
                citations_from_items(extra.get("web_sites") if isinstance(extra, dict) else None),
                citations_from_items(output.get("references")),
            )
            if phase in {"", "answer"} and isinstance(content, str) and content.strip():
                answer = content
        if not answer and isinstance(last_body.get("output"), dict):
            message = last_body["output"].get("message") or {}
            answer = str(message.get("content") or "")
        citations = merge_citations(citations, citations_from_text(answer))
        return answer, citations, usage, last_body
