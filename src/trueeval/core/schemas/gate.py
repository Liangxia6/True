"""Access & Compliance Gate records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from trueeval.core.schemas.common import VersionedModel
from trueeval.core.timeutil import utc_now

GateDecision = Literal["ALLOWED", "DENIED", "INCOMPLETE"]


class GateRecord(VersionedModel):
    schema_version: str = "trueeval.gate_record.v0.1"
    gate_id: str
    run_id: str | None = None
    decision: GateDecision
    license: str
    authorized_channel: str
    data_region: str
    retention_days: int
    allowed_outbound_fields: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = "local"
