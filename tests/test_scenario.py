"""The end-to-end scenario from section 47 of the specification.

One run over one deck and one target list has to get all seven of these right at once:

* a famous fund participates but does not lead;
* a smaller specialist fund has actual lead history;
* a strategic has strong signal value but cannot lead;
* a follower requires another lead;
* a fund is between funds;
* a warm introduction exists to one candidate;
* one investor has a portfolio conflict.
"""

from __future__ import annotations

import pypdf
import pytest

from src.models.investor import (
    ConflictLevel,
    DisqualificationReason,
    FundStatus,
    Relationship,
    SignalValue,
    Tier,
)
from src.pipeline import PipelineOptions, run


@pytest.fixture(scope="function")
def result(deck_path, investors_csv, notes_path, tmp_path):
    return run(
        PipelineOptions(
            deck_path=deck_path,
            supporting_paths=[investors_csv, notes_path],
            use_llm=False,
            output_directory=tmp_path / "out",
        )
    )


@pytest.fixture
def analysis(result):
    return result.analysis


def prospect(analysis, name):
    found = analysis.prospect(name)
    assert found is not None, f"{name} is missing from the prospect list"
    return found


# --- the round -------------------------------------------------------------------------------


def test_round_is_read_from_the_deck(analysis):
    assert analysis.round.stage.value == "Series A"
    assert analysis.round.raise_amount.numeric_value == 6_000_000
    assert analysis.round.committed.numeric_value == 1_500_000
    assert analysis.round.remaining.numeric_value == 4_500_000
    assert analysis.lead_requirement.is_known


# --- the seven traps ---------------------------------------------------------------------------


def test_famous_participant_is_not_promoted_to_lead(analysis):
    bigname = prospect(analysis, "Bigname Global Partners")
    assert bigname.tier != Tier.POTENTIAL_LEAD
    assert not bigname.has_verified_lead_history
    assert DisqualificationReason.NO_VERIFIED_LEAD_HISTORY in bigname.disqualification_reasons
    assert bigname.investor_name not in [e.investor_name for e in analysis.lead_shortlist]


def test_specialist_with_real_lead_history_is_a_lead_candidate(analysis):
    northlight = prospect(analysis, "Northlight Diagnostics Fund")
    assert northlight.tier in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}
    assert northlight.has_verified_lead_history
    assert "Vessl Dx" in northlight.lead_history_display(2)
    assert northlight.investor_name in [e.investor_name for e in analysis.lead_shortlist]


def test_specialist_outranks_the_famous_fund(analysis):
    northlight = prospect(analysis, "Northlight Diagnostics Fund")
    bigname = prospect(analysis, "Bigname Global Partners")
    assert (northlight.lead_score or 0) > (bigname.lead_score or 0)


def test_strategic_has_signal_but_is_not_a_lead(analysis):
    grandview = prospect(analysis, "Grandview Strategic Ventures")
    assert grandview.tier == Tier.STRATEGIC_VALIDATOR
    assert grandview.signal_value in {SignalValue.HIGH, SignalValue.VERY_HIGH}
    assert DisqualificationReason.STRATEGIC_ONLY in grandview.disqualification_reasons


def test_follower_requires_a_lead(analysis):
    follower = prospect(analysis, "Followell Capital")
    assert follower.tier == Tier.FOLLOW_ON
    assert "Lead investor secured" in follower.dependencies
    assert "Requires lead in place" in follower.tier_rationale


def test_fund_between_funds_is_excluded_from_leading(analysis):
    harbourstone = prospect(analysis, "Harbourstone Ventures")
    assert harbourstone.fund_status == FundStatus.BETWEEN_FUNDS
    assert harbourstone.tier not in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}
    assert DisqualificationReason.BETWEEN_FUNDS in harbourstone.disqualification_reasons
    sequence = analysis.outreach_sequence
    assert harbourstone.investor_name not in sequence.phase_1.investors
    assert harbourstone.investor_name not in sequence.phase_2.investors


def test_the_warm_introduction_is_recorded_with_its_path(analysis):
    northlight = prospect(analysis, "Northlight Diagnostics Fund")
    assert northlight.relationship_strength >= Relationship.WARM_INTRO_AVAILABLE
    assert northlight.warm_intro_path and "Patel" in northlight.warm_intro_path
    assert northlight.warm_intro_verified


