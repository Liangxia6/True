"""Built-in graders. Official prompts stay in their upstream wrappers."""

from __future__ import annotations

from trueeval.graders.cited_not_verified import CitedNotVerifiedGrader
from trueeval.graders.deepresearch_quality import OfficialQualityGrader
from trueeval.graders.exact_match import ExactMatchGrader
from trueeval.graders.format import FormatCompletenessGrader
from trueeval.graders.official_wrapper import OfficialAccuracyGrader


def default_graders(*, fetch_citations: bool = False, judge: object | None = None) -> dict[str, object]:
    return {
        "format-completeness": FormatCompletenessGrader(),
        "exact-match": ExactMatchGrader(),
        "official-accuracy": OfficialAccuracyGrader(judge=judge),
        "official-quality": OfficialQualityGrader(judge=judge),
        "cited-not-verified": CitedNotVerifiedGrader(fetch=fetch_citations, judge=judge),
    }
