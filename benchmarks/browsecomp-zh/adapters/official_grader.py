"""Official BrowseComp-ZH grader wrapper.

Keeps the upstream Judge prompt and GPT-4o judge path from PALIN2018/BrowseComp-ZH
(prompt.py + run.py). This file does not invent a new LLM Judge.
"""

from __future__ import annotations

from pathlib import Path

UPSTREAM_PROMPT = Path(__file__).with_name("official_prompt.py")


def load_official_judge_prompt() -> str:
    ns: dict = {}
    exec(UPSTREAM_PROMPT.read_text(encoding="utf-8"), ns)
    return ns["JUDGE_PROMPT_CN"]


def build_judge_messages(question: str, response: str, correct_answer: str) -> list[dict]:
    prompt = load_official_judge_prompt().format(
        question=question,
        response=response,
        correct_answer=correct_answer,
    )
    return [
        {"role": "system", "content": "you are a helpful assistant!"},
        {"role": "user", "content": prompt},
    ]


OFFICIAL_JUDGE_MODEL = "gpt-4o"
