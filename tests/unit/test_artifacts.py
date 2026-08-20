from __future__ import annotations

from pathlib import Path

import pytest

from trueeval.core.errors import TrueEvalError
from trueeval.storage.artifacts import ArtifactStore, make_fernet


def test_atomic_json_and_hash(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, fernet=make_fernet("k"))
    ref = store.write_json("runs/r1/hello.json", {"b": 2, "a": 1}, kind="input")
    assert ref.sha256.startswith("sha256:")
    again = store.write_json("runs/r1/hello.json", {"b": 2, "a": 1}, kind="input")
    assert again.sha256 == ref.sha256
    with pytest.raises(TrueEvalError):
        store.write_json("runs/r1/hello.json", {"b": 3, "a": 1}, kind="input")


def test_protected_roundtrip(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path, fernet=make_fernet("k"))
    ref = store.write_protected("r1", "e1", "raw_response.enc", {"secret": "value"}, kind="raw_response")
    assert ref.protected
    data = store.read_json(ref.uri, protected=True)
    assert data["secret"] == "value"


def test_path_component_rejects_external_id_separators() -> None:
    from trueeval.core.ids import safe_path_component

    assert safe_path_component("ab/cd") == "ab_cd"
