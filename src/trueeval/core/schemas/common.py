"""Shared schema primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trueeval.core.timeutil import parse_iso, to_iso


class StrictModel(BaseModel):
    """All core models forbid unknown fields unless a compatibility policy is set."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CompatibleModel(BaseModel):
    """Readers may keep unknown fields for forward-compatible artifacts."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


def utc_field() -> Any:
    return Field(json_schema_extra={"format": "date-time"})


class UtcDateTime(datetime):
    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
        return handler(datetime)


def normalize_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        return parse_iso(value)
    if value.tzinfo is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    return value


class VersionedModel(StrictModel):
    schema_version: str

    @field_validator("schema_version")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("schema_version is required")
        return value


def dump_canonical(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump(mode="json")
    return _sort(data)


def _sort(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sort(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_sort(v) for v in value]
    if isinstance(value, datetime):
        return to_iso(value)
    return value
