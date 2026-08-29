"""Runtime guards used by extraction and analysis.

These enforce the hallucination controls in one place so that no module can quietly
promote an inference to a fact.
"""

from __future__ import annotations

from ..models.evidence import Confidence, EvidenceStatus


class ValidationProblem(Exception):
    """Raised when a structure violates an invariant we refuse to ship."""


def assert_no_unsourced_verification(items, label: str = "fact") -> list[str]:
    """Return a list of problems where VERIFIED status has no supporting source.

    Public-research claims must carry a URL; document claims must carry a document
    reference. VERIFIED with nothing behind it is downgraded by the caller, never
    silently accepted.
    """
    problems: list[str] = []
    for item in items:
        status = getattr(item, "status", None)
        sources = getattr(item, "sources", []) or []
        if status == EvidenceStatus.VERIFIED and not sources:
            problems.append(f"{label} '{getattr(item, 'claim', item)}' is VERIFIED with no source")
        for source in sources:
            if getattr(source, "source_type", "") == "public_research" and not getattr(
                source, "source_url", None
            ):
                problems.append(f"{label} '{getattr(item, 'claim', item)}' cites public research with no URL")
    return problems


def downgrade_unsourced(fact) -> None:
    """Force an unsupported VERIFIED fact down to INFERRED / LOW confidence in place."""
    if fact.status == EvidenceStatus.VERIFIED and not fact.sources:
        fact.status = EvidenceStatus.INFERRED
        fact.confidence = Confidence.LOW
        note = "Downgraded: marked verified with no supporting source."
        fact.note = f"{fact.note} {note}".strip() if fact.note else note
