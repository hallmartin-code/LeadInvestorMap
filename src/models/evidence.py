"""Evidence primitives.

Every material claim in this application is a :class:`Fact`: a value, the status of that
value, a confidence level, and the sources behind it. A value with no source cannot be
VERIFIED, and a missing value stays missing - it is never filled in with a guess.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from ..utils.dates import freshness_label, iso_today


class EvidenceStatus(str, Enum):
    """How a value came to be known."""

    VERIFIED = "VERIFIED"
    USER_PROVIDED = "USER PROVIDED"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"
    NOT_PROVIDED = "NOT PROVIDED"
    CONFLICTING = "CONFLICTING"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT EVIDENCE"


class Freshness(str, Enum):
    CURRENT = "CURRENT"
    RECENT = "RECENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class SourceType(str, Enum):
    PITCH_DECK = "pitch_deck"
    INVESTOR_LIST = "investor_list"
    CRM_EXPORT = "crm_export"
    MEETING_NOTES = "meeting_notes"
    DILIGENCE_DOC = "diligence_doc"
    INVESTOR_RESEARCH = "investor_research"
    USER_INPUT = "user_input"
    PUBLIC_RESEARCH = "public_research"
    DERIVED = "derived"


class SourceRef(BaseModel):
    """A pointer back to where a claim came from."""

    source_type: SourceType
    source_name: str = ""
    page_or_slide: int | None = None
    source_text: str = ""
    source_url: str | None = None
    source_date: str | None = None
    accessed_date: str | None = None

    @property
    def freshness(self) -> Freshness:
        # Company-supplied material is as current as the engagement itself unless it
        # carries its own date.
        if self.source_type in {SourceType.PITCH_DECK, SourceType.USER_INPUT}:
            if not self.source_date:
                return Freshness.CURRENT
        return Freshness(freshness_label(self.source_date))

    def citation(self) -> str:
        """Short human-readable citation for the PDF footnote and the sources file."""
        bits: list[str] = []
        if self.source_name:
            bits.append(self.source_name)
        if self.page_or_slide is not None:
            bits.append(f"p./sl. {self.page_or_slide}")
        if self.source_url:
            bits.append(self.source_url)
        if self.source_date:
            bits.append(self.source_date)
        return " - ".join(bits) if bits else self.source_type.value


class Fact(BaseModel):
    """A single claim with its provenance.

    A ``value`` of None means the information was not found. Rendering that state always
    produces the literal string NOT PROVIDED.
    """

    claim: str = ""
    value: str | None = None
    numeric_value: float | None = None
    status: EvidenceStatus = EvidenceStatus.NOT_PROVIDED
    confidence: Confidence = Confidence.INSUFFICIENT
    note: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)

    @field_validator("value")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        text = str(v).strip()
        return text or None

    # -- constructors ------------------------------------------------------------------

    @classmethod
    def missing(cls, claim: str = "") -> "Fact":
        return cls(
            claim=claim,
            status=EvidenceStatus.NOT_PROVIDED,
            confidence=Confidence.INSUFFICIENT,
        )

    @classmethod
    def from_user(cls, claim: str, value: str, numeric_value: float | None = None) -> "Fact":
        return cls(
            claim=claim,
            value=value,
            numeric_value=numeric_value,
            status=EvidenceStatus.USER_PROVIDED,
            confidence=Confidence.HIGH,
            sources=[
                SourceRef(
                    source_type=SourceType.USER_INPUT,
                    source_name="user entry",
                    source_text=str(value),
                    source_date=iso_today(),
                )
            ],
        )

    @classmethod
    def from_document(
        cls,
        claim: str,
        value: str,
        source: SourceRef,
        *,
        numeric_value: float | None = None,
        status: EvidenceStatus = EvidenceStatus.VERIFIED,
        confidence: Confidence = Confidence.HIGH,
    ) -> "Fact":
        return cls(
            claim=claim,
            value=value,
            numeric_value=numeric_value,
            status=status,
            confidence=confidence,
            sources=[source],
        )

    @classmethod
    def inferred(cls, claim: str, value: str, note: str, sources: list[SourceRef] | None = None) -> "Fact":
        return cls(
            claim=claim,
            value=value,
            status=EvidenceStatus.INFERRED,
            confidence=Confidence.LOW,
            note=note,
            sources=sources or [],
        )

    # -- behaviour ---------------------------------------------------------------------

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.status != EvidenceStatus.NOT_PROVIDED

    @property
    def freshness(self) -> Freshness:
        if not self.sources:
            return Freshness.UNKNOWN
        labels = [s.freshness for s in self.sources]
        for level in (Freshness.CURRENT, Freshness.RECENT, Freshness.STALE, Freshness.UNKNOWN):
            if level in labels:
                return level
        return Freshness.UNKNOWN

    def display(self, *, with_status: bool = False) -> str:
        """Render for the one-pager. Unknown values read NOT PROVIDED, never blank."""
        if not self.is_known:
            return "NOT PROVIDED"
        text = str(self.value)
        flagged = {
            EvidenceStatus.USER_PROVIDED,
            EvidenceStatus.INFERRED,
            EvidenceStatus.UNVERIFIED,
            EvidenceStatus.CONFLICTING,
        }
        if with_status and self.status in flagged:
            return f"{text} ({self.status.value})"
        return text

    def conflict_with(self, other: "Fact") -> "Fact":
        """Merge two disagreeing readings into one explicitly CONFLICTING fact."""
        merged = self.model_copy(deep=True)
        merged.status = EvidenceStatus.CONFLICTING
        merged.confidence = Confidence.LOW
        merged.sources = [*self.sources, *other.sources]
        detail = f"Conflicting values: {self.value} vs {other.value}."
        merged.note = f"{merged.note} {detail}".strip() if merged.note else detail
        return merged


class ResearchClaim(BaseModel):
    """A claim sourced from public research. A URL is mandatory - no URL, no claim."""

    claim: str
    investor_name: str = ""
    source_url: str
    source_title: str = ""
    source_date: str | None = None
    accessed_date: str = Field(default_factory=iso_today)
    confidence: Confidence = Confidence.MEDIUM
    supports: str = ""
    conflicts_with: list[str] = Field(default_factory=list)

    @property
    def freshness(self) -> Freshness:
        return Freshness(freshness_label(self.source_date))

    def to_source_ref(self) -> SourceRef:
        return SourceRef(
            source_type=SourceType.PUBLIC_RESEARCH,
            source_name=self.source_title or self.source_url,
            source_text=self.claim,
            source_url=self.source_url,
            source_date=self.source_date,
            accessed_date=self.accessed_date,
        )


class Warning(BaseModel):
    """A user-facing problem that must survive into the output rather than be swallowed."""

    severity: str = "info"  # info | warning | error
    stage: str = ""
    message: str
    detail: str | None = None

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"[{self.severity.upper()}] {self.message}"
