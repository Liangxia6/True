"""Write summary.json and report.md. Gold answers never appear in reports."""

from __future__ import annotations

from pathlib import Path

from trueeval.core.hashing import canonical_json
from trueeval.core.schemas.common import dump_canonical
from trueeval.core.schemas.run import RunManifest, RunSummary
from trueeval.core.schemas.score import ScoreRecord
from trueeval.core.schemas.task import TaskRun
from trueeval.storage.artifacts import ArtifactStore


def write_report(
    artifacts: ArtifactStore,
    manifest: RunManifest,
    summary: RunSummary,
    tasks: list[TaskRun],
    scores: list[ScoreRecord],
) -> Path:
    run_id = manifest.run_id
    artifacts.write_json(f"runs/{run_id}/summary.json", dump_canonical(summary), kind="grader_output", overwrite=True)
    lines = [
        f"# TrueEval Run {run_id}",
        "",
        f"- Benchmark: `{manifest.benchmark.benchmark_id}` / `{manifest.benchmark.split}`",
        f"- SUT: `{manifest.sut.sut_id}` `{manifest.sut.model}` channel=`{manifest.sut.channel}`",
        f"- Executions: {summary.total_executions} (tasks={summary.total_tasks}, repeats={manifest.execution.repeats})",
        f"- Scorable completed answers: {summary.scorable_executions}",
        "",
        "## Execution status",
        "",
    ]
    for key, value in sorted(summary.status_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Answer status (not the same as wrong answers)", ""]
    if summary.answer_status_counts:
        for key, value in sorted(summary.answer_status_counts.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- (no answer artifacts)")
    lines += ["", "## Official metrics", ""]
    for metric in summary.official_metrics:
        lines.append(
            f"- `{metric.metric}`: mean={metric.mean} n={metric.n} coverage={metric.coverage:.3f}"
        )
    lines += ["", "## TrueEval diagnostics", ""]
    if summary.trueeval_metrics:
        for metric in summary.trueeval_metrics:
            lines.append(
                f"- `{metric.metric}`: mean={metric.mean} n={metric.n} coverage={metric.coverage:.3f}"
            )
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Latency and cost",
        "",
        f"- latency_ms p50/p95: {summary.latency_ms.get('p50')} / {summary.latency_ms.get('p95')}",
        f"- usage: {canonical_json(summary.usage)}",
        "",
        "## Anomalies",
        "",
    ]
    if summary.anomalies:
        for item in summary.anomalies:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Evidence",
        "",
        f"- Manifest: `runs/{run_id}/manifest.json`",
        f"- Events: `runs/{run_id}/events.jsonl`",
        f"- Selected grading jobs: {', '.join(summary.selected_grading_jobs) or 'none'}",
        f"- Task runs: {len(tasks)}; score rows: {len(scores)}",
        "",
        "System failures and coverage are first-class. Averages alone are not a leaderboard.",
        "",
    ]
    artifacts.write_text(
        f"runs/{run_id}/report.md",
        "\n".join(lines),
        kind="report",
        media_type="text/markdown",
        overwrite=True,
    )
    return artifacts.run_path(run_id) / "report.md"
