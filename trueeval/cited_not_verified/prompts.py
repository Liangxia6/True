"""Judge prompts for Relevant Content and Fact Check.

Onweller et al. (arXiv:2605.06635) define the two LLM dimensions and the 5,000
character truncation. The exact system/user strings were published by the same
group for this pipeline in Leung et al. (arXiv:2607.08700) Appendix A. They are
copied verbatim. Do not rewrite them into a new Judge.
"""

CONTENT_TRUNCATE_CHARS = 5000

SOURCE_RELEVANCE_SYSTEM = """You are an expert evaluator assessing content relevance.
Your task is to determine if the content at a URL is relevant to a given
attribution text.

Evaluate whether the content at the URL is relevant to the attribution text.
Consider:
- Does the URL content discuss the same topic as the attribution?
- Does it provide supporting information for the claims in the attribution?
- Is there a clear connection between the attribution and the URL content?

This is a binary evaluation:
- score = 1 if the content IS relevant
- score = 0 if the content is NOT relevant"""

SOURCE_RELEVANCE_HUMAN = """Attribution Text:
{attribution_text}

URL: {url}

URL Content:
{url_content}

Evaluate whether this URL content is relevant to the attribution text."""

FACTUAL_SUPPORT_SYSTEM = """You are an expert fact-checker evaluating factual accuracy.
Your task is to determine if the factual claims in an attribution text are
supported by the content at a URL.

Evaluate whether the factual claims in the attribution text are supported by
the URL content. Consider:
- Are the specific facts, numbers, dates, and claims in the attribution text
  present in the URL content?
- Do they match or are they consistent?
- Are there any contradictions?

This is a binary evaluation:
- score = 1 if the facts ARE supported by the URL content
- score = 0 if the facts are NOT supported (contradicted, missing, or
  unverifiable)"""

FACTUAL_SUPPORT_HUMAN = """Attribution Text:
{attribution_text}

URL: {url}

URL Content:
{url_content}

Verify whether the factual claims in the attribution text are supported by
this URL content."""
