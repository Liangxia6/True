"""智谱清言 / GLM 联网问答 via official Web Search in Chat."""

from __future__ import annotations

from typing import Any

import httpx

from trueeval.core.schemas.sut import InputPackage
from trueeval.suts.research_common import (
    SyncChatResearchSUT,
    auth_headers,
    citations_from_items,
    load_json_or_text,
    merge_citations,
    parse_openai_completion,
    raise_for_status,
    wrap_http_error,
)


class ZhipuQingyanSUT(SyncChatResearchSUT):
    def __init__(
        self,
        *,
        sut_id: str = "zhipu-qingyan",
        provider: str = "zhipu",
        product: str = "zhipu-qingyan",
        model: str = "glm-4-plus",
        endpoint_family: str = "zhipu_chat",
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        chat_path: str = "/chat/completions",
        auth_env: str = "ZHIPU_API_KEY",
        timeout_seconds: float = 180.0,
        search_engine: str = "search_pro",
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
            client=client,
        )
        self.chat_path = chat_path
        self.search_engine = search_engine

    async def _complete(
        self,
        input: InputPackage,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        try:
            client = await self._http()
            response = await client.post(
                self._url(self.chat_path),
                json={
                    "model": self._spec.model,
                    "messages": [{"role": "user", "content": input.prompt}],
                    "temperature": 0.1,
                    "tools": [
                        {
                            "type": "web_search",
                            "web_search": {
                                "enable": True,
                                "search_engine": self.search_engine,
                                "search_result": True,
                            },
                        }
                    ],
                },
                headers=auth_headers(self.auth_env),
                timeout=self.timeout_seconds,
            )
            raise_for_status(response, "zhipu-qingyan")
            body = load_json_or_text(response)
        except Exception as exc:
            raise wrap_http_error(exc, "zhipu-qingyan") from exc
        answer, citations, usage = parse_openai_completion(body)
        citations = merge_citations(
            citations,
            citations_from_items(body.get("web_search")),
            citations_from_items(body.get("search_result") or body.get("search_results")),
        )
        return answer, citations, usage, body
