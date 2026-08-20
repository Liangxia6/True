from __future__ import annotations

from trueeval.core.schemas.artifact import ResearchAnswer, SUTIdentity
from trueeval.core.schemas.benchmark import GoldRecord, TaskInput, TaskSpec
from trueeval.core.schemas.grader import GradeContext
from trueeval.graders.official_wrapper import (
    OfficialAccuracyGrader,
    _load_official_prompt_template,
    _parse_official_verdict,
)


class _ScriptedJudge:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.text


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="xbench-deepsearch.2505.000001",
        benchmark_id="xbench-deepsearch",
        upstream_task_id="1",
        split="2505",
        input=TaskInput(prompt="2024年上海黄金交易所 Au(T+D) 最高价是多少？"),
    )


def _answer(text: str) -> ResearchAnswer:
    return ResearchAnswer(
        schema_version="trueeval.research_answer.v0.1",
        run_id="run-1",
        execution_id="e1",
        task_id="xbench-deepsearch.2505.000001",
        repeat_index=0,
        status="completed",
        final_answer=text,
        channel="API_SYNC",
        sut=SUTIdentity(
            provider="kimi",
            product="kimi-research",
            model="kimi-k2.6",
            endpoint_family="moonshot_chat",
            channel="API_SYNC",
        ),
    )


def _ctx() -> GradeContext:
    return GradeContext(
        run_id="run-1",
        execution_id="e1",
        grading_job_id="g1",
        task=_task(),
        gold=GoldRecord(
            task_id="xbench-deepsearch.2505.000001",
            answer_type="short_text",
            reference_answer="637.30元/克",
        ),
        grader_config_hash="sha256:0",
        input_artifact_hash="sha256:0",
    )


def test_xbench_official_prompt_is_loaded() -> None:
    template = _load_official_prompt_template("xbench-deepsearch")
    assert template is not None
    assert "[正确答案]" in template
    assert "结论" in template


def test_parse_xbench_and_browsecomp_verdicts() -> None:
    assert _parse_official_verdict("最终答案: 1\n解释: 一致\n结论: 正确") is True
    assert _parse_official_verdict("结论：错误") is False
    assert _parse_official_verdict("correct: yes\nconfidence: 100") is True
    assert _parse_official_verdict("correct: no") is False
    assert _parse_official_verdict("I think it looks fine") is None


async def test_official_grader_uses_llm_judge() -> None:
    judge = _ScriptedJudge("最终答案: 637.30元/克\n解释: 与正确答案一致\n结论: 正确")
    scores = await OfficialAccuracyGrader(judge=judge).grade(
        _task(),
        [_answer("根据年报，2024年最高价为637.30元/克，最低1984元/公斤。")],
        _ctx(),
    )
    assert scores[0].normalized_value == 1.0
    assert "正确答案" in judge.prompts[0] or "[正确答案]" in judge.prompts[0]


async def test_official_grader_falls_back_without_judge() -> None:
    scores = await OfficialAccuracyGrader().grade(
        _task(),
        [_answer("a long research paragraph that is not an exact match")],
        _ctx(),
    )
    assert scores[0].normalized_value == 0.0
    assert scores[0].rationale and "not configured" in scores[0].rationale
