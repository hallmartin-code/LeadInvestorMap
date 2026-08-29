"""The company being financed, as read from the deck."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .evidence import Fact


class Objection(BaseModel):
    """An investor objection derived from the deck, not from boilerplate.

    ``evidence`` must quote or paraphrase the deck content that creates the objection;
    an objection with no evidence is not shown.
    """

    category: str
    objection: str
    evidence: str = ""
    source_ref: str = ""
    severity: str = "medium"  # high | medium | low

    @property
    def is_grounded(self) -> bool:
        return bool(self.evidence.strip())


class Company(BaseModel):
    name: Fact = Field(default_factory=Fact.missing)
    one_liner: Fact = Field(default_factory=Fact.missing)
    sector: Fact = Field(default_factory=Fact.missing)
    sub_sector: Fact = Field(default_factory=Fact.missing)
    business_model: Fact = Field(default_factory=Fact.missing)
    market: Fact = Field(default_factory=Fact.missing)
    stage: Fact = Field(default_factory=Fact.missing)
    location: Fact = Field(default_factory=Fact.missing)
    fundraising_status: Fact = Field(default_factory=Fact.missing)

    traction: list[Fact] = Field(default_factory=list)
    key_risks: list[Fact] = Field(default_factory=list)
    investor_weaknesses: list[Fact] = Field(default_factory=list)
    named_competitors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    objections: list[Objection] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name.value or "COMPANY NOT IDENTIFIED"

    def sector_terms(self) -> list[str]:
        """Terms used for sector-fit and conflict matching, lower-cased and de-duplicated.

        The business model is deliberately excluded: "software licence plus per-test
        cartridge revenue" describes how the company charges, and letting the word
        "software" into sector matching makes an enterprise-software fund look like a fit
        for a diagnostics company.
        """
        terms: list[str] = []
        for fact in (self.sector, self.sub_sector, self.market):
            if fact.is_known:
                terms.extend(t.strip().lower() for t in str(fact.value).replace("/", ",").split(","))
        terms.extend(k.strip().lower() for k in self.keywords)
        seen: list[str] = []
        for term in terms:
            cleaned = term.strip(" .;:-")
            if len(cleaned) >= 3 and cleaned not in seen:
                seen.append(cleaned)
        return seen
