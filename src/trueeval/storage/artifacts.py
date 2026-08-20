"""Immutable filesystem Artifact Store with atomic write and SHA-256."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.hashing import canonical_json, sha256_bytes, sha256_file
from trueeval.core.ids import safe_path_component
from trueeval.core.paths import assert_inside, execution_artifact_dir, run_dir, score_dir
from trueeval.core.redact import redact_mapping
from trueeval.core.schemas.artifact import ArtifactKind, ArtifactRef


class ArtifactStore:
    """Local filesystem store. Interface is storage-agnostic for a future object store."""

    def __init__(
        self,
        root: Path,
        *,
        fernet: Fernet | None = None,
        extra_secrets: list[str] | None = None,
    ) -> None:
        self.root = Path(root)
        self._fernet = fernet
        self._secrets = extra_secrets or []

    def run_path(self, run_id: str) -> Path:
        path = run_dir(self.root, run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(
        self,
        relative: str,
        payload: Mapping[str, Any] | list[Any] | dict[str, Any],
        *,
        kind: ArtifactKind,
        protected: bool = False,
        source_sha256: str | None = None,
        overwrite: bool = False,
    ) -> ArtifactRef:
        text = canonical_json(payload) + "\n"
        data = text.encode("utf-8")
        return self.write_bytes(
            relative,
            data,
            kind=kind,
            media_type="application/json",
            protected=protected,
            source_sha256=source_sha256,
            overwrite=overwrite,
        )

    def write_text(
        self,
        relative: str,
        text: str,
        *,
        kind: ArtifactKind,
        media_type: str = "text/plain",
        protected: bool = False,
        overwrite: bool = False,
    ) -> ArtifactRef:
        return self.write_bytes(
            relative,
            text.encode("utf-8"),
            kind=kind,
            media_type=media_type,
            protected=protected,
            overwrite=overwrite,
        )

    def write_bytes(
        self,
        relative: str,
        data: bytes,
        *,
        kind: ArtifactKind,
        media_type: str,
        protected: bool = False,
        source_sha256: str | None = None,
        overwrite: bool = False,
    ) -> ArtifactRef:
        dest = assert_inside(self.root, self.root / relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256_bytes(data)
        if dest.exists():
            existing = sha256_file(dest) if not protected or self._fernet is None else None
            if not overwrite:
                if existing == digest:
                    return ArtifactRef(
                        uri=self.uri_for(dest),
                        sha256=digest,
                        kind=kind,
                        media_type=media_type,
                        bytes=dest.stat().st_size,
                        protected=protected,
                        source_sha256=source_sha256,
                    )
                if existing is not None:
                    raise TrueEvalError(
                        "refusing to overwrite artifact with different content",
                        category=FailureCategory.STORAGE_ERROR,
                        code="artifact_overwrite",
                        retryable=False,
                        details={"path": str(dest)},
                    )
        to_write = data
        if protected:
            if self._fernet is None:
                raise TrueEvalError(
                    "protected artifact key is not configured",
                    category=FailureCategory.STORAGE_ERROR,
                    code="missing_artifact_key",
                    retryable=False,
                )
            to_write = self._fernet.encrypt(data)
        _atomic_write(dest, to_write)
        return ArtifactRef(
            uri=self.uri_for(dest),
            sha256=digest,
            kind=kind,
            media_type=media_type,
            bytes=len(to_write),
            protected=protected,
            source_sha256=source_sha256,
        )

    def write_jsonl(self, relative: str, rows: list[Mapping[str, Any]], *, overwrite: bool = False) -> Path:
        dest = assert_inside(self.root, self.root / relative)
        if dest.exists() and not overwrite:
            return dest
        lines = "".join(canonical_json(row) + "\n" for row in rows)
        _atomic_write(dest, lines.encode("utf-8"))
        return dest

    def append_jsonl(self, relative: str, row: Mapping[str, Any]) -> None:
        dest = assert_inside(self.root, self.root / relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        line = canonical_json(row) + "\n"
        with dest.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def read_json(self, uri_or_path: str, *, protected: bool = False) -> Any:
        path = self.resolve(uri_or_path)
        data = path.read_bytes()
        if protected:
            if self._fernet is None:
                raise TrueEvalError(
                    "cannot decrypt protected artifact",
                    category=FailureCategory.STORAGE_ERROR,
                    code="missing_artifact_key",
                    retryable=False,
                )
            try:
                data = self._fernet.decrypt(data)
            except InvalidToken as exc:
                raise TrueEvalError(
                    "protected artifact decrypt failed",
                    category=FailureCategory.STORAGE_ERROR,
                    code="decrypt_failed",
                    retryable=False,
                    cause=exc,
                ) from exc
        return json.loads(data.decode("utf-8"))

    def read_text(self, uri_or_path: str) -> str:
        return self.resolve(uri_or_path).read_text(encoding="utf-8")

    def resolve(self, uri_or_path: str) -> Path:
        if uri_or_path.startswith("artifact://"):
            relative = uri_or_path.removeprefix("artifact://")
            return assert_inside(self.root, self.root / relative)
        return assert_inside(self.root, Path(uri_or_path) if Path(uri_or_path).is_absolute() else self.root / uri_or_path)

    def uri_for(self, path: Path) -> str:
        relative = assert_inside(self.root, path).relative_to(self.root.resolve()).as_posix()
        return f"artifact://{relative}"

    def execution_dir(self, run_id: str, execution_id: str) -> Path:
        path = execution_artifact_dir(self.root, run_id, execution_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "protected").mkdir(exist_ok=True)
        (path / "evaluation").mkdir(exist_ok=True)
        return path

    def scores_dir(self, run_id: str, grading_job_id: str) -> Path:
        path = score_dir(self.root, run_id, grading_job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def relative(self, run_id: str, *parts: str) -> str:
        cleaned = [safe_path_component(run_id, max_len=80), *[safe_path_component(p, max_len=120) if "/" not in p else p for p in parts]]
        return str(Path("runs", *cleaned)).replace("\\", "/")

    def write_evaluation_json(
        self,
        run_id: str,
        execution_id: str,
        name: str,
        payload: Mapping[str, Any],
        *,
        kind: ArtifactKind,
        source_sha256: str | None = None,
    ) -> ArtifactRef:
        redacted = redact_mapping(payload, self._secrets)
        rel = (
            f"runs/{safe_path_component(run_id)}/artifacts/"
            f"{safe_path_component(execution_id)}/evaluation/{name}"
        )
        return self.write_json(rel, redacted, kind=kind, source_sha256=source_sha256)

    def write_protected(
        self,
        run_id: str,
        execution_id: str,
        name: str,
        payload: Mapping[str, Any] | bytes | str,
        *,
        kind: ArtifactKind,
    ) -> ArtifactRef:
        rel = (
            f"runs/{safe_path_component(run_id)}/artifacts/"
            f"{safe_path_component(execution_id)}/protected/{name}"
        )
        if isinstance(payload, bytes):
            data = payload
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = (canonical_json(payload) + "\n").encode("utf-8")
        return self.write_bytes(
            rel,
            data,
            kind=kind,
            media_type="application/octet-stream",
            protected=True,
        )

    def verify_run(self, run_id: str) -> list[str]:
        errors: list[str] = []
        base = self.run_path(run_id)
        manifest = base / "manifest.json"
        if not manifest.exists():
            errors.append("missing manifest.json")
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "protected" in path.parts:
                continue
            if path.suffix in {".json", ".jsonl", ".md"}:
                try:
                    if path.suffix == ".json":
                        json.loads(path.read_text(encoding="utf-8"))
                    elif path.suffix == ".jsonl":
                        for line in path.read_text(encoding="utf-8").splitlines():
                            if line.strip():
                                json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid json {path}: {exc}")
        return errors


def make_fernet(key: str | None) -> Fernet | None:
    if not key:
        return None
    raw = key.encode("utf-8")
    if len(raw) == 44 and raw.endswith(b"="):
        return Fernet(raw)
    import base64
    import hashlib

    digest = hashlib.sha256(raw).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _atomic_write(dest: Path, data: bytes) -> None:
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
