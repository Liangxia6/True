"""TrueEval CLI. Human text is the default; --json emits structured output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import typer
import yaml

from trueeval import __version__
from trueeval.app import build_service, load_local_env, workspace_root
from trueeval.benchmarks.registry import load_benchmark
from trueeval.cli import exit_codes
from trueeval.core.errors import FailureCategory, TrueEvalError
from trueeval.core.logging import configure_logging
from trueeval.core.schemas.config import RunConfig
from trueeval.core.schemas.manual import ManualImportPackage
from trueeval.suts.manual import ManualResearchImport
from trueeval.suts.registry import load_sut

app = typer.Typer(no_args_is_help=True, add_completion=False)
run_app = typer.Typer(no_args_is_help=True)
import_app = typer.Typer(no_args_is_help=True)
grade_app = typer.Typer(no_args_is_help=True)
report_app = typer.Typer(no_args_is_help=True)
benchmark_app = typer.Typer(no_args_is_help=True)
sut_app = typer.Typer(no_args_is_help=True)
artifact_app = typer.Typer(no_args_is_help=True)

app.add_typer(run_app, name="run")
app.add_typer(import_app, name="import")
app.add_typer(grade_app, name="grade")
app.add_typer(report_app, name="report")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(sut_app, name="sut")
app.add_typer(artifact_app, name="artifact")


def _emit(data: Any, *, as_json: bool, human: str) -> None:
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        typer.echo(human)


def _load_config(path: Path) -> RunConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return RunConfig.model_validate(data)


def _fail(exc: TrueEvalError) -> None:
    payload = exc.to_info().model_dump()
    typer.echo(json.dumps(payload, ensure_ascii=False), err=True)
    if exc.category == FailureCategory.GATE_DENIED:
        raise typer.Exit(exit_codes.GATE_DENIED)
    if exc.category == FailureCategory.BUDGET_EXCEEDED:
        raise typer.Exit(exit_codes.BUDGET)
    if exc.info.code in {"run_not_found", "unknown_benchmark", "unknown_sut"}:
        raise typer.Exit(exit_codes.NOT_FOUND)
    if exc.category == FailureCategory.INVALID_ARGUMENT:
        raise typer.Exit(exit_codes.VALIDATION)
    raise typer.Exit(exit_codes.ERROR)


@app.callback()
def _root(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Structured JSON on stdout"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    configure_logging(level="DEBUG" if verbose else "INFO")
    load_local_env()
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


@app.command("version")
def version() -> None:
    typer.echo(__version__)


@benchmark_app.command("validate")
def benchmark_validate(benchmark_id: str) -> None:
    try:
        adapter = load_benchmark(benchmark_id, workspace=workspace_root())
        spec = adapter.spec()
        splits = {s.name: len(adapter.load_tasks(s.name)) for s in spec.splits} or {
            "default": len(adapter.load_tasks("test"))
        }
        _emit(
            {"benchmark_id": spec.benchmark_id, "version": spec.benchmark_version, "splits": splits},
            as_json=click.get_current_context().obj.get("json", False),
            human=f"{spec.benchmark_id} ok splits={splits}",
        )
    except TrueEvalError as exc:
        _fail(exc)


@sut_app.command("validate")
def sut_validate(sut_id: str) -> None:
    try:
        adapter = load_sut(sut_id, workspace=workspace_root())
        spec = adapter.spec() if hasattr(adapter, "spec") else adapter.spec()
        data = spec.model_dump() if hasattr(spec, "model_dump") else {"sut_id": sut_id}
        _emit(data, as_json=click.get_current_context().obj.get("json", False), human=f"{sut_id} ok")
    except TrueEvalError as exc:
        _fail(exc)


@run_app.command("plan")
def run_plan(config: Path = typer.Option(..., "--config", exists=True)) -> None:
    try:
        cfg = _load_config(config)
        service = build_service(cfg)
        plan = service.plan(cfg)
        service.state.close()
        _emit(
            plan,
            as_json=True,
            human=json.dumps(plan, ensure_ascii=False, indent=2),
        )
    except TrueEvalError as exc:
        _fail(exc)


@run_app.command("start")
def run_start(
    config: Path = typer.Option(..., "--config", exists=True),
    yes: bool = typer.Option(False, "--yes", help="Skip paid-operation confirmation"),
) -> None:
    try:
        cfg = _load_config(config)
        service = build_service(cfg)
        plan = service.plan(cfg)
        typer.echo(json.dumps(plan, ensure_ascii=False, indent=2))
        if not yes and not typer.confirm("Submit paid or long-running SUT tasks?", default=False):
            raise typer.Exit(exit_codes.SUCCESS)
        manifest = service.create(cfg)
        import asyncio

        result = asyncio.run(service.start(manifest.run_id))
        service.build_report(manifest.run_id)
        service.state.close()
        _emit(result, as_json=True, human=f"run {manifest.run_id} {result['status']}")
    except TrueEvalError as exc:
        _fail(exc)


@run_app.command("resume")
def run_resume(run_id: str) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        import asyncio

        result = asyncio.run(service.resume(run_id))
        service.build_report(run_id)
        service.state.close()
        _emit(result, as_json=True, human=f"resumed {run_id} {result['status']}")
    except TrueEvalError as exc:
        _fail(exc)


@run_app.command("status")
def run_status(run_id: str) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        result = service.status(run_id)
        service.state.close()
        _emit(result, as_json=True, human=json.dumps(result, indent=2))
    except TrueEvalError as exc:
        _fail(exc)


@run_app.command("cancel")
def run_cancel(run_id: str, yes: bool = typer.Option(False, "--yes")) -> None:
    if not yes and not typer.confirm(f"Cancel run {run_id}?", default=False):
        raise typer.Exit(exit_codes.SUCCESS)
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        service.cancel(run_id)
        service.state.close()
        _emit({"run_id": run_id, "status": "cancelled"}, as_json=True, human=f"cancelled {run_id}")
    except TrueEvalError as exc:
        _fail(exc)


@import_app.command("validate")
def import_validate(run_id: str = typer.Option(..., "--run"), package: Path = typer.Option(..., "--package", exists=True)) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        payload = yaml.safe_load(package.read_text(encoding="utf-8")) if package.suffix in {".yaml", ".yml"} else json.loads(package.read_text(encoding="utf-8"))
        pkg = ManualImportPackage.model_validate(payload)
        tasks = {t.task_id: t for t in service.load_tasks(run_id)}
        if pkg.task_id not in tasks:
            raise TrueEvalError(
                f"task {pkg.task_id} not in run",
                category=FailureCategory.INVALID_ARGUMENT,
                code="unknown_task",
                retryable=False,
            )
        result = ManualResearchImport().validate_package(pkg, tasks[pkg.task_id])
        service.state.close()
        _emit(result.model_dump(), as_json=True, human="ok" if result.ok else "invalid")
        if not result.ok:
            raise typer.Exit(exit_codes.VALIDATION)
    except TrueEvalError as exc:
        _fail(exc)


@import_app.command("apply")
def import_apply(run_id: str = typer.Option(..., "--run"), package: Path = typer.Option(..., "--package", exists=True)) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        payload = json.loads(package.read_text(encoding="utf-8"))
        pkg = ManualImportPackage.model_validate(payload)
        tasks = {t.task_id: t for t in service.load_tasks(run_id)}
        task = tasks[pkg.task_id]
        importer = ManualResearchImport()
        result = importer.validate_package(pkg, task)
        if not result.ok:
            _emit(result.model_dump(), as_json=True, human="invalid package")
            raise typer.Exit(exit_codes.VALIDATION)
        raw = importer.collect(pkg, task)
        execution = None
        for item in service.state.list_task_runs(run_id):
            if item.task_id == pkg.task_id and (pkg.execution_id in {None, item.execution_id}):
                execution = item
                break
        if execution is None:
            raise TrueEvalError("no matching execution for import", category=FailureCategory.INVALID_ARGUMENT, code="missing_execution", retryable=False)
        from trueeval.core.orchestration.grader_router import GraderRouter
        from trueeval.core.orchestration.rate_limit import CapacityPool
        from trueeval.core.orchestration.runner import ExecutionRunner
        from trueeval.storage.events import EventProjector

        manifest = service.load_manifest(run_id)
        runner = ExecutionRunner(
            manifest=manifest,
            state=service.state,
            artifacts=service.artifacts,
            projector=EventProjector(service.state, service.artifacts),
            benchmark=service.benchmark,
            sut=service.sut,  # type: ignore[arg-type]
            graders=GraderRouter(service.graders, state=service.state, artifacts=service.artifacts),
            grader_specs=service._resolve_graders_from_manifest(manifest),
            pool=CapacityPool(),
            tasks=tasks,
        )
        raw.execution_id = execution.execution_id
        runner.apply_import(execution.execution_id, raw)
        import asyncio

        asyncio.run(runner.finish_imported(execution.execution_id))
        service.build_report(run_id)
        service.state.close()
        _emit({"run_id": run_id, "execution_id": execution.execution_id}, as_json=True, human="imported")
    except TrueEvalError as exc:
        _fail(exc)


@grade_app.command("run")
def grade_run(run_id: str, grader: str | None = typer.Option(None, "--grader")) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        import asyncio

        jobs = asyncio.run(service.grade_only(run_id, grader))
        service.build_report(run_id)
        service.state.close()
        _emit({"grading_jobs": jobs}, as_json=True, human=f"regraded {len(jobs)} jobs")
    except TrueEvalError as exc:
        _fail(exc)


@report_app.command("build")
def report_build(run_id: str) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        path = service.build_report(run_id)
        service.state.close()
        _emit({"report": str(path)}, as_json=True, human=str(path))
    except TrueEvalError as exc:
        _fail(exc)


@artifact_app.command("verify")
def artifact_verify(run_id: str) -> None:
    try:
        cfg = _resume_config(run_id)
        service = build_service(cfg)
        errors = service.artifacts.verify_run(run_id)
        service.state.close()
        ok = not errors
        _emit({"ok": ok, "errors": errors}, as_json=True, human="ok" if ok else "\n".join(errors))
        if not ok:
            raise typer.Exit(exit_codes.VALIDATION)
    except TrueEvalError as exc:
        _fail(exc)


def _resume_config(run_id: str) -> RunConfig:
    root = workspace_root()
    manifest_path = root / "runs" / run_id / "manifest.json"
    if not manifest_path.exists():
        raise TrueEvalError(
            f"run {run_id} not found",
            category=FailureCategory.INVALID_ARGUMENT,
            code="run_not_found",
            retryable=False,
        )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    resolved = data.get("resolved_config") or {}
    if resolved:
        return RunConfig.model_validate(resolved)
    return RunConfig.model_validate(
        {
            "benchmark": {"id": data["benchmark"]["benchmark_id"], "split": data["benchmark"]["split"]},
            "sut": {"id": data["sut"]["sut_id"], "model": data["sut"]["model"]},
            "workspace": str(root),
        }
    )


if __name__ == "__main__":
    app()
