"""Load TrueEval V0.1 benchmark directories and normalize SUT output."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from trueeval.core.errors import FailureCategory, SchemaVersionError, TrueEvalError
from trueeval.core.hashing import sha256_json
from trueeval.core.orchestration.normalize import research_answer_from_raw
from trueeval.core.protocols import RunContext
from trueeval.core.schemas.artifact import ArtifactPointers, ResearchAnswer
from trueeval.core.schemas.benchmark import BenchmarkSpec, GoldRecord, TaskSpec
from trueeval.core.schemas.common import dump_canonical
from trueeval.core.schemas.grader import GraderSpec
from trueeval.core.schemas.run import RunSummary
from trueeval.core.schemas.score import ScoreRecord
from trueeval.core.schemas.sut import InputPackage, RawSUTResult

SUPPORTED_BENCHMARK = ("trueeval.research_benchmark.v0.1",)
SUPPORTED_TASK = ("trueeval.research_task.v0.1",)


class FileBenchmarkAdapter:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._spec = self._load_spec()
        self._tasks: dict[str, list[TaskSpec]] = {}
        self._gold: dict[str, GoldRecord] = {}
        self._load_gold()

    def spec(self) -> BenchmarkSpec:
        return self._spec

    def load_tasks(self, split: str) -> list[TaskSpec]:
        if split in self._tasks:
            return list(self._tasks[split])
        path = self.root / "tasks.jsonl"
        if not path.exists():
            self._tasks[split] = []
            return []
        tasks: list[TaskSpec] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            version = data.get("schema_version")
            if version not in SUPPORTED_TASK:
                raise SchemaVersionError(str(version), list(SUPPORTED_TASK))
            task = TaskSpec.model_validate(data)
            if task.split == split:
                if "gold" in data or "reference_answer" in data:
                    raise TrueEvalError(
                        f"task {task.task_id} contains gold fields",
                        category=FailureCategory.PARSE_ERROR,
                        code="gold_in_tasks",
                        retryable=False,
                    )
                tasks.append(task)
        tasks.sort(key=lambda t: t.task_id)
        self._tasks[split] = tasks
        return list(tasks)

    def load_gold(self, task_id: str) -> GoldRecord | None:
        return self._gold.get(task_id)

    def build_input(self, task: TaskSpec, ctx: RunContext) -> InputPackage:
        payload = {
            "task_id": task.task_id,
            "prompt": task.input.prompt,
            "language": task.input.language,
            "as_of": task.input.as_of,
            "constraints": dump_canonical(task.constraints),
            "attachments": list(task.input.attachments),
        }
        return InputPackage(
            task_id=task.task_id,
            prompt=task.input.prompt,
            language=task.input.language,
            as_of=task.input.as_of,
            constraints=payload["constraints"],
            attachments=list(task.input.attachments),
            input_hash=sha256_json(payload),
        )

    def normalize(self, raw: RawSUTResult, task: TaskSpec, ctx: RunContext) -> ResearchAnswer:
        repeat = 0
        if ctx.extra.get("repeat_index") is not None:
            repeat = int(ctx.extra["repeat_index"])  # type: ignore[arg-type]
        return research_answer_from_raw(
            raw=raw,
            task=task,
            manifest=ctx.manifest,
            pointers=ArtifactPointers(),
            execution_id=raw.execution_id,
            repeat_index=repeat,
        )

    def required_graders(self) -> list[GraderSpec]:
        rubric = self.root / "rubric.yaml"
        graders: list[GraderSpec] = [
            GraderSpec(
                grader_id="format-completeness",
                version="0.1.0",
                kind="hard",
                metrics=["trueeval.format_completeness"],
            )
        ]
        if not rubric.exists():
            graders.append(
                GraderSpec(
                    grader_id="exact-match",
                    version="0.1.0",
                    kind="official",
                    metrics=["official.answer_accuracy"],
                    requires_gold=True,
                )
            )
            return graders
        data = yaml.safe_load(rubric.read_text(encoding="utf-8")) or {}
        for metric in data.get("metrics") or []:
            metric_id = metric.get("metric_id", "")
            method = metric.get("method", "")
            if metric_id == "official.quality_score":
                graders.append(
                    GraderSpec(
                        grader_id="official-quality",
                        version="0.1.0",
                        kind="official",
                        metrics=[metric_id],
                        config={"adapter": metric.get("adapter"), "method": method},
                    )
                )
            if metric_id == "official.answer_accuracy" and method in {
                "exact_match",
                "upstream_executable",
            }:
                graders.append(
                    GraderSpec(
                        grader_id="exact-match" if method == "exact_match" else "official-accuracy",
                        version="0.1.0",
                        kind="official",
                        metrics=[metric_id],
                        requires_gold=True,
                        config={"adapter": metric.get("adapter"), "method": method},
                    )
                )
            if metric_id in {"official.link_works", "official.relevant_content", "official.fact_check"}:
                if not any(g.grader_id == "cited-not-verified" for g in graders):
                    graders.append(
                        GraderSpec(
                            grader_id="cited-not-verified",
                            version="0.1.0",
                            kind="citation",
                            metrics=[
                                "official.link_works",
                                "official.relevant_content",
                                "official.fact_check",
                            ],
                            requires_network=True,
                            config={"fuse_scores": False},
                        )
                    )
        if not any(g.kind == "official" for g in graders):
            graders.append(
                GraderSpec(
                    grader_id="exact-match",
                    version="0.1.0",
                    kind="official",
                    metrics=["official.answer_accuracy"],
                    requires_gold=True,
                )
            )
        return graders

    def required_capabilities(self) -> list[str]:
        return list(self._spec.default_execution.allowed_tools)

    def aggregate(self, scores: list[ScoreRecord]) -> RunSummary:
        return RunSummary(
            run_id="unbound",
            total_tasks=0,
            total_executions=0,
            scorable_executions=0,
        )

    def _load_spec(self) -> BenchmarkSpec:
        path = self.root / "benchmark.yaml"
        if not path.exists():
            raise TrueEvalError(
                f"missing benchmark.yaml in {self.root}",
                category=FailureCategory.INVALID_ARGUMENT,
                code="missing_benchmark",
                retryable=False,
            )
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        version = data.get("schema_version")
        if version not in SUPPORTED_BENCHMARK:
            raise SchemaVersionError(str(version), list(SUPPORTED_BENCHMARK))
        # Drop unknown top-level keys that are documentation-only.
        allowed = set(BenchmarkSpec.model_fields)
        cleaned = {k: v for k, v in data.items() if k in allowed}
        spec = BenchmarkSpec.model_validate(cleaned)
        spec.root_dir = str(self.root)
        return spec

    def _load_gold(self) -> None:
        path = self.root / "gold.jsonl"
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            allowed = set(GoldRecord.model_fields)
            record = GoldRecord.model_validate({k: v for k, v in data.items() if k in allowed})
            self._gold[record.task_id] = record
