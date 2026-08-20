"""Structured JSONL logging. Secrets never enter log records."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from trueeval.core.redact import redact_mapping


class JsonlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", record.funcName),
            "run_id": getattr(record, "run_id", None),
            "task_id": getattr(record, "task_id", None),
            "execution_id": getattr(record, "execution_id", None),
            "attempt": getattr(record, "attempt", None),
            "provider": getattr(record, "provider", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "error_category": getattr(record, "error_category", None),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        payload = {k: v for k, v in payload.items() if v is not None}
        return json.dumps(redact_mapping(payload), ensure_ascii=False, sort_keys=True)


def configure_logging(*, level: str = "INFO", stream: Any | None = None) -> logging.Logger:
    logger = logging.getLogger("trueeval")
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(JsonlFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"trueeval.{component}")


def bind(
    logger: logging.Logger,
    **fields: Any,
) -> logging.LoggerAdapter[logging.Logger]:
    return logging.LoggerAdapter(logger, fields)


class ContextAdapter(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        extra = kwargs.setdefault("extra", {})
        extra.update(self.extra)
        extra.setdefault("component", self.extra.get("component"))
        return msg, kwargs
