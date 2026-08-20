"""LLM-as-judge adapters for Relevant Content and Fact Check.

The Judge is a plug-in. Official prompts stay in prompts.py. Callers must not
replace those strings with a homemade rubric.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from trueeval.cited_not_verified.prompts import (
    FACTUAL_SUPPORT_HUMAN,
    FACTUAL_SUPPORT_SYSTEM,
    SOURCE_RELEVANCE_HUMAN,
    SOURCE_RELEVANCE_SYSTEM,
)

SCORE_RE = re.compile(r"score\s*=\s*([01](?:\.0)?)", re.IGNORECASE)


class JudgeClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class MissingJudgeError(RuntimeError):
    pass


def parse_binary_score(text: str) -> tuple[int, str]:
    rationale = text.strip()
    try:
        data = json.loads(rationale)
        if isinstance(data, dict) and "score" in data:
            return (1 if float(data["score"]) >= 0.5 else 0, rationale)
    except json.JSONDecodeError:
        pass
    m = SCORE_RE.search(rationale)
    if m:
        return (1 if float(m.group(1)) >= 0.5 else 0, rationale)
    tail = re.findall(r"\b([01])\b", rationale)
    if tail:
        return int(tail[-1]), rationale
    return 0, rationale


def score_relevant_content(
    judge: JudgeClient,
    attribution_text: str,
    url: str,
    url_content: str,
) -> tuple[int, str]:
    user = SOURCE_RELEVANCE_HUMAN.format(
        attribution_text=attribution_text,
        url=url,
        url_content=url_content,
    )
    return parse_binary_score(judge.complete(SOURCE_RELEVANCE_SYSTEM, user))


def score_fact_check(
    judge: JudgeClient,
    attribution_text: str,
    url: str,
    url_content: str,
) -> tuple[int, str]:
    user = FACTUAL_SUPPORT_HUMAN.format(
        attribution_text=attribution_text,
        url=url,
        url_content=url_content,
    )
    return parse_binary_score(judge.complete(FACTUAL_SUPPORT_SYSTEM, user))


class OpenAICompatJudge:
    """Optional OpenAI-compatible client. Not an official paper model."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url or os.environ.get("TRUEEVAL_JUDGE_BASE_URL")
        self.api_key = api_key or os.environ.get("TRUEEVAL_JUDGE_API_KEY") or os.environ.get("OPENAI_API_KEY")

    def complete(self, system: str, user: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise MissingJudgeError("openai package is not installed") from exc
        if not self.api_key:
            raise MissingJudgeError("set TRUEEVAL_JUDGE_API_KEY or OPENAI_API_KEY")
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
