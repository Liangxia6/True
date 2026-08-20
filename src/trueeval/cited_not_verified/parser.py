"""Markdown AST parser from Onweller et al., arXiv:2605.06635 §3.2 / Algorithm 1.

Stages: canonicalize → strip fenced code → extract citation nodes → sentence
segment → backward-attribute. No LLM is used here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urldefrag, urlparse

from trueeval.cited_not_verified.models import Attribution, AttributionDocument, Citation

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,}).*$", re.MULTILINE)
REF_DEF_RE = re.compile(
    r"^\[(?P<label>[^\]]+)\]:\s*(?P<url><[^>\s]+>|\S+)",
    re.MULTILINE,
)
INLINE_LINK_RE = re.compile(
    r"""(?P<img>!?)\[(?P<text>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+"[^"]*")?\)"""
)
AUTOLINK_RE = re.compile(r"<(?P<url>https?://[^>\s]+)>")
RANGE_CITE_RE = re.compile(r"\[(\d+)\s*-\s*(\d+)\]")
NUM_CITE_RE = re.compile(r"\[(\d+)\]")
FOOTNOTE_CITE_RE = re.compile(r"\[\^(?P<label>[^\]]+)\]")
SENTENCE_RE = re.compile(
    r"(?:(?<=[.!?])|(?<=\]))(?:\s+|\n+)(?=[A-Z0-9\"“'(\[])"
)


