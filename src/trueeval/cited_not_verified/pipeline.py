"""Algorithm 1 evaluation runner (Onweller et al., arXiv:2605.06635).

Phase 1 is deterministic parse. Phase 2 fetches each unique URL, then scores
every attribution-citation pair. The three dimensions stay separate.
"""

from __future__ import annotations

from trueeval.cited_not_verified.fetch import fetch_url
from trueeval.cited_not_verified.judge import (
    JudgeClient,
    score_fact_check,
    score_relevant_content,
)
from trueeval.cited_not_verified.models import AttributionDocument, PairEval
from trueeval.cited_not_verified.parser import parse_markdown_report


def evaluate_report(
    markdown: str,
    *,
    query: str | None = None,
    judge: JudgeClient | None = None,
    fetch: bool = True,
    score_llm_dims: bool = True,
) -> AttributionDocument:
    doc = parse_markdown_report(markdown, query=query)

    if fetch:
        for citation in doc.citations:
            result = fetch_url(citation.url)
            citation.link_works = result.link_works
            citation.url_content = result.url_content
            if result.error:
                doc.notes.append(f"fetch:{citation.citation_id}:{result.error}")
    else:
        for citation in doc.citations:
            citation.link_works = None
            citation.url_content = None

    cite_by_id = {c.citation_id: c for c in doc.citations}
    for attr in doc.attributions:
        for cid in attr.citation_ids:
            citation = cite_by_id[cid]
            link = 0 if citation.link_works is None else int(citation.link_works)
            relevant = None
            fact = None
            rel_why = None
            fact_why = None
            if score_llm_dims and judge is not None and citation.link_works == 1:
                relevant, rel_why = score_relevant_content(
                    judge, attr.text_nocite, citation.url, citation.url_content or ""
                )
                fact, fact_why = score_fact_check(
                    judge, attr.text_nocite, citation.url, citation.url_content or ""
                )
            elif score_llm_dims and judge is None:
                doc.notes.append("llm_dims_skipped_no_judge")
                score_llm_dims = False
            doc.evals.append(
                PairEval(
                    attribution_id=attr.attribution_id,
                    citation_id=cid,
                    link_works=link,
                    relevant_content=relevant,
                    fact_check=fact,
                    relevant_rationale=rel_why,
                    fact_check_rationale=fact_why,
                )
            )
    return doc
