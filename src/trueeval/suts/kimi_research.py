"""Kimi Research via official Moonshot Chat Completions + $web_search."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.schemas.sut import InputPackage
from trueeval.suts.research_common import (
    SyncChatResearchSUT,
    auth_headers,
    load_json_or_text,
    parse_openai_completion,
    raise_for_status,
    wrap_http_error,
)

WEB_SEARCH_TOOL = {"type": "builtin_function", "function": {"name": "$web_search"}}


class KimiResearchSUT(SyncChatResearchSUT):
    def __init__(
        self,
        *,
        sut_id: str = "kimi-research",
        provider: str = "kimi",
        product: str = "kimi-research",
        model: str = "kimi-k2.6",
        endpoint_family: str = "moonshot_chat",
        base_url: str = "https://api.moonshot.ai/v1",
        chat_path: str = "/chat/completions",
        auth_env: str = "MOONSHOT_API_KEY",
        timeout_seconds: float = 600.0,
        max_tool_rounds: int = 8,
        system_prompt: str | None = None,
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
        self.max_tool_rounds = max_tool_rounds
        self.system_prompt = system_prompt or (
            "You are a deep research assistant. Use the $web_search tool to gather "
            "evidence, then write one complete, self-contained final report that fully "
            "answers the user's request. Never reply with only a plan or an intent to "
            "search; your final message must be the full answer itself."
        )

    async def _complete(
        self,
        input: InputPackage,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": input.prompt},
        ]
        last_body: dict[str, Any] = {}
        usage: dict[str, Any] = {}
        try:
            for round_index in range(self.max_tool_rounds):
                allow_tools = round_index < self.max_tool_rounds - 1
                last_body = await self._chat(messages, use_tools=allow_tools)
                usage = last_body.get("usage") or usage
                choice = (last_body.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                tool_calls = message.get("tool_calls") or []
                if allow_tools and tool_calls:
                    messages.append(message)
                    for call in tool_calls:
                        fn = call.get("function") or {}
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id"),
                                "name": fn.get("name") or "$web_search",
                                "content": fn.get("arguments") or "{}",
                            }
                        )
                    continue
                answer, citations, parsed_usage = parse_openai_completion(last_body)
                if allow_tools and _is_deferral(answer):
                    messages.append(message or {"role": "assistant", "content": answer})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Continue now. If you still need evidence, call the "
                                "$web_search tool in this turn. Otherwise write the "
                                "complete final report in this message. Do not reply "
                                "with only a statement that you intend to search."
                            ),
                        }
                    )
                    continue
                return answer, citations, parsed_usage or usage, last_body
        except Exception as exc:
            raise wrap_http_error(exc, "kimi-research") from exc
        answer, citations, parsed_usage = parse_openai_completion(last_body)
        if answer.strip():
            return answer, citations, parsed_usage or usage, last_body
        raise TrueEvalError(
            "Kimi web search exceeded tool-call rounds",
            category=FailureCategory.PROVIDER_ERROR,
            code="tool_loop_limit",
            retryable=False,
        )

    async def _http(self) -> httpx.AsyncClient:
        # trust_env=False bypasses the OS/system proxy, which can silently drop the
        # long follow-up request that carries $web_search results (~60s cutoff).
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False)
        return self._client

    async def _chat(
        self, messages: list[dict[str, Any]], *, use_tools: bool = True
    ) -> dict[str, Any]:
        client = await self._http()
        payload: dict[str, Any] = {
            "model": self._spec.model,
            "messages": messages,
            "thinking": {"type": "disabled"},
        }
        if use_tools:
            payload["tools"] = [WEB_SEARCH_TOOL]
        headers = auth_headers(self.auth_env)
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.post(
                    self._url(self.chat_path),
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                raise_for_status(response, "kimi-research")
                return load_json_or_text(response)
            except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
                # Follow-up requests that carry web-search results occasionally get
                # dropped mid-flight (proxy/server disconnect); retry with backoff.
                last_exc = exc
                if attempt == 2:
                    break
                await asyncio.sleep(1.5 * (attempt + 1))
        raise wrap_http_error(last_exc or RuntimeError("kimi chat failed"), "kimi-research")


_DEFERRAL_MARKERS = (
    "let me search",
    "let me look",
    "let me find",
    "let me gather",
    "let me dig",
    "let me investigate",
    "let me conduct",
    "let me continue",
    "let me do",
    "conduct additional",
    "additional search",
    "additional searches",
    "more search",
    "further search",
    "need to search",
    "i need to search",
    "i need more",
    "i'll search",
    "i will search",
    "i'll look",
    "i'll gather",
    "let me research",
)


def _is_deferral(answer: str) -> bool:
    """A short message that only announces intent to search, without real content."""
    text = (answer or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return len(text) < 300 and any(marker in lowered for marker in _DEFERRAL_MARKERS)
