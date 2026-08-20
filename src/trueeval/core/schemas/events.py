"""Event store records. Outbox is the source of truth."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from trueeval.core.schemas.common import VersionedModel
from trueeval.core.timeutil import utc_now


class EventRecord(VersionedModel):
    schema_version: str = "trueeval.event.v0.1"
    run_id: str
    event_sequence: int
    event_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