def test_the_portfolio_conflict_is_found_and_acted_on(analysis):
    cobalt = prospect(analysis, "Cobalt Ridge Capital")
    assert cobalt.conflict_level == ConflictLevel.HIGH
    assert any(c.company == "Inflammatix" for c in cobalt.portfolio_conflicts)
    assert cobalt.tier != Tier.POTENTIAL_LEAD
    assert cobalt.investor_name in analysis.outreach_sequence.hold_back.investors


# --- the derived analysis -----------------------------------------------------------------------


def test_every_prospect_has_exactly_one_tier(analysis):
    assert analysis.prospects
    assert all(p.tier is not None for p in analysis.prospects)


def test_shortlist_is_only_as_long_as_the_evidence_allows(analysis):
    assert 0 < len(analysis.lead_shortlist) <= 8
    for entry in analysis.lead_shortlist:
        assert entry.why_they_can_lead and entry.key_obstacle
        assert entry.required_next_step and entry.next_step_owner


def test_highest_pull_and_momentum_use_real_prospects(analysis):
    names = {p.investor_name for p in analysis.prospects}
    pull = analysis.highest_pull_commitment
    assert pull.investor_name in names
    for step in analysis.momentum_sequence:
        for name in step.investor_name.split(", "):
            assert name in names or name.endswith("...")
    for downstream in pull.downstream_investors:
        assert downstream in names


def test_outreach_sequence_does_not_contact_everyone_at_once(analysis):
    sequence = analysis.outreach_sequence
    phase_1 = set(sequence.phase_1.investors)
    phase_2 = set(sequence.phase_2.investors)
    assert not (phase_1 & phase_2)
    assert not (set(sequence.hold_back.investors) & phase_2)


def test_gaps_are_identified_with_consequences(analysis):
    assert analysis.gaps_and_risks
    assert all(gap.gap and gap.consequence for gap in analysis.gaps_and_risks)


def test_objections_come_from_the_deck(analysis):
    assert analysis.company.objections
    assert all(o.is_grounded for o in analysis.company.objections)


def test_no_llm_run_says_so_rather_than_inventing(analysis):
    assert any("rule-based" in w.message for w in analysis.warnings)
    assert analysis.metadata.llm_provider.startswith("none")


def test_every_output_file_is_written(result):
    for path in (result.pdf_path, result.json_path, result.sources_path, result.csv_path):
        assert path is not None and path.exists() and path.stat().st_size > 0


def test_the_pdf_is_one_page(result):
    assert len(pypdf.PdfReader(str(result.pdf_path)).pages) == 1


def test_claims_retain_their_sources(analysis):
    assert analysis.round.raise_amount.sources
    assert analysis.round.raise_amount.sources[0].page_or_slide == 4
    northlight = prospect(analysis, "Northlight Diagnostics Fund")
    assert northlight.sources
    assert all(s.source_name for s in northlight.sources)


def test_analysis_survives_a_missing_investor_list(deck_path, tmp_path):
    result = run(
        PipelineOptions(
            deck_path=deck_path,
            supporting_paths=[],
            use_llm=False,
            output_directory=tmp_path / "out2",
        )
    )
    analysis = result.analysis
    assert analysis.prospects == []
    assert analysis.lead_shortlist == []
    assert any("No investor prospects" in w.message for w in analysis.warnings)
    assert result.pdf_path.exists()


def test_analysis_survives_a_missing_deck(investors_csv, tmp_path):
    result = run(
        PipelineOptions(
            deck_path=None,
            supporting_paths=[investors_csv],
            use_llm=False,
            output_directory=tmp_path / "out3",
        )
    )
    analysis = result.analysis
    assert analysis.prospects
    assert analysis.round.raise_amount.display() == "NOT PROVIDED"
    assert not analysis.lead_requirement.is_known
    assert result.pdf_path.exists()


def test_user_overrides_reach_the_output(deck_path, investors_csv, tmp_path):
    result = run(
        PipelineOptions(
            deck_path=deck_path,
            supporting_paths=[investors_csv],
            round_overrides={"raise_amount": "$10M", "target_close": "March 2027"},
            use_llm=False,
            output_directory=tmp_path / "out4",
        )
    )
    analysis = result.analysis
    assert analysis.round.raise_amount.numeric_value == 10_000_000
    assert analysis.round.raise_amount.status.value == "USER PROVIDED"
    # The lead requirement follows the corrected round size.
    assert analysis.lead_requirement.remaining_raise == 8_500_000
