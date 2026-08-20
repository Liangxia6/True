from __future__ import annotations

from trueeval.core.schemas.artifact import ResearchAnswer, SUTIdentity
from trueeval.core.schemas.benchmark import TaskInput, TaskSpec
from trueeval.core.schemas.grader import GradeContext
from trueeval.graders.deepresearch_quality import (
    OfficialQualityGrader,
    default_weights,
    extract_json,
    hierarchical_total,
)


def test_extract_json_from_official_tag() -> None:
    raw = "note\n<json_output>\n[{\"meta_dimension_name\": \"Policy Fit\", \"definition\": \"x\"}]\n</json_output>"
    parsed = extract_json(raw)
    assert parsed[0]["meta_dimension_name"] == "Policy Fit"


def test_hierarchical_total() -> None:
    criteria = {
        "coverage": [{"criterion": "a", "weight": 1.0}],
        "insight": [{"criterion": "b", "weight": 1.0}],
    }
    scores = {
        "coverage": [{"criterion": "a", "report_score_0_to_10": 8}],
        "insight": [{"criterion": "b", "report_score_0_to_10": 6}],
    }
    total, dims = hierarchical_total(scores, criteria, {"coverage": 0.5, "insight": 0.5})
    assert dims["coverage"] == 8
    assert dims["insight"] == 6
    assert total == 7


class _ScriptedJudge:
    def __init__(self) -> None:
        self.n = 0

    def complete(self, system: str, user: str) -> str:
        self.n += 1
        if "additional same-level" in user:
            return '<json_output>[{"meta_dimension_name":"Policy Fit","definition":"policy"}]</json_output>'
        if "assign **dynamic" in user or "final weights" in user:
            return '<json_output>{"coverage":0.25,"insight":0.25,"instruction_following":0.25,"clarity":0.25}</json_output>'
        if "generate task-specific evaluation criteria" in user:
            return '<json_output>[{"criterion":"c1","explanation":"e","weight":1.0}]</json_output>'
        return '<json_output>[{"criterion":"c1","analysis":"ok","report_score_0_to_10":7.0}]</json_output>'


async def test_official_quality_with_scripted_judge(tmp_path) -> None:
    grader = OfficialQualityGrader(judge=_ScriptedJudge(), cache_dir=tmp_path)
    task = TaskSpec(
        task_id="deepresearcheval.v1.000001",
        benchmark_id="deepresearcheval",
        upstream_task_id="1",
        split="v1",
        input=TaskInput(prompt="Assess semiconductor export controls."),
    )
    answer = ResearchAnswer(
        run_id="r",
        execution_id="e",
        task_id=task.task_id,
        status="completed",
        final_answer="A short research-style paragraph about export controls and supply chains.",
        channel="API_SYNC",
        sut=SUTIdentity(
            provider="kimi",
            product="kimi-research",
            model="kimi-k2.6",
            endpoint_family="moonshot_chat",
            channel="API_SYNC",
        ),
    )
    ctx = GradeContext(
        run_id="r",
        execution_id="e",
        grading_job_id="g",
        task=task,
        grader_config_hash="sha256:0",
        input_artifact_hash="sha256:0",
    )
    scores = await grader.grade(task, [answer], ctx)
    assert scores[0].status == "scored"
    assert scores[0].metric == "official.quality_score"
    assert scores[0].raw_value == 7.0
    assert scores[0].normalized_value == 0.7


def test_default_weights_include_extra() -> None:
    weights = default_weights([{"meta_dimension_name": "Policy Fit"}])
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert "policy_fit" in weights
