"""Resolve SUT adapters from configuration. Secrets are not accepted from YAML."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import yaml

from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.suts.fake import FakeSUTAdapter
from trueeval.suts.http_research import HTTPResearchSUTAdapter
from trueeval.suts.kimi_research import KimiResearchSUT
from trueeval.suts.manual import ManualResearchImport
from trueeval.suts.metaso_research import MetasoResearchSUT
from trueeval.suts.qwen_deep_research import QwenDeepResearchSUT
from trueeval.suts.zhipu_qingyan import ZhipuQingyanSUT

_FACTORIES: dict[str, type] = {
    "fake-research": FakeSUTAdapter,
    "fake": FakeSUTAdapter,
    "manual-research-import": ManualResearchImport,
    "manual": ManualResearchImport,
    "http-research": HTTPResearchSUTAdapter,
    "deepseek-research-api": HTTPResearchSUTAdapter,
    "kimi-research": KimiResearchSUT,
    "kimi": KimiResearchSUT,
    "metaso-research": MetasoResearchSUT,
    "metaso": MetasoResearchSUT,
    "qwen-deep-research": QwenDeepResearchSUT,
    "qwen-research": QwenDeepResearchSUT,
    "zhipu-qingyan": ZhipuQingyanSUT,
    "zhipu-research": ZhipuQingyanSUT,
    "glm-research": ZhipuQingyanSUT,
}


def _init_kwargs(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    allowed = set(inspect.signature(cls.__init__).parameters) - {"self"}
    accepts_var = any(
        p.kind is inspect.Parameter.VAR_KEYWORD
        for p in inspect.signature(cls.__init__).parameters.values()
    )
    if accepts_var:
        return {k: v for k, v in data.items() if k not in {"schema_version", "id"}}
    return {k: v for k, v in data.items() if k in allowed}


def load_sut(sut_id: str, *, workspace: Path, parameters: dict[str, Any] | None = None) -> Any:
    path = workspace / "configs" / "suts" / f"{sut_id}.yaml"
    params = dict(parameters or {})
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "api_key" in data or "authorization" in data:
            raise TrueEvalError(
                "secrets must not appear in SUT YAML",
                category=FailureCategory.ADAPTER_ERROR,
                code="secret_in_yaml",
                retryable=False,
            )
        params = {**data, **params}
        params.pop("schema_version", None)
        params.pop("id", None)

    factory = _FACTORIES.get(sut_id)
    if factory is FakeSUTAdapter:
        return FakeSUTAdapter(**_init_kwargs(FakeSUTAdapter, params))
    if factory is ManualResearchImport:
        return ManualResearchImport()
    if factory is HTTPResearchSUTAdapter or (factory is None and path.exists()):
        if "sut_id" not in params:
            params["sut_id"] = sut_id
        return HTTPResearchSUTAdapter(**_init_kwargs(HTTPResearchSUTAdapter, params))
    if factory is not None:
        if "sut_id" not in params:
            params["sut_id"] = sut_id
        return factory(**_init_kwargs(factory, params))
    raise TrueEvalError(
        f"unknown SUT {sut_id}",
        category=FailureCategory.INVALID_ARGUMENT,
        code="unknown_sut",
        retryable=False,
    )
