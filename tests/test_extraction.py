"""Extraction: round parameters, investor records, and the rules about what counts."""

from __future__ import annotations

from pathlib import Path

from src.extraction.investor_extractor import (
    extract_investors,
    investors_from_rows,
    investors_from_text,
)
from src.extraction.normalizer import (
    deduplicate,
    identity_key,
    merge_investors,
    normalise_name,
    same_investor,
)
from src.extraction.round_extractor import (
    apply_user_overrides,
    extract_round_rule_based,
    merge_round,
)
from src.ingestion.loader import load_document
from src.ingestion.types import ParsedDocument, Segment
from src.models.evidence import Confidence, EvidenceStatus, SourceRef, SourceType
from src.models.investor import DiligenceStage, FundStatus, InvestorType, Relationship
from src.models.round import estimate_lead_requirement
from src.utils.money import format_money
from tests.factories import make_investor


def _deck(text: str, index: int = 12) -> ParsedDocument:
    document = ParsedDocument(path=Path("deck.pdf"), name="deck.pdf", source_type=SourceType.PITCH_DECK)
    document.segments = [Segment(index=index, text=text)]
    return document


# --- round -------------------------------------------------------------------------------


def test_round_parameters_are_extracted_with_page_references(deck_path):
    document = load_document(deck_path, SourceType.PITCH_DECK)
    round_ = extract_round_rule_based(document)

    assert round_.stage.value == "Series A"
    assert round_.raise_amount.numeric_value == 6_000_000
    assert round_.instrument.value == "Priced Equity"
    assert round_.pre_money.numeric_value == 22_000_000
    assert round_.committed.numeric_value == 1_500_000
    assert round_.circled.numeric_value == 400_000
    assert round_.target_close.value == "December 2026"
    assert round_.raise_amount.sources[0].page_or_slide == 4


def test_missing_values_stay_missing():
    round_ = extract_round_rule_based(_deck("We are a diagnostics company."))
    assert round_.raise_amount.display() == "NOT PROVIDED"
    assert round_.raise_amount.status == EvidenceStatus.NOT_PROVIDED
    assert round_.remaining.display() == "NOT PROVIDED"
    assert not estimate_lead_requirement(round_).is_known


def test_a_safe_cap_infers_the_instrument_but_labels_the_inference():
    round_ = extract_round_rule_based(_deck("Raising $2M with a valuation cap of $12M."))
    assert round_.safe_cap.numeric_value == 12_000_000
    assert round_.instrument.value == "SAFE"
    assert round_.instrument.status == EvidenceStatus.INFERRED
    assert "ASSUMPTION" in round_.instrument.note


def test_conflicting_figures_are_marked_not_resolved():
    document = _deck("Raising $6M Series A.")
    document.segments.append(Segment(index=20, text="Round size: $8M"))
    round_ = extract_round_rule_based(document)

    assert round_.raise_amount.status == EvidenceStatus.CONFLICTING
    assert round_.raise_amount.confidence == Confidence.LOW
    assert len(round_.raise_amount.sources) == 2
    assert "Conflicting values" in round_.raise_amount.note


def test_merge_prefers_the_primary_and_flags_disagreement():
    primary = extract_round_rule_based(_deck("Raising $6M Series A."))
    secondary = extract_round_rule_based(_deck("Raising $6M Series A. $2M committed."))
    merged = merge_round(primary, secondary)

    assert merged.raise_amount.confidence == Confidence.HIGH  # both agree
    assert merged.committed.numeric_value == 2_000_000  # only one had it

    disagreeing = extract_round_rule_based(_deck("Raising $9M Series A."))
    conflicted = merge_round(primary, disagreeing)
    assert conflicted.raise_amount.status == EvidenceStatus.CONFLICTING


def test_user_overrides_win_and_are_labelled():
    round_ = extract_round_rule_based(_deck("Raising $6M Series A."))
    updated = apply_user_overrides(round_, {"raise_amount": "$9M", "target_close": "March 2027"})

    assert updated.raise_amount.numeric_value == 9_000_000
    assert updated.raise_amount.status == EvidenceStatus.USER_PROVIDED
    assert "USER PROVIDED" in updated.raise_amount.display(with_status=True)
    assert updated.target_close.value == "March 2027"


