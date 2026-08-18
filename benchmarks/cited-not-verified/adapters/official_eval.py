"""Wrapper for the Onweller et al. source-attribution runner."""

from __future__ import annotations

from trueeval.cited_not_verified.judge import JudgeClient
from trueeval.cited_not_verified.pipeline import evaluate_report


def evaluate_markdown(markdown: str, query: str | None = None, judge: JudgeClient | None = None):
    return evaluate_report(markdown, query=query, judge=judge)


OFFICIAL_PRIMARY_METRIC = "official.fact_check"
FUSE_OFFICIAL_SCORES = False
