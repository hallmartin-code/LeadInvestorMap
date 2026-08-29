"""The round being raised, and what a credible lead would have to write into it."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..utils.config import LEAD_CHECK_HIGH_FRACTION, LEAD_CHECK_LOW_FRACTION
from ..utils.money import format_money
from .evidence import Confidence, EvidenceStatus, Fact


class Instrument(str, Enum):
    PRICED_EQUITY = "Priced Equity"
    SAFE = "SAFE"
    CONVERTIBLE_NOTE = "Convertible Note"
    OTHER = "Other"
    UNKNOWN = "NOT PROVIDED"


class Round(BaseModel):
    stage: Fact = Field(default_factory=Fact.missing)
    raise_amount: Fact = Field(default_factory=Fact.missing)
    instrument: Fact = Field(default_factory=Fact.missing)
    pre_money: Fact = Field(default_factory=Fact.missing)
    post_money: Fact = Field(default_factory=Fact.missing)
    safe_cap: Fact = Field(default_factory=Fact.missing)
    committed: Fact = Field(default_factory=Fact.missing)
    circled: Fact = Field(default_factory=Fact.missing)
    target_close: Fact = Field(default_factory=Fact.missing)
    investor_count: Fact = Field(default_factory=Fact.missing)

    # -- derived --------------------------------------------------------------------

    @property
    def remaining_amount(self) -> float | None:
        """Total raise less committed capital. None when the raise is unknown."""
        total = self.raise_amount.numeric_value
        if total is None:
            return None
        committed = self.committed.numeric_value or 0.0
        return max(0.0, total - committed)

    @property
    def remaining(self) -> Fact:
        remaining = self.remaining_amount
        if remaining is None:
            return Fact(
                claim="Remaining allocation",
                status=EvidenceStatus.NOT_PROVIDED,
                confidence=Confidence.INSUFFICIENT,
                note="Total raise not established, so remaining allocation cannot be computed.",
            )
        sources = [*self.raise_amount.sources, *self.committed.sources]
        derived_from_zero = self.committed.numeric_value is None
        return Fact(
            claim="Remaining allocation",
            value=format_money(remaining),
            numeric_value=remaining,
            status=EvidenceStatus.INFERRED,
            confidence=Confidence.LOW if derived_from_zero else Confidence.MEDIUM,
            note=(
                "Committed amount not stated; remaining shown as the full raise."
                if derived_from_zero
                else "Derived: total raise less stated commitments."
            ),
            sources=sources,
        )

    @property
    def valuation_display(self) -> str:
        """One line covering whichever valuation marker the round actually uses."""
        if self.safe_cap.is_known:
            return f"Cap {self.safe_cap.display()}"
        if self.pre_money.is_known:
            return f"Pre {self.pre_money.display()}"
        if self.post_money.is_known:
            return f"Post {self.post_money.display()}"
        return "NOT PROVIDED"


class LeadRequirement(BaseModel):
    """What a lead has to be able to write, and how confident we are in that figure."""

    remaining_raise: float | None = None
    lead_check_min: float | None = None
    lead_check_max: float | None = None
    basis: str = ""
    confidence: Confidence = Confidence.INSUFFICIENT
    status: EvidenceStatus = EvidenceStatus.NOT_PROVIDED
    assumptions: list[str] = Field(default_factory=list)

    @property
    def is_known(self) -> bool:
        return self.lead_check_min is not None

    def display(self) -> str:
        if not self.is_known:
            return "NOT PROVIDED"
        return f"{format_money(self.lead_check_min)}-{format_money(self.lead_check_max)}"


def estimate_lead_requirement(round_: Round) -> LeadRequirement:
    """Estimate the cheque a credible lead would need to write.

    This is an estimate and is labelled as one. It is derived only from figures that
    were actually established; with no raise figure there is no estimate.
    """
    remaining = round_.remaining_amount
    if remaining is None or remaining <= 0:
        return LeadRequirement(
            remaining_raise=remaining,
            basis=(
                "Round size not established in the supplied materials."
                if remaining is None
                else "Remaining allocation is zero on the stated figures."
            ),
            confidence=Confidence.INSUFFICIENT,
            status=EvidenceStatus.NOT_PROVIDED,
        )

    low = remaining * LEAD_CHECK_LOW_FRACTION
    high = remaining * LEAD_CHECK_HIGH_FRACTION

    assumptions = [
        f"Lead assumed to take {int(LEAD_CHECK_LOW_FRACTION * 100)}-"
        f"{int(LEAD_CHECK_HIGH_FRACTION * 100)}% of the remaining allocation.",
    ]
    if round_.committed.numeric_value is None:
        assumptions.append(
            "ASSUMPTION - no commitments were stated, so the full raise is treated as remaining."
        )
    if not round_.stage.is_known:
        assumptions.append("ASSUMPTION - stage not stated; syndicate shape not stage-adjusted.")

    confidence = Confidence.MEDIUM
    if round_.raise_amount.status in {EvidenceStatus.INFERRED, EvidenceStatus.UNVERIFIED}:
        confidence = Confidence.LOW
    if round_.committed.numeric_value is None:
        confidence = Confidence.LOW

    return LeadRequirement(
        remaining_raise=remaining,
        lead_check_min=low,
        lead_check_max=high,
        basis=(
            f"{format_money(round_.raise_amount.numeric_value)} raise less "
            f"{format_money(round_.committed.numeric_value or 0)} committed = "
            f"{format_money(remaining)} remaining."
        ),
        confidence=confidence,
        status=EvidenceStatus.INFERRED,
        assumptions=assumptions,
    )