def test_user_override_survives_a_later_merge():
    user = apply_user_overrides(extract_round_rule_based(_deck("")), {"raise_amount": "$9M"})
    deck = extract_round_rule_based(_deck("Raising $6M Series A."))
    merged = merge_round(user, deck)
    assert merged.raise_amount.numeric_value == 9_000_000
    assert merged.raise_amount.status == EvidenceStatus.USER_PROVIDED


def test_lead_requirement_is_derived_and_labelled_an_estimate():
    round_ = extract_round_rule_based(_deck("Raising $6M Series A. $1.5M committed from existing investors."))
    requirement = estimate_lead_requirement(round_)

    assert requirement.remaining_raise == 4_500_000
    assert requirement.lead_check_min == 1_800_000
    assert requirement.lead_check_max == 3_150_000
    assert requirement.status == EvidenceStatus.INFERRED
    assert format_money(4_500_000) in requirement.basis


def test_lead_requirement_without_commitments_says_so():
    round_ = extract_round_rule_based(_deck("Raising $6M Series A."))
    requirement = estimate_lead_requirement(round_)
    assert requirement.remaining_raise == 6_000_000
    assert requirement.confidence == Confidence.LOW
    assert any("no commitments were stated" in a for a in requirement.assumptions)


# --- investors ---------------------------------------------------------------------------


def test_investor_rows_become_records(investors_csv):
    document = load_document(investors_csv, SourceType.INVESTOR_LIST)
    investors = investors_from_rows(document)
    by_name = {i.investor_name: i for i in investors}

    northlight = by_name["Northlight Diagnostics Fund"]
    assert northlight.investor_type == InvestorType.MICRO_VC
    assert northlight.estimated_check_min == 2_000_000
    assert northlight.estimated_check_max == 4_000_000
    assert northlight.has_verified_lead_history
    assert northlight.relationship_strength == Relationship.WARM_INTRO_AVAILABLE
    assert northlight.sources[0].page_or_slide == 3  # csv row number


def test_participation_is_not_lead_history(investors_csv):
    document = load_document(investors_csv, SourceType.INVESTOR_LIST)
    investors = {i.investor_name: i for i in investors_from_rows(document)}
    bigname = investors["Bigname Global Partners"]

    assert not bigname.has_verified_lead_history
    assert bigname.lead_history_display() == "NOT VERIFIED"


def test_stated_non_lead_behaviour_is_recorded(investors_csv):
    document = load_document(investors_csv, SourceType.INVESTOR_LIST)
    investors = {i.investor_name: i for i in investors_from_rows(document)}
    assert investors["Followell Capital"].leads_rounds_stated is False
    assert investors["Grandview Strategic Ventures"].leads_rounds_stated is False


def test_notes_attribute_lead_history_to_the_right_investor(notes_path):
    document = load_document(notes_path, SourceType.MEETING_NOTES)
    investors = {i.investor_name: i for i in investors_from_text(document)}

    assert investors["Northlight Diagnostics Fund"].has_verified_lead_history
    # The fund named inside Northlight's sentence is a portfolio company, not a prospect.
    assert "Vessl Dx" not in investors
    assert not investors["Bigname Global Partners"].has_verified_lead_history
    assert investors["Bigname Global Partners"].leads_rounds_stated is False


def test_notes_capture_stated_dependencies_and_intro_paths(notes_path):
    document = load_document(notes_path, SourceType.MEETING_NOTES)
    investors = {i.investor_name: i for i in investors_from_text(document)}

    assert "Lead investor secured" in investors["Grandview Strategic Ventures"].stated_dependencies
    northlight = investors["Northlight Diagnostics Fund"]
    assert northlight.warm_intro_path and "Dr Patel" in northlight.warm_intro_path


