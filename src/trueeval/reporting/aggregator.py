"""Aggregate ScoreRecords without hiding system failures or coverage."""

from __future__ import annotations

import statistics
from collections import defaultdict

from trueeval.core.ids import uuid7
from trueeval.core.schemas.artifact import ResearchAnswer
from trueeval.core.schemas.run import RunManifest, RunSummary
from trueeval.core.schemas.score import MetricSummary, ScoreRecord
from trueeval.core.schemas.task import TaskRun
from trueeval.core.state_machine.states import TaskRunState


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def _metric_summaries(scores: list[ScoreRecord]) -> list[MetricSummary]:
    by_metric: dict[str, list[ScoreRecord]] = defaultdict(list)
    for score in scores:
        by_metric[score.metric].append(score)
    out: list[MetricSummary] = []
    for metric, rows in sorted(by_metric.items()):
        usable = [r for r in rows if r.status == "scored" and r.normalized_value is not None]
        values = [float(r.normalized_value) for r in usable if r.normalized_value is not None]
        coverage = (len(usable) / len(rows)) if rows else 0.0
        out.append(
            MetricSummary(
                metric=metric,
                mean=statistics.fmean(values) if values else None,
                n=len(usable),
                coverage=coverage,
                p50=_percentile(values, 50),
                p95=_percentile(values, 95),
                variance=statistics.pvariance(values) if len(values) >= 2 else None,
            )
        )
    return out


def aggregate_run(
    manifest: RunManifest,
    tasks: list[TaskRun],
    scores: list[ScoreRecord],
    answers: list[ResearchAnswer],
) -> RunSummary:
    status_counts: dict[str, int] = {}
    for task in tasks:
        status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1
    answer_counts: dict[str, int] = {}
    latencies: list[float] = []
    tokens_in = 0.0
    tokens_out = 0.0
    searches = 0.0
    cost = 0.0
    for answer in answers:
        answer_counts[answer.status] = answer_counts.get(answer.status, 0) + 1
        if answer.usage.latency_ms is not None:
            latencies.append(float(answer.usage.latency_ms))
        tokens_in += float(answer.usage.input_tokens or 0)
        tokens_out += float(answer.usage.output_tokens or 0)
        searches += float(answer.usage.search_calls or 0)
        cost += float(answer.usage.cost_usd or 0)
    scorable = sum(1 for a in answers if a.status == "completed")
    official = [s for s in scores if s.metric.startswith("official.")]
    diagnostic = [s for s in scores if s.metric.startswith("trueeval.")]
    anomalies: list[str] = []
    if status_counts.get(TaskRunState.WAITING_EXTERNAL.value):
        anomalies.append("unknown submissions waiting for manual disposition")
    if any(s.status == "grader_error" for s in scores):
        anomalies.append("one or more graders returned GRADER_ERROR")
    selected = sorted({s.grading_job_id for s in scores})
    return RunSummary(
        run_id=manifest.run_id,
        total_tasks=len({t.task_id for t in tasks}),
        total_executions=len(tasks),
        scorable_executions=scorable,
        status_counts=status_counts,
        answer_status_counts=answer_counts,
        official_metrics=_metric_summaries(official or scores),
        trueeval_metrics=_metric_summaries(diagnostic),
        latency_ms={"p50": _percentile(latencies, 50), "p95": _percentile(latencies, 95)},
        usage={
            "input_tokens": tokens_in or None,
            "output_tokens": tokens_out or None,
            "search_calls": searches or None,
            "cost_usd": cost or None,
        },
        selected_grading_jobs=selected,
        anomalies=anomalies,
    )


def unused_id() -> str:
    return uuid7()
