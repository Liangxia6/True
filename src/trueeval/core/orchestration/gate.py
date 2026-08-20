"""Access & Compliance Gate. DENIED or incomplete information blocks submission."""

from __future__ import annotations

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.ids import uuid7
from trueeval.core.schemas.benchmark import BenchmarkSpec
from trueeval.core.schemas.config import RunConfig
from trueeval.core.schemas.gate import GateRecord


def evaluate_gate(config: RunConfig, benchmark: BenchmarkSpec) -> GateRecord:
    reasons: list[str] = []
    license_text = benchmark.upstream.license.strip()
    if not license_text or license_text.lower() in {"unknown", "unspecified"}:
        reasons.append("benchmark license is missing")
    if config.gate.data_region in {"", "unspecified"}:
        reasons.append("data_region is unspecified")
    if config.gate.authorized_channel not in {"api", "manual_import", "authorized_web"}:
        reasons.append(f"unauthorized channel {config.gate.authorized_channel}")
    if not config.gate.allow_decrypt_upload and config.sut.channel != "MANUAL_IMPORT":
        # decrypt upload is blocked by default; API path is allowed if license exists
        pass
    if config.gate.allow_decrypt_upload:
        reasons.append("decrypt test set upload to uncontrolled services is forbidden")

    decision: str
    if any(r.startswith("decrypt") for r in reasons):
        decision = "DENIED"
    elif reasons:
        decision = "INCOMPLETE"
    else:
        decision = "ALLOWED"

    outbound = ["input.prompt", "input.language", "input.as_of"]
    if config.gate.allow_pii_outbound:
        outbound.append("attachments")

    return GateRecord(
        gate_id=uuid7(),
        decision=decision,  # type: ignore[arg-type]
        license=license_text or "missing",
        authorized_channel=config.gate.authorized_channel,
        data_region=config.gate.data_region,
        retention_days=config.retention.artifact_days,
        allowed_outbound_fields=outbound,
        reasons=reasons,
        created_by=config.gate.operator,
    )


def assert_gate_allows(record: GateRecord) -> None:
    if record.decision != "ALLOWED":
        raise TrueEvalError(
            f"access gate {record.decision}: {'; '.join(record.reasons) or 'blocked'}",
            category=FailureCategory.GATE_DENIED,
            code="gate_denied",
            retryable=False,
            details={"decision": record.decision, "reasons": record.reasons},
        )