def test_fund_status_is_read_from_the_text(investors_csv):
    document = load_document(investors_csv, SourceType.INVESTOR_LIST)
    investors = {i.investor_name: i for i in investors_from_rows(document)}
    assert investors["Harbourstone Ventures"].fund_status == FundStatus.BETWEEN_FUNDS
    assert investors["Northlight Diagnostics Fund"].fund_status == FundStatus.ACTIVE


def test_pass_status_is_detected(tmp_path):
    from tests.factories import write_csv

    path = write_csv(
        tmp_path / "passed.csv",
        [{"Investor": "Doubtful Capital", "Status": "Passed - too early", "Check Size": "$1M"}],
    )
    document = load_document(path, SourceType.INVESTOR_LIST)
    investor = investors_from_rows(document)[0]
    assert investor.current_diligence_stage == DiligenceStage.PASS
    assert not investor.is_active_prospect


# --- normalisation -------------------------------------------------------------------------


def test_aliases_resolve_to_one_investor():
    assert same_investor("Andreessen Horowitz", "a16z")
    assert same_investor("A16Z", "a16z")
    # normalise_name drops legal suffixes; identity_key also drops generic fund words.
    assert normalise_name("Northlight Capital LLC") == "northlight capital"
    assert identity_key("Northlight Capital LLC") == "northlight"
    assert same_investor("Northlight Capital LLC", "Northlight Capital")


def test_similar_names_are_not_merged():
    assert not same_investor("Redwood Capital", "Redwood Ventures")
    assert not same_investor("Bay Bridge Ventures", "Golden Gate Ventures")


def test_duplicates_merge_and_keep_the_stronger_evidence():
    from_list = make_investor("Northlight Diagnostics Fund", check=(2e6, 4e6))
    from_notes = make_investor(
        "Northlight Diagnostics",
        check=(None, None),
        lead_history=[("Vessl Dx", "Series A", "led")],
        relationship=Relationship.PARTNER_ENGAGEMENT,
    )
    merged, notes = deduplicate([from_list, from_notes])

    assert len(merged) == 1
    survivor = merged[0]
    assert survivor.estimated_check_max == 4e6
    assert survivor.has_verified_lead_history
    assert survivor.relationship_strength == Relationship.PARTNER_ENGAGEMENT
    assert "Northlight Diagnostics" in survivor.aliases
    assert notes


def test_merging_keeps_every_source():
    a = make_investor("Northlight Diagnostics Fund")
    b = make_investor("Northlight Diagnostics Fund")
    b.sources[0] = SourceRef(source_type=SourceType.MEETING_NOTES, source_name="notes.md", page_or_slide=1)
    merged = merge_investors(a, b)
    assert {s.source_name for s in merged.sources} == {"targets.csv", "notes.md"}


def test_extract_investors_combines_sources(investors_csv, notes_path, deck_path):
    documents = [
        load_document(investors_csv, SourceType.INVESTOR_LIST),
        load_document(notes_path, SourceType.MEETING_NOTES),
    ]
    deck = load_document(deck_path, SourceType.PITCH_DECK)
    investors, _ = extract_investors(documents, deck)
    names = {i.investor_name for i in investors}

    assert "Northlight Diagnostics Fund" in names
    assert len(investors) == 7  # the notes name no one new
    northlight = next(i for i in investors if i.investor_name == "Northlight Diagnostics Fund")
    assert len(northlight.sources) >= 2


def test_unnamed_records_are_skipped(tmp_path):
    from tests.factories import write_csv

    path = write_csv(
        tmp_path / "blank.csv",
        [{"Investor": "", "Check Size": "$1M"}, {"Investor": "Real Fund", "Check Size": "$2M"}],
    )
    document = load_document(path, SourceType.INVESTOR_LIST)
    investors = investors_from_rows(document)
    # The blank row falls back to its only other value rather than inventing a name.
    assert any(i.investor_name == "Real Fund" for i in investors)


def test_source_text_is_preserved_for_every_claim(investors_csv):
    document = load_document(investors_csv, SourceType.INVESTOR_LIST)
    investor = investors_from_rows(document)[1]
    assert investor.sources[0].source_text
    assert investor.sources[0].citation().startswith("targets.csv")
