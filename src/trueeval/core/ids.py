"""UUIDv7 and stable idempotency keys."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from uuid import UUID


def uuid7(*, clock_ms: int | None = None, random_bytes: bytes | None = None) -> str:
    """RFC 9562 UUIDv7. Clock and entropy are injectable for tests."""
    timestamp_ms = clock_ms if clock_ms is not None else int(time.time() * 1000)
    rand = random_bytes if random_bytes is not None else secrets.token_bytes(10)
    if len(rand) < 10:
        rand = rand + secrets.token_bytes(10 - len(rand))
    unix_ts_ms = timestamp_ms & 0xFFFFFFFFFFFF
    time_high = (unix_ts_ms >> 16) & 0xFFFFFFFF
    time_low = unix_ts_ms & 0xFFFF
    rand_a = int.from_bytes(rand[0:2], "big") & 0x0FFF
    rand_b = int.from_bytes(rand[2:10], "big") & 0x3FFFFFFFFFFFFFFF
    value = (time_high << 96) | (time_low << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return str(UUID(int=value))


def execution_id() -> str:
    return uuid7()


def run_id() -> str:
    return uuid7()


def grading_job_id() -> str:
    return uuid7()


def idempotency_key(
    *,
    run_id: str,
    execution_id: str,
    task_id: str,
    repeat_index: int,
    attempt: int,
    sut_id: str,
) -> str:
    """Stable key for one Attempt of one execution. Never reuse across regenerations."""
    material = "|".join(
        [
            "trueeval.idempotency.v0.1",
            run_id,
            execution_id,
            task_id,
            str(repeat_index),
            str(attempt),
            sut_id,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"te-{digest[:40]}"


def safe_path_component(value: str, *, max_len: int = 80) -> str:
    """Sanitize external IDs before they enter filesystem paths."""
    allowed = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_", "."}:
            allowed.append(ch)
        else:
            allowed.append("_")
    cleaned = "".join(allowed).strip("._") or "unnamed"
    return cleaned[:max_len]


def process_nonce() -> str:
    return secrets.token_hex(8)


def hostname_hint() -> str:
    return os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "local"
