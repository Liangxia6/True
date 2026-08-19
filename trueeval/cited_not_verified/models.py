from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Citation:
    citation_id: str
    url: str
    raw_labels: list[str] = field(default_factory=list)
    url_content: str | None = None
    link_works: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Attribution:
    attribution_id: str
    text_nocite: str
    span: tuple[int, int]
    citation_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PairEval:
    attribution_id: str
    citation_id: str
    link_works: int
    relevant_content: int | None
    fact_check: int | None
    relevant_rationale: str | None = None
    fact_check_rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AttributionDocument:
    query: str | None
    citations: list[Citation]
    attributions: list[Attribution]
    evals: list[PairEval] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "trueeval.cited_not_verified.document.v0.1",
            "query": self.query,
            "citations": [c.to_dict() for c in self.citations],
            "attributions": [a.to_dict() for a in self.attributions],
            "evals": [e.to_dict() for e in self.evals],
            "notes": list(self.notes),
            "aggregate": self.aggregate(),
        }

    def aggregate(self) -> dict[str, Any]:
        evals = self.evals
        def _rate(key: str) -> float | None:
            vals = [getattr(e, key) for e in evals if getattr(e, key) is not None]
            if not vals:
                return None
            return sum(int(v) for v in vals) / len(vals)

        return {
            "n_citations": len(self.citations),
            "n_attributions": len(self.attributions),
            "n_pairs": len(evals),
            "link_works": _rate("link_works"),
            "relevant_content": _rate("relevant_content"),
            "fact_check": _rate("fact_check"),
            "fuse_scores": False,
        }
