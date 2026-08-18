"""Run the Cited but Not Verified framework on a Markdown report.

Examples:
  python scripts/eval_cited_not_verified.py --self-check
  python scripts/eval_cited_not_verified.py --report report.md --out out.json
  python scripts/eval_cited_not_verified.py --report report.md --no-fetch
  python scripts/eval_cited_not_verified.py --report report.md --judge-model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trueeval.cited_not_verified.judge import OpenAICompatJudge, parse_binary_score
from trueeval.cited_not_verified.parser import parse_markdown_report
from trueeval.cited_not_verified.pipeline import evaluate_report

SAMPLE = """# Sample

The Taylor series is an infinite sum used to approximate functions.[1]
It is widely taught in first-year calculus.

See also the [OpenStax chapter](https://openstax.org/books/calculus-volume-1/).

[1]: https://openstax.org/books/calculus-volume-1/
"""


def self_check() -> int:
    doc = parse_markdown_report(SAMPLE, query="What is a Taylor series?")
    urls = {c.url for c in doc.citations}
    assert "https://openstax.org/books/calculus-volume-1/" in urls, urls
    assert len(doc.attributions) >= 1, doc
    texts = [a.text_nocite for a in doc.attributions]
    assert any("Taylor series" in t for t in texts), texts
    first = next(a for a in doc.attributions if "Taylor series" in a.text_nocite)
    assert first.citation_ids, first
    assert "[1]" not in first.text_nocite
    score, _ = parse_binary_score("The facts match.\nscore = 1")
    assert score == 1
    print("self-check ok")
    print(json.dumps(doc.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cited but Not Verified citation evaluator")
    parser.add_argument("--report", type=Path, help="Markdown report path")
    parser.add_argument("--query", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--judge-model", default=None, help="OpenAI-compatible model for Relevant/Fact Check")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    if args.self_check:
        return self_check()
    if args.report is None:
        parser.error("--report is required unless --self-check")

    markdown = args.report.read_text(encoding="utf-8")
    judge = OpenAICompatJudge(model=args.judge_model) if args.judge_model else None
    doc = evaluate_report(
        markdown,
        query=args.query,
        judge=judge,
        fetch=not args.no_fetch,
        score_llm_dims=judge is not None,
    )
    payload = doc.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
