"""秘塔 AI 搜索 / 深度研究 via official Metaso Chat Completions."""

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


class MetasoResearchSUT(SyncChatResearchSUT):
    def __init__(
        self,
        *,
        sut_id: str = "metaso-research",
        provider: str = "metaso",
        product: str = "metaso-research",
        model: str = "research",
        endpoint_family: str = "metaso_chat",
        base_url: str = "https://metaso.cn/api/v1",
        chat_path: str = "/chat/completions",
        auth_env: str = "METASO_API_KEY",
        timeout_seconds: float = 180.0,
        scope: str = "webpage",
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
        self.scope = scope

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
                    "scope": self.scope,
                    "stream": False,
                    "format": "chat_completions",
                    "q": input.prompt,
                    "messages": [{"role": "user", "content": input.prompt}],
                },
                headers=auth_headers(self.auth_env),
                timeout=self.timeout_seconds,
            )
            raise_for_status(response, "metaso-research")
            body = load_json_or_text(response)
        except Exception as exc:
            raise wrap_http_error(exc, "metaso-research") from exc
        answer, citations, usage = parse_openai_completion(body)
        citations = merge_citations(
            citations,
            citations_from_items(body.get("webpages")),
            citations_from_items(body.get("sources")),
        )
        return answer, citations, usage, body
