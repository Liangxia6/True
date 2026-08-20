from __future__ import annotations

from pathlib import Path

import pytest

from trueeval.storage.artifacts import ArtifactStore, make_fernet
from trueeval.storage.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "benchmarks").mkdir()
    src = ROOT / "benchmarks" / "tiny-research"
    dest = tmp_path / "benchmarks" / "tiny-research"
    dest.mkdir()
    for name in ("benchmark.yaml", "tasks.jsonl", "gold.jsonl", "rubric.yaml"):
        dest.joinpath(name).write_bytes(src.joinpath(name).read_bytes())
    return tmp_path


@pytest.fixture
def artifacts(workspace: Path) -> ArtifactStore:
    return ArtifactStore(workspace, fernet=make_fernet("trueeval-dev-artifact-key"))


@pytest.fixture
def state(workspace: Path) -> StateStore:
    store = StateStore(workspace / "runs" / ".state.sqlite")
    yield store
    store.close()
