"""Cited but Not Verified source-attribution framework (Onweller et al., arXiv:2605.06635).

Official pipeline: parse Markdown citations without an LLM, fetch each URL, then
score Link Works / Relevant Content / Fact Check independently. Do not fuse the
three scores.
"""

from trueeval.cited_not_verified.models import Attribution, AttributionDocument, Citation, PairEval
from trueeval.cited_not_verified.parser import parse_markdown_report
from trueeval.cited_not_verified.pipeline import evaluate_report

__all__ = [
    "Attribution",
    "AttributionDocument",
    "Citation",
    "PairEval",
    "evaluate_report",
    "parse_markdown_report",
]
