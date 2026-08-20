"""Official DeepResearchEval point-wise quality grader.

Uses official prompts and the official hierarchical scoring algorithm.
Does not score citations or factuality.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from trueeval.core.errors import ErrorInfo, FailureCategory
from trueeval.core.ids import uuid7
from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.score import ScoreRecord

_PROMPTS: dict[str, Any] | None = None
_JSON_TAG = re.compile(r"<json_output>\s*(.*?)\s*</json_output>", re.DOTALL)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _load_prompts() -> dict[str, Any]:
    global _PROMPTS
    if _PROMPTS is not None:
        return _PROMPTS
    path = Path("benchmarks/deepresearcheval/adapters/official_prompts.py")
    ns: dict[str, Any] = {}
    exec(path.read_text(encoding="utf-8"), ns)
    _PROMPTS = ns
    return ns


def dim_key(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def extract_json(text: str) -> Any:
    if not text:
        return None
    tagged = _JSON_TAG.search(text)
    candidates = [tagged.group(1).strip()] if tagged else []
    candidates.extend(block.strip() for block in _CODE_FENCE.findall(text))
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        candidates.append(stripped)
    for raw in candidates:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def default_weights(extra: list[dict[str, Any]]) -> dict[str, float]:
    names = ["coverage", "insight", "instruction_following", "clarity"]
    names.extend(dim_key(str(item.get("meta_dimension_name") or "")) for item in extra)
    names = [name for name in names if name]
    share = 1.0 / len(names)
    return {name: share for name in names}


def hierarchical_total(
    scores: dict[str, list[dict[str, Any]]],
    criteria: dict[str, list[dict[str, Any]]],
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    dim_totals: dict[str, float] = {}
    total = 0.0
    for name, items in criteria.items():
        rows = scores.get(name) or []
        weighted = 0.0
        weight_sum = 0.0
        by_criterion = {str(row.get("criterion")): row for row in rows if isinstance(row, dict)}
        for item in items:
            hit = by_criterion.get(str(item.get("criterion")))
            if not hit:
                continue
            try:
                value = float(hit.get("report_score_0_to_10"))
                weight = float(item.get("weight") or 0)
            except (TypeError, ValueError):
                continue
            weighted += value * weight
            weight_sum += weight
        dim_score = (weighted / weight_sum) if weight_sum else 0.0
        dim_totals[name] = dim_score
        total += dim_score * float(weights.get(name) or 0)
    return total, dim_totals


class OfficialQualityGrader:
    def __init__(self, judge: object | None = None, cache_dir: Path | None = None) -> None:
        self.judge = judge
        self.cache_dir = cache_dir or Path(".trueeval") / "dre_quality_cache"

    def spec(self) -> GraderSpec:
        return GraderSpec(
            grader_id="official-quality",
            version="0.1.0",
            kind="official",
            metrics=["official.quality_score"],
            prompt_id="deepresearcheval.point_quality",
            requires_network=True,
        )

    def supports(self, artifact: ArtifactRef | ResearchAnswer, task: TaskSpec) -> bool:
        return isinstance(artifact, ResearchAnswer) and task.benchmark_id == "deepresearcheval"

    async def grade(
        self,
        task: TaskSpec,
        artifacts: list[ResearchAnswer],
        ctx: GradeContext,
    ) -> list[ScoreRecord]:
        answer = artifacts[0]
        if answer.status != "completed" or not (answer.final_answer or "").strip():
            return [
                ScoreRecord(
                    score_id=uuid7(),
                    run_id=ctx.run_id,
                    execution_id=ctx.execution_id,
                    task_id=task.task_id,
                    repeat_index=answer.repeat_index,
                    grading_job_id=ctx.grading_job_id,
                    grader_id="official-quality",
                    grader_version="0.1.0",
                    metric="official.quality_score",
                    coverage=0.0,
                    grader_config_hash=ctx.grader_config_hash,
                    input_artifact_hash=ctx.input_artifact_hash,
                    status="excluded",
                    rationale=f"system status {answer.status}",
                )
            ]
        judge = ctx.extra.get("judge") or self.judge
        if judge is None:
            return [self._err(task, answer, ctx, "missing_judge", "official quality judge is not configured")]
        try:
            raw, rationale = self._score_report(task.input.prompt, answer.final_answer or "", task.task_id, judge)
        except Exception as exc:
            return [self._err(task, answer, ctx, "official_quality_failed", str(exc))]
        return [
            ScoreRecord(
                score_id=uuid7(),
                run_id=ctx.run_id,
                execution_id=ctx.execution_id,
                task_id=task.task_id,
                repeat_index=answer.repeat_index,
                grading_job_id=ctx.grading_job_id,
                grader_id="official-quality",
                grader_version="0.1.0",
                metric="official.quality_score",
                raw_value=raw,
                normalized_value=max(0.0, min(1.0, raw / 10.0)),
                coverage=1.0,
                rationale=rationale[:1500],
                grader_config_hash=ctx.grader_config_hash,
                input_artifact_hash=ctx.input_artifact_hash,
                status="scored",
            )
        ]

    def _score_report(self, task_prompt: str, report: str, task_id: str, judge: object) -> tuple[float, str]:
        prompts = _load_prompts()
        frozen = self._load_frozen(task_id)
        extra = frozen.get("additional_dimensions")
        if extra is None:
            extra = self._ask_json(
                judge,
                prompts["DIMENSION_GENERATION_PROMPT"].format(task_prompt=task_prompt),
                default=[],
            )
            if not isinstance(extra, list):
                extra = []
            extra = [item for item in extra if isinstance(item, dict) and item.get("meta_dimension_name")][:3]
            frozen["additional_dimensions"] = extra

        weights = frozen.get("weights")
        if not isinstance(weights, dict):
            parsed = self._ask_json(
                judge,
                prompts["WEIGHT_GENERATION_PROMPT"].format(
                    task_prompt=task_prompt,
                    additional_dimensions_json=json.dumps(extra, ensure_ascii=False, indent=2),
                ),
                default=None,
            )
            weights = {dim_key(str(k)): float(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
            if not weights:
                weights = default_weights(extra)
            total = sum(weights.values())
            if total > 0:
                weights = {k: v / total for k, v in weights.items()}
            frozen["weights"] = weights

        all_dims = {name: definition for name, definition in prompts["FIXED_DIMENSIONS"]}
        for item in extra:
            all_dims[str(item["meta_dimension_name"])] = str(item.get("definition") or "")
        meta = "\n".join(f"- **{name}**: {definition}" for name, definition in all_dims.items())

        criteria = frozen.get("criteria")
        if not isinstance(criteria, dict):
            criteria = {}
            for name in all_dims:
                parsed = self._ask_json(
                    judge,
                    prompts["CRITERIA_GENERATION_PROMPT"].format(
                        task_prompt=task_prompt,
                        num_dimensions=len(all_dims),
                        meta_dimensions=meta,
                        dimension_name=name,
                    ),
                    default=None,
                )
                rows = parsed if isinstance(parsed, list) else []
                cleaned = []
                for row in rows:
                    if isinstance(row, dict) and row.get("criterion"):
                        cleaned.append(
                            {
                                "criterion": str(row["criterion"]),
                                "explanation": str(row.get("explanation") or ""),
                                "weight": float(row.get("weight") or 0),
                            }
                        )
                if not cleaned:
                    cleaned = [
                        {
                            "criterion": f"General {name} assessment",
                            "explanation": f"Overall assessment of {name} quality",
                            "weight": 1.0,
                        }
                    ]
                weight_sum = sum(item["weight"] for item in cleaned) or 1.0
                for item in cleaned:
                    item["weight"] = item["weight"] / weight_sum
                criteria[dim_key(name)] = cleaned
            frozen["criteria"] = criteria
        self._save_frozen(task_id, frozen)

        scores: dict[str, list[dict[str, Any]]] = {}
        for name, rows in criteria.items():
            payload = [{"criterion": item["criterion"], "explanation": item["explanation"]} for item in rows]
            parsed = self._ask_json(
                judge,
                prompts["SCORING_PROMPT"].format(
                    task_prompt=task_prompt,
                    report=report,
                    criteria_of_one_dimension_json=json.dumps(payload, ensure_ascii=False, indent=2),
                ),
                default=[],
            )
            scores[name] = parsed if isinstance(parsed, list) else []

        total, dim_totals = hierarchical_total(scores, criteria, weights)
        rationale = json.dumps(
            {"total_weighted_score": round(total, 4), "dimension_scores": dim_totals, "weights": weights},
            ensure_ascii=False,
        )
        return float(total), rationale

    def _ask_json(self, judge: object, prompt: str, default: Any) -> Any:
        raw = judge.complete("", prompt)  # type: ignore[attr-defined]
        parsed = extract_json(raw)
        return default if parsed is None else parsed

    def _cache_path(self, task_id: str) -> Path:
        return self.cache_dir / f"{task_id}.json"

    def _load_frozen(self, task_id: str) -> dict[str, Any]:
        path = self._cache_path(task_id)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save_frozen(self, task_id: str, payload: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(task_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _err(self, task: TaskSpec, answer: ResearchAnswer, ctx: GradeContext, code: str, message: str) -> ScoreRecord:
        return ScoreRecord(
            score_id=uuid7(),
            run_id=ctx.run_id,
            execution_id=ctx.execution_id,
            task_id=task.task_id,
            repeat_index=answer.repeat_index,
            grading_job_id=ctx.grading_job_id,
            grader_id="official-quality",
            grader_version="0.1.0",
            metric="official.quality_score",
            grader_config_hash=ctx.grader_config_hash,
            input_artifact_hash=ctx.input_artifact_hash,
            status="grader_error",
            error=ErrorInfo(
                category=FailureCategory.GRADER_ERROR,
                code=code,
                message=message,
                retryable=False,
            ),
        )
