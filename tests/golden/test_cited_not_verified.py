from __future__ import annotations

from trueeval.cited_not_verified.judge import parse_binary_score
from trueeval.cited_not_verified.parser import parse_markdown_report
from trueeval.cited_not_verified.pipeline import evaluate_report

SAMPLE = """# Sample

The Taylor series is an infinite sum used to approximate functions.[1]
It is widely taught in first-year calculus.

See also the [OpenStax chapter](https://openstax.org/books/calculus-volume-1/).

[1]: https://openstax.org/books/calculus-volume-1/
"""


def test_parse_golden() -> None:
    doc = parse_markdown_report(SAMPLE, query="What is a Taylor series?")
    urls = {c.url for c in doc.citations}
    assert "https://openstax.org/books/calculus-volume-1/" in urls
    assert len(doc.attributions) >= 1
    first = next(a for a in doc.attributions if "Taylor series" in a.text_nocite)
    assert first.citation_ids
    assert "[1]" not in first.text_nocite
    score, _ = parse_binary_score("The facts match.\nscore = 1")
    assert score == 1


def test_evaluate_without_fetch_does_not_invent_llm_scores() -> None:
    doc = evaluate_report(SAMPLE, query="q", fetch=False, score_llm_dims=False)
    assert doc.evals
    assert all(e.relevant_content is None and e.fact_check is None for e in doc.evals)
    agg = doc.aggregate()
    assert agg["fuse_scores"] is False