def canonicalize(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip() + "\n"


def strip_fenced_code(markdown: str) -> str:
    lines = markdown.split("\n")
    kept: list[str] = []
    fence: str | None = None
    for line in lines:
        m = FENCE_RE.match(line)
        if m:
            token = m.group(1)[0]
            if fence is None:
                fence = token
            elif token == fence:
                fence = None
            continue
        if fence is None:
            kept.append(line)
    return "\n".join(kept)


def _clean_url(raw: str) -> str:
    url = raw.strip().strip("<>").strip(".,);")
    url, _ = urldefrag(url)
    return url


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@dataclass
class _CiteNode:
    start: int
    end: int
    labels: list[str]
    url: str | None


def _expand_range(lo: int, hi: int) -> list[str]:
    if hi < lo:
        lo, hi = hi, lo
    if hi - lo > 50:
        return [str(lo), str(hi)]
    return [str(i) for i in range(lo, hi + 1)]


def _extract_nodes(text: str) -> tuple[list[_CiteNode], dict[str, str]]:
    registry: dict[str, str] = {}
    occupied: list[tuple[int, int]] = []
    nodes: list[_CiteNode] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(not (end <= a or start >= b) for a, b in occupied)

    for m in REF_DEF_RE.finditer(text):
        url = _clean_url(m.group("url"))
        if _is_http_url(url):
            registry[m.group("label").strip()] = url
        occupied.append((m.start(), m.end()))

    for m in INLINE_LINK_RE.finditer(text):
        if m.group("img"):
            occupied.append((m.start(), m.end()))
            continue
        url = _clean_url(m.group("url"))
        if not _is_http_url(url) or _overlaps(m.start(), m.end()):
            continue
        label = m.group("text").strip() or url
        registry.setdefault(label, url)
        nodes.append(_CiteNode(m.start(), m.end(), [label], url))
        occupied.append((m.start(), m.end()))

    for m in AUTOLINK_RE.finditer(text):
        url = _clean_url(m.group("url"))
        if not _is_http_url(url) or _overlaps(m.start(), m.end()):
            continue
        registry.setdefault(url, url)
        nodes.append(_CiteNode(m.start(), m.end(), [url], url))
        occupied.append((m.start(), m.end()))

    for m in RANGE_CITE_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        labels = _expand_range(int(m.group(1)), int(m.group(2)))
        nodes.append(_CiteNode(m.start(), m.end(), labels, None))
        occupied.append((m.start(), m.end()))

    for m in NUM_CITE_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        nodes.append(_CiteNode(m.start(), m.end(), [m.group(1)], None))
        occupied.append((m.start(), m.end()))

    for m in FOOTNOTE_CITE_RE.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        nodes.append(_CiteNode(m.start(), m.end(), [m.group("label")], None))
        occupied.append((m.start(), m.end()))

    nodes.sort(key=lambda n: n.start)
    return nodes, registry


def _strip_citation_markup(sentence: str) -> str:
    s = INLINE_LINK_RE.sub(lambda m: "" if m.group("img") else m.group("text"), sentence)
    s = AUTOLINK_RE.sub("", s)
    s = RANGE_CITE_RE.sub("", s)
    s = NUM_CITE_RE.sub("", s)
    s = FOOTNOTE_CITE_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_paragraphs(text: str) -> list[tuple[int, int, str]]:
    parts: list[tuple[int, int, str]] = []
    start = 0
    for m in re.finditer(r"\n\s*\n", text):
        block = text[start:m.start()]
        if block.strip():
            parts.append((start, m.start(), block))
        start = m.end()
    tail = text[start:]
    if tail.strip():
        parts.append((start, len(text), tail))
    return parts


def _split_sentences(paragraph: str, abs_start: int) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for m in SENTENCE_RE.finditer(paragraph):
        chunk = paragraph[cursor:m.start()]
        if chunk.strip():
            spans.append((abs_start + cursor, abs_start + m.start(), chunk.strip()))
        cursor = m.end()
    tail = paragraph[cursor:]
    if tail.strip():
        spans.append((abs_start + cursor, abs_start + len(paragraph), tail.strip()))
    return spans


def parse_markdown_report(markdown: str, query: str | None = None) -> AttributionDocument:
    raw = canonicalize(markdown)
    body = strip_fenced_code(raw)
    nodes, registry = _extract_nodes(body)

    url_to_id: dict[str, str] = {}
    citations: list[Citation] = []
    label_to_id: dict[str, str] = {}

    def _ensure_citation(url: str, label: str | None) -> str | None:
        url = _clean_url(url)
        if not _is_http_url(url):
            return None
        if url not in url_to_id:
            cid = f"c{len(citations) + 1}"
            url_to_id[url] = cid
            citations.append(Citation(citation_id=cid, url=url, raw_labels=[]))
        cid = url_to_id[url]
        target = next(c for c in citations if c.citation_id == cid)
        if label and label not in target.raw_labels:
            target.raw_labels.append(label)
        if label:
            label_to_id[label] = cid
        return cid

    for label, url in registry.items():
        _ensure_citation(url, label)

    for node in nodes:
        if node.url:
            for lab in node.labels:
                _ensure_citation(node.url, lab)

    notes: list[str] = []
    attributions: list[Attribution] = []
    aid = 0

    for p_start, _p_end, para in _split_paragraphs(body):
        sentences = _split_sentences(para, p_start)
        pending: list[tuple[int, int, str]] = []
        for s_start, s_end, sent in sentences:
            sent_nodes = [n for n in nodes if s_start <= n.start < s_end]
            cite_ids: list[str] = []
            for n in sent_nodes:
                if n.url:
                    cid = _ensure_citation(n.url, n.labels[0] if n.labels else None)
                    if cid:
                        cite_ids.append(cid)
                    continue
                for lab in n.labels:
                    cid = label_to_id.get(lab)
                    if cid:
                        cite_ids.append(cid)
                    else:
                        notes.append(f"unresolved_citation_label:{lab}")
            cite_ids = list(dict.fromkeys(cite_ids))
            if cite_ids:
                bundle = pending + [(s_start, s_end, sent)]
                pending = []
                for b_start, b_end, b_sent in bundle:
                    aid += 1
                    attributions.append(
                        Attribution(
                            attribution_id=f"a{aid}",
                            text_nocite=_strip_citation_markup(b_sent),
                            span=(b_start, b_end),
                            citation_ids=list(cite_ids),
                        )
                    )
            else:
                pending.append((s_start, s_end, sent))

    return AttributionDocument(
        query=query,
        citations=citations,
        attributions=attributions,
        notes=notes,
    )
