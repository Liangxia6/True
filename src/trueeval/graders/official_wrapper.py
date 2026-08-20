"""Call official benchmark graders through their existing adapters.

This wrapper does not replace official prompts. If the official path needs an
LLM judge and none is configured, exact-match is used instead of a homemade rubric.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from trueeval.core.errors import ErrorInfo, FailureCategory
from trueeval.core.ids import uuid7
from trueeval.core.schemas.artifact import ArtifactRef, ResearchAnswer
from trueeval.core.schemas.benchmark import TaskSpec
from trueeval.core.schemas.grader import GradeContext, GraderSpec
from trueeval.core.schemas.score import ScoreRecord
from trueeval.graders.exact_match import normalize_answer

_PROMPT_NAMES = ("JUDGE_PROMPT_CN", "JUDGE_PROMPT", "LLM_JUDGE_PROMPT")


class OfficialAccuracyGrader:
    def __init__(self, judge: object | None = None) -> None:
        self.judge = judge

    def spec(self) -> GraderSpec:
        return GraderSpec(
            grader_id="official-accuracy",
            version="0.1.0",
            kind="official",
            metrics=["official.answer_accuracy"],
            requires_gold=True,
        )

    def supports(self, artifact: ArtifactRef | ResearchAnswer, task: TaskSpec) -> bool:
        return isinstance(artifact, ResearchAnswer)

    async def grade(
        self,
        task: TaskSpec,
        artifacts: list[ResearchAnswer],
        ctx: GradeContext,
    ) -> list[ScoreRecord]:
        answer = artifacts[0]
        if answer.status != "completed":
            return [
                ScoreRecord(
                    score_id=uuid7(),
                    run_id=ctx.run_id,
                    execution_id=ctx.execution_id,
                    task_id=task.task_id,
                    repeat_index=answer.repeat_index,
                    grading_job_id=ctx.grading_job_id,
                    grader_id="official-accuracy",
                    grader_version="0.1.0",
                    metric="official.answer_accuracy",
                    coverage=0.0,
                    grader_config_hash=ctx.grader_config_hash,
                    input_artifact_hash=ctx.input_artifact_hash,
                    status="excluded",
                    rationale=f"system status {answer.status}",
                )
            ]
        gold = ctx.gold.reference_answer if ctx.gold else None
        if not gold:
            return [self._err(task, answer, ctx, "missing_gold", "gold reference_answer missing")]
        prediction = answer.final_answer or ""
        if _direct_match(prediction, gold):
            return [self._score(task, answer, ctx, 1.0, "direct match; official LLM judge not required")]
        judge = ctx.extra.get("judge") or self.judge
        if judge is None:
            value = 1.0 if normalize_answer(prediction) == normalize_answer(gold) else 0.0
            return [self._score(task, answer, ctx, value, "deterministic fallback; official judge not configured")]
        try:
            prompt = _official_prompt(task, prediction, gold)
            raw = judge.complete("you are a helpful assistant!", prompt)
            verdict = _parse_official_verdict(raw)
            if verdict is None:
                return [self._err(task, answer, ctx, "judge_unparsed", raw[:500] or "empty judge response")]
            return [self._score(task, answer, ctx, 1.0 if verdict else 0.0, raw[:500])]
        except Exception as exc:
            return [self._err(task, answer, ctx, "official_judge_failed", str(exc))]

    def _score(self, task: TaskSpec, answer: ResearchAnswer, ctx: GradeContext, value: float, why: str) -> ScoreRecord:
        return ScoreRecord(
            score_id=uuid7(),
            run_id=ctx.run_id,
            execution_id=ctx.execution_id,
            task_id=task.task_id,
            repeat_index=answer.repeat_index,
            grading_job_id=ctx.grading_job_id,
            grader_id="official-accuracy",
            grader_version="0.1.0",
            metric="official.answer_accuracy",
            raw_value=value,
            normalized_value=value,
            coverage=1.0,
            rationale=why,
            grader_config_hash=ctx.grader_config_hash,
            input_artifact_hash=ctx.input_artifact_hash,
            status="scored",
        )

    def _err(self, task: TaskSpec, answer: ResearchAnswer, ctx: GradeContext, code: str, message: str) -> ScoreRecord:
        return ScoreRecord(
            score_id=uuid7(),
            run_id=ctx.run_id,
            execution_id=ctx.execution_id,
            task_id=task.task_id,
            repeat_index=answer.repeat_index,
            grading_job_id=ctx.grading_job_id,
            grader_id="official-accuracy",
            grader_version="0.1.0",
            metric="official.answer_accuracy",
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


def _direct_match(prediction: str, gold: str) -> bool:
    extracted = prediction
    for pattern in (r"Exact Answer:\s*(.+)", r"最终答案[:：]\s*(.+)"):
        m = re.search(pattern, prediction)
        if m:
            extracted = m.group(1).strip()
            break
    return normalize_answer(extracted) == normalize_answer(gold)


def _parse_official_verdict(raw: str) -> bool | None:
    if re.search(r"correct:\s*yes", raw, re.I):
        return True
    if re.search(r"correct:\s*no", raw, re.I):
        return False
    match = re.search(r"结论[:：]\s*(正确|错误)", raw)
    if match:
        return match.group(1) == "正确"
    return None


def _official_prompt(task: TaskSpec, prediction: str, gold: str) -> str:
    prompt = _load_official_prompt_template(task.benchmark_id)
    if prompt:
        return prompt.format(question=task.input.prompt, response=prediction, correct_answer=gold)
    return (
        f"[question]: {task.input.prompt}\n[correct_answer]: {gold}\n[response]: {prediction}\n"
        "correct: yes or no"
    )


def _load_official_prompt_template(benchmark_id: str) -> str | None:
    adapters = Path("benchmarks") / benchmark_id / "adapters"
    for name in ("official_prompt.py", "official_grader.py"):
        path = adapters / name
        if not path.exists():
            continue
        found = _string_constants(path)
        for key in _PROMPT_NAMES:
            value = found.get(key)
            if value:
                return value
    return None


def _string_constants(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = _literal_str(node.value)
        if value is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = value
    return out


def _literal_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "strip":
        return _literal_str(node.func.value)
    return None
