"""Freshness handling for investor evidence.

Fund status, cheque size, partner roles and lead behaviour all go out of date quickly.
Nothing here deletes stale evidence - it labels it, and downgrades the confidence of any
conclusion that rests on it, so a two-year-old fund announcement cannot masquerade as a
current deployment signal.
"""

from __future__ import annotations

from datetime import date

from ..models.evidence import Confidence, Freshness, ResearchClaim
from ..utils.dates import freshness_label, parse_date, today

#: Fields whose staleness materially changes the conclusion.
TIME_SENSITIVE = (
    "fund_status",
    "check_size",
    "partner_role",
    "portfolio",
    "lead_behaviour",
    "investment_thesis",
)


def label(source_date: str | date | None, *, now: date | None = None) -> Freshness:
    return Freshness(freshness_label(source_date, now=now or today()))


def downgrade_for_age(confidence: Confidence, freshness: Freshness) -> Confidence:
    """Stale evidence cannot support a HIGH-confidence conclusion."""
    if freshness == Freshness.STALE:
        if confidence == Confidence.HIGH:
            return Confidence.LOW
        if confidence == Confidence.MEDIUM:
            return Confidence.LOW
    elif freshness == Freshness.UNKNOWN and confidence == Confidence.HIGH:
        return Confidence.MEDIUM
    return confidence


def apply_freshness(claims: list[ResearchClaim]) -> list[str]:
    """Adjust claim confidence by age. Returns notes describing what was downgraded."""
    notes: list[str] = []
    for claim in claims:
        freshness = claim.freshness
        adjusted = downgrade_for_age(claim.confidence, freshness)
        if adjusted != claim.confidence:
            notes.append(
                f"{claim.investor_name or 'claim'}: '{claim.claim[:60]}' downgraded to "
                f"{adjusted.value} ({freshness.value} source)."
            )
            claim.confidence = adjusted
    return notes


def freshest(claims: list[ResearchClaim]) -> ResearchClaim | None:
    dated = [(parse_date(c.source_date), c) for c in claims]
    dated = [(d, c) for d, c in dated if d is not None]
    if not dated:
        return claims[0] if claims else None
    return max(dated, key=lambda pair: pair[0])[1]
