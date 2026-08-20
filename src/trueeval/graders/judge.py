"""OpenAI-compatible chat judge. Official prompts stay in benchmark adapters."""

from __future__ import annotations

from typing import Any

import httpx

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.schemas.config import GradingConfig
from trueeval.suts.research_common import auth_headers, load_json_or_text, raise_for_status

_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "auth_env": "MOONSHOT_API_KEY",
        "auth_fallbacks": ["TRUEEVAL_JUDGE_API_KEY"],
        "default_model": "kimi-k2.6",
        "omit_temperature": True,
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    "moonshot": {
        "base_url": "https://api.moonshot.ai/v1",
        "auth_env": "MOONSHOT_API_KEY",
        "auth_fallbacks": ["TRUEEVAL_JUDGE_API_KEY"],
        "default_model": "kimi-k2.6",
        "omit_temperature": True,
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "auth_env": "TRUEEVAL_JUDGE_API_KEY",
        "auth_fallbacks": ["OPENAI_API_KEY"],
        "default_model": "gpt-4o-mini",
        "omit_temperature": False,
        "extra_body": {},
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "auth_env": "DEEPSEEK_API_KEY",
        "auth_fallbacks": ["TRUEEVAL_JUDGE_API_KEY"],
        "default_model": "deepseek-v4-pro",
        "omit_temperature": False,
        "extra_body": {"thinking": {"type": "disabled"}},
    },
}


class HttpChatJudge:
    """Minimal chat-completions client that matches JudgeClient.complete()."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        auth_env: str,
        auth_fallbacks: list[str] | None = None,
        omit_temperature: bool = False,
        extra_body: dict[str, Any] | None = None,
        timeout_seconds: float = 180.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.auth_env = auth_env
        self.auth_fallbacks = auth_fallbacks or []
        self.omit_temperature = omit_temperature
        self.extra_body = extra_body or {}
        self.timeout_seconds = timeout_seconds
        self._client = client

    def complete(self, system: str, user: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if not self.omit_temperature:
            payload["temperature"] = 0
        payload.update(self.extra_body)
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close = self._client is None
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=auth_headers(self.auth_env, self.auth_fallbacks),
            )
            raise_for_status(response, "llm-judge")
            body = load_json_or_text(response)
        except TrueEvalError:
            raise
        except Exception as exc:
            raise TrueEvalError(
                "llm-judge request failed",
                category=FailureCategory.GRADER_ERROR,
                code="judge_http_error",
                retryable=True,
                cause=exc,
            ) from exc
        finally:
            if close:
                client.close()
        choices = body.get("choices") if isinstance(body, dict) else None
        message = (choices or [{}])[0].get("message") or {}
        return str(message.get("content") or "")


def build_judge(config: GradingConfig, *, client: httpx.Client | None = None) -> HttpChatJudge | None:
    if not config.judge_provider and not config.judge_model:
        return None
    provider = (config.judge_provider or "kimi").strip().lower()
    preset = _PROVIDER_PRESETS.get(provider)
    if preset is None:
        raise TrueEvalError(
            f"unknown judge_provider {config.judge_provider}",
            category=FailureCategory.INVALID_ARGUMENT,
            code="unknown_judge_provider",
            retryable=False,
        )
    return HttpChatJudge(
        model=config.judge_model or str(preset["default_model"]),
        base_url=str(preset["base_url"]),
        auth_env=str(preset["auth_env"]),
        auth_fallbacks=list(preset["auth_fallbacks"]),
        omit_temperature=bool(preset["omit_temperature"]),
        extra_body=dict(preset["extra_body"]),
        client=client,
    )
