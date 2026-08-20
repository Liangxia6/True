"""Secret and PII redaction before logs, evaluation artifacts, and reports."""

from __future__ import annotations

import re
from typing import Any

SECRET_ENV_KEYS = {
    "TRUEEVAL_SUT_API_KEY",
    "TRUEEVAL_JUDGE_API_KEY",
    "TRUEEVAL_ARTIFACT_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "API_KEY",
    "AUTHORIZATION",
}

KEY_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|authorization|bearer|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d[\d\-\s]{8,}\d)\b")


def redact_text(text: str, extra_secrets: list[str] | None = None) -> str:
    out = text
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(secret, "[REDACTED]")
    for pattern in KEY_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    out = EMAIL_RE.sub("[REDACTED_EMAIL]", out)
    return out


def contains_secret(text: str, extra_secrets: list[str] | None = None) -> bool:
    for secret in extra_secrets or []:
        if secret and secret in text:
            return True
    return any(p.search(text) for p in KEY_PATTERNS)


def redact_mapping(value: Any, extra_secrets: list[str] | None = None) -> Any:
    if isinstance(value, str):
        return redact_text(value, extra_secrets)
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in {"authorization", "api_key", "apikey", "token", "password", "secret"}:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_mapping(item, extra_secrets)
        return redacted
    if isinstance(value, list):
        return [redact_mapping(item, extra_secrets) for item in value]
    return value
