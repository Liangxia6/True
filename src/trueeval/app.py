"""Compose a RunService from a workspace and run config."""

from __future__ import annotations

import os
from pathlib import Path

from trueeval.benchmarks.registry import load_benchmark
from trueeval.core.orchestration.run_service import RunService
from trueeval.core.schemas.config import RunConfig
from trueeval.graders.judge import build_judge
from trueeval.graders.registry import default_graders
from trueeval.storage.artifacts import ArtifactStore, make_fernet
from trueeval.storage.state import StateStore
from trueeval.suts.registry import load_sut


def workspace_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return Path(os.environ.get("TRUEEVAL_WORKSPACE", ".")).resolve()


def load_local_env(root: Path | None = None) -> Path | None:
    """Load gitignored `.env` from the workspace. Existing process env wins."""
    path = (root or workspace_root()) / ".env"
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return path


def build_service(config: RunConfig, *, workspace: Path | None = None) -> RunService:
    root = workspace or workspace_root(config.workspace)
    load_local_env(root)
    artifacts = ArtifactStore(
        root,
        fernet=make_fernet(os.environ.get("TRUEEVAL_ARTIFACT_KEY") or "trueeval-dev-artifact-key"),
        extra_secrets=_secret_values(),
    )
    state = StateStore(root / "runs" / ".state.sqlite")
    benchmark = load_benchmark(config.benchmark.id, workspace=root)
    sut_params = dict(config.sut.parameters)
    if config.sut.model:
        sut_params.setdefault("model", config.sut.model)
    if config.sut.channel:
        sut_params.setdefault("channel", config.sut.channel)
    sut = load_sut(config.sut.id, workspace=root, parameters=sut_params)
    graders = default_graders(
        fetch_citations=config.grading.fetch_citations,
        judge=build_judge(config.grading),
    )
    return RunService(
        workspace=root,
        state=state,
        artifacts=artifacts,
        benchmark=benchmark,
        sut=sut,
        graders=graders,
        code_commit_sha=os.environ.get("TRUEEVAL_CODE_SHA"),
    )


def _secret_values() -> list[str]:
    names = [
        "TRUEEVAL_SUT_API_KEY",
        "TRUEEVAL_JUDGE_API_KEY",
        "TRUEEVAL_ARTIFACT_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
        "METASO_API_KEY",
        "DASHSCOPE_API_KEY",
        "ALIYUN_API_KEY",
        "ZHIPU_API_KEY",
    ]
    return [os.environ[n] for n in names if os.environ.get(n)]
