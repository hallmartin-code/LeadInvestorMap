"""Classification, ranking, conflicts, momentum, sequencing and gaps."""

from __future__ import annotations

import pytest

from src.analysis.conflict_analyzer import analyse_conflicts
from src.analysis.gap_analyzer import analyse_gaps, evaluate_fallbacks
from src.analysis.lead_classifier import (
    assess_sector_fit,
    assess_stage_fit,
    assess_timeline,
    classify_all,
)
from src.analysis.lead_ranker import build_shortlist, rank, score_investor, weighted_score
from src.analysis.momentum_analyzer import (
    apply_next_steps,
    build_momentum_sequence,
    identify_highest_pull,
)
from src.analysis.objection_analyzer import generate_objections_rule_based
from src.analysis.outreach_sequencer import build_sequence, derive_dependencies
from src.models.investor import (
    ConflictLevel,
    DiligenceStage,
    DisqualificationReason,
    Fit,
    FundStatus,
    InvestorType,
    LeadConfidence,
    Relationship,
    Tier,
)
from src.models.round import estimate_lead_requirement
from tests.factories import make_company, make_investor, make_round


@pytest.fixture
def context():
    round_ = make_round(raise_amount=6_000_000, committed=1_500_000)
    return make_company(), round_, estimate_lead_requirement(round_)


def _classified(investors, context):
    company, round_, requirement = context
    classify_all(investors, round_, requirement, company)
    rank(investors, requirement)
    return {i.investor_name: i for i in investors}


# --- tiering -------------------------------------------------------------------------------


def test_a_fund_with_lead_history_and_capacity_is_tier_one(context):
    investor = make_investor(
        "Northlight Diagnostics Fund",
        check=(2_000_000, 4_000_000),
        lead_history=[("Vessl Dx", "Series A", "led")],
    )
    result = _classified([investor], context)["Northlight Diagnostics Fund"]
    assert result.tier == Tier.POTENTIAL_LEAD
    assert result.lead_confidence in {LeadConfidence.HIGH, LeadConfidence.MEDIUM}


def test_a_famous_fund_that_only_participated_is_not_a_lead(context):
    investor = make_investor(
        "Bigname Global Partners",
        check=(5_000_000, 20_000_000),
        entry_stages=["Series B", "Series C"],
        lead_history=[("Inflammatix", "Series C", "participated")],
        relationship=Relationship.COLD,
        diligence=DiligenceStage.COLD,
    )
    result = _classified([investor], context)["Bigname Global Partners"]

    assert result.tier != Tier.POTENTIAL_LEAD
    assert DisqualificationReason.NO_VERIFIED_LEAD_HISTORY in result.disqualification_reasons
    assert result.lead_history_display() == "NOT VERIFIED"


def test_a_cheque_below_the_lead_requirement_becomes_a_co_lead(context):
    investor = make_investor(
        "Small Specialist Fund",
        check=(500_000, 1_000_000),
        lead_history=[("Vessl Dx", "Series A", "led")],
    )
    result = _classified([investor], context)["Small Specialist Fund"]
    assert result.tier == Tier.CO_LEAD
    assert DisqualificationReason.CHECK_TOO_SMALL in result.disqualification_reasons


def test_a_strategic_is_tier_three_however_engaged(context):
    investor = make_investor(
        "Grandview Strategic Ventures",
        investor_type=InvestorType.CORPORATE,
        check=(1_000_000, 3_000_000),
        relationship=Relationship.ACTIVE_DILIGENCE,
        diligence=DiligenceStage.DILIGENCE,
        stated_dependencies=["Lead investor secured"],
    )
    result = _classified([investor], context)["Grandview Strategic Ventures"]
    assert result.tier == Tier.STRATEGIC_VALIDATOR
    assert DisqualificationReason.STRATEGIC_ONLY in result.disqualification_reasons


def test_a_follower_is_tier_four_and_needs_a_lead(context):
    investor = make_investor("Followell Capital", check=(1_000_000, 2_000_000), leads_rounds_stated=False)
    result = _classified([investor], context)["Followell Capital"]
    assert result.tier == Tier.FOLLOW_ON
    assert "Lead investor secured" in result.dependencies
    assert DisqualificationReason.REQUIRES_EXISTING_LEAD in result.disqualification_reasons


def test_a_fund_between_funds_cannot_lead(context):
    investor = make_investor(
        "Harbourstone Ventures",
        check=(2_000_000, 4_000_000),
        lead_history=[("Pulsewave", "Series A", "co-led")],
        fund_status=FundStatus.BETWEEN_FUNDS,
    )
    result = _classified([investor], context)["Harbourstone Ventures"]
    assert result.tier not in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}
    assert DisqualificationReason.BETWEEN_FUNDS in result.disqualification_reasons


def test_an_angel_group_is_tier_five_or_six(context):
    investor = make_investor(
        "Bay Angels Collective",
        investor_type=InvestorType.ANGEL_GROUP,
        check=(100_000, 250_000),
    )
    result = _classified([investor], context)["Bay Angels Collective"]
    assert result.tier in {Tier.ANGEL_FAMILY_SYNDICATE, Tier.FILL_THE_ROUND}


def test_small_cheques_are_fill_the_round(context):
    investor = make_investor(
        "Tiny Syndicate",
        investor_type=InvestorType.SYNDICATE,
        check=(50_000, 150_000),  # under 5% of a $6M round
    )
    result = _classified([investor], context)["Tiny Syndicate"]
    assert result.tier == Tier.FILL_THE_ROUND


def test_every_prospect_gets_exactly_one_tier(context):
    investors = [
        make_investor("A", lead_history=[("X", "Series A", "led")]),
        make_investor("B", investor_type=InvestorType.ANGEL, check=(50_000, 100_000)),
        make_investor("C", investor_type=InvestorType.CORPORATE),
        make_investor("D", investor_type=InvestorType.UNKNOWN, check=(None, None)),
    ]
    results = _classified(investors, context)
    assert all(i.tier is not None for i in results.values())
    assert len({i.investor_name for i in results.values()}) == 4


# --- fit -----------------------------------------------------------------------------------


def test_portfolio_stage_does_not_establish_entry_stage(context):
    _, round_, _ = context
    investor = make_investor("Seed Only Fund", entry_stages=["Pre-Seed", "Seed"])
    investor.supporting_portfolio_companies = ["A Series B company"]
    assess_stage_fit(investor, round_)
    assert investor.stage_fit == Fit.PARTIAL  # seed is adjacent to Series A, not a match


def test_wrong_stage_is_a_mismatch(context):
    _, round_, _ = context
    investor = make_investor("Growth Fund", entry_stages=["Series C", "Series D"])
    assess_stage_fit(investor, round_)
    assert investor.stage_fit == Fit.MISMATCH


def test_sector_fit_uses_stated_focus_not_prose(context):
    company, _, _ = context
    investor = make_investor(
        "Software Fund",
        sector_focus="enterprise software, fintech",
        notes="No life sciences investments identified.",
    )
    assess_sector_fit(investor, company)
    assert investor.sector_fit == Fit.WEAK


def test_sector_fit_matches_on_significant_words(context):
    company, _, _ = context
    investor = make_investor("Diagnostics Fund", sector_focus="diagnostics, medical devices")
    assess_sector_fit(investor, company)
    assert investor.sector_fit == Fit.STRONG
    assert "Matched" in investor.sector_fit_detail


def test_timeline_is_unknown_without_a_close_date():
    round_ = make_round(target_close=None)
    investor = make_investor("Any Fund")
    assess_timeline(investor, round_)
    assert investor.timeline_compatible is None
    assert "estimated" in investor.estimated_time_to_term_sheet


# --- conflicts ------------------------------------------------------------------------------


def test_a_named_competitor_in_the_portfolio_is_a_high_conflict():
    company = make_company(competitors=["Inflammatix"])
    investor = make_investor("Cobalt Ridge Capital", portfolio=["Inflammatix", "Verity Molecular"])
    analyse_conflicts(investor, company)
    assert investor.conflict_level == ConflictLevel.HIGH
    assert investor.portfolio_conflicts[0].company == "Inflammatix"


def test_the_same_broad_sector_is_not_a_conflict():
    company = make_company(competitors=["Inflammatix"])
    investor = make_investor("Other Diagnostics Fund", portfolio=["Vessl Dx", "Coriolis"])
    analyse_conflicts(investor, company)
    assert investor.conflict_level == ConflictLevel.NONE


def test_an_unknown_portfolio_stays_unknown():
    company = make_company(competitors=["Inflammatix"])
    investor = make_investor("Opaque Fund", portfolio=[])
    analyse_conflicts(investor, company)
    assert investor.conflict_level == ConflictLevel.UNKNOWN


# --- scoring --------------------------------------------------------------------------------


def test_unknown_evidence_scores_neither_zero_nor_full(context):
    _, _, requirement = context
    unknown = make_investor("Opaque Fund", check=(None, None), fund_status=FundStatus.UNKNOWN)
    breakdown = score_investor(unknown, requirement)
    assert 0 < breakdown["check_size_fit"] < 100
    assert 0 < breakdown["lead_history"] < 100


def test_weights_sum_to_one_hundred():
    from src.utils.config import LEAD_SCORE_WEIGHTS

    assert abs(sum(LEAD_SCORE_WEIGHTS.values()) - 1.0) < 1e-9
    assert weighted_score({key: 100.0 for key in LEAD_SCORE_WEIGHTS}) == 100.0


def test_high_confidence_requires_verified_lead_history(context):
    investor = make_investor(
        "Confident But Unproven",
        check=(3_000_000, 6_000_000),
        leads_rounds_stated=True,
        relationship=Relationship.VERBAL_INTEREST,
    )
    result = _classified([investor], context)["Confident But Unproven"]
    assert result.lead_confidence != LeadConfidence.HIGH


def test_shortlist_is_not_padded(context):
    company, round_, requirement = context
    investors = [
        make_investor("Only Real Lead", lead_history=[("X", "Series A", "led")]),
        make_investor("Follower", leads_rounds_stated=False),
        make_investor("Angel", investor_type=InvestorType.ANGEL, check=(50_000, 100_000)),
    ]
    _classified(investors, context)
    shortlist = build_shortlist(investors, requirement, round_, company)
    assert len(shortlist) == 1
    assert shortlist[0].investor_name == "Only Real Lead"


def test_shortlist_caps_at_eight(context):
    company, round_, requirement = context
    investors = [
        make_investor(f"Fund {index}", lead_history=[(f"Deal {index}", "Series A", "led")])
        for index in range(12)
    ]
    _classified(investors, context)
    shortlist = build_shortlist(investors, requirement, round_, company)
    assert len(shortlist) == 8
    assert [e.rank for e in shortlist] == list(range(1, 9))


# --- momentum and sequencing -------------------------------------------------------------------


def test_highest_pull_prefers_evidenced_leads_with_downstream_effect(context):
    investors = [
        make_investor("Real Lead", lead_history=[("X", "Series A", "led")]),
        make_investor("Follower One", leads_rounds_stated=False),
        make_investor("Follower Two", leads_rounds_stated=False),
        make_investor("Follower Three", leads_rounds_stated=False),
    ]
    _classified(investors, context)
    derive_dependencies(investors, has_credible_lead=True)
    pull = identify_highest_pull(investors)

    assert pull.investor_name == "Real Lead"
    assert pull.confidence == "HIGH"
    assert len(pull.downstream_investors) == 3


def test_momentum_excludes_committed_money(context):
    lead = make_investor("Real Lead", lead_history=[("X", "Series A", "led")])
    committed = make_investor(
        "Already In",
        leads_rounds_stated=False,
        relationship=Relationship.COMMITTED,
        diligence=DiligenceStage.COMMITTED,
    )
    waiting = make_investor("Waiting Fund", leads_rounds_stated=False)
    investors = [lead, committed, waiting]
    _classified(investors, context)
    derive_dependencies(investors, has_credible_lead=True)

    steps = build_momentum_sequence(investors, identify_highest_pull(investors))
    named = " ".join(s.investor_name for s in steps)
    assert "Already In" not in named
    assert "Waiting Fund" in named


def test_no_pull_when_nothing_can_lead(context):
    investors = [make_investor("Angel", investor_type=InvestorType.ANGEL, check=(50_000, 90_000))]
    _classified(investors, context)
    pull = identify_highest_pull(investors)
    assert pull.investor_name is None
    assert pull.confidence == "INSUFFICIENT EVIDENCE"


def test_the_best_lead_is_never_spent_on_calibration(context):
    """Phase 1 exists to test the pitch on conversations the round can afford to lose."""
    strong_lead = make_investor(
        "Cold Strong Lead",
        lead_history=[("X", "Series A", "led"), ("Y", "Series A", "led")],
        relationship=Relationship.COLD,
        diligence=DiligenceStage.COLD,
        check=(3_000_000, 6_000_000),
    )
    replaceable = make_investor(
        "Partial Lead",
        leads_rounds_stated=True,
        check=(500_000, 900_000),
        relationship=Relationship.INTRO_MADE,
        diligence=DiligenceStage.INTRO_MADE,
    )
    investors = [strong_lead, replaceable]
    _classified(investors, context)
    sequence = build_sequence(investors)

    assert "Cold Strong Lead" not in sequence.phase_1.investors
    assert "Cold Strong Lead" in sequence.phase_2.investors


def test_cold_strategics_are_held_back(context):
    strategic = make_investor(
        "Cold Strategic",
        investor_type=InvestorType.CORPORATE,
        relationship=Relationship.COLD,
        diligence=DiligenceStage.COLD,
    )
    lead = make_investor("Real Lead", lead_history=[("X", "Series A", "led")])
    investors = [strategic, lead]
    _classified(investors, context)
    sequence = build_sequence(investors)

    assert "Cold Strategic" in sequence.hold_back.investors
    assert "Cold Strategic" not in sequence.phase_3.investors


def test_conflicted_investors_are_held_back(context):
    company = make_company(competitors=["Inflammatix"])
    conflicted = make_investor(
        "Cobalt Ridge Capital",
        portfolio=["Inflammatix"],
        lead_history=[("Verity", "Series A", "led")],
        relationship=Relationship.INTRO_MADE,
        diligence=DiligenceStage.INTRO_MADE,
    )
    _, round_, requirement = context
    classify_all([conflicted], round_, requirement, company)
    rank([conflicted], requirement)
    sequence = build_sequence([conflicted])
    assert "Cobalt Ridge Capital" in sequence.hold_back.investors


def test_every_active_prospect_gets_one_next_step(context):
    investors = [
        make_investor("A", lead_history=[("X", "Series A", "led")]),
        make_investor("B", relationship=Relationship.COLD, diligence=DiligenceStage.COLD),
        make_investor("C", check=(None, None)),
    ]
    _classified(investors, context)
    apply_next_steps(investors)
    assert all(i.required_next_step and i.next_step_owner for i in investors)


# --- gaps and fallbacks --------------------------------------------------------------------------


def test_gaps_name_their_consequence(context):
    company, round_, requirement = context
    investors = [make_investor("Follower", leads_rounds_stated=False, check=(200_000, 400_000))]
    _classified(investors, context)
    gaps = analyse_gaps(investors, round_, requirement, company)

    assert gaps
    assert all(gap.consequence for gap in gaps)
    assert any("no prospect" in gap.gap.lower() for gap in gaps)


def test_fallbacks_are_offered_only_when_no_lead_exists(context):
    company, round_, requirement = context
    strong = [make_investor("Real Lead", lead_history=[("X", "Series A", "led")])]
    _classified(strong, context)
    assert evaluate_fallbacks(strong, round_, requirement) == []

    weak = [
        make_investor(f"Follower {i}", leads_rounds_stated=False, check=(1_000_000, 2_000_000))
        for i in range(4)
    ]
    _classified(weak, context)
    structures = evaluate_fallbacks(weak, round_, requirement)
    assert any(s.structure == "Party round" for s in structures)
    assert all(s.primary_risk and s.milestone_required for s in structures)


def test_objections_are_tied_to_deck_content(deck_path, context):
    from src.ingestion.loader import load_document
    from src.models.evidence import SourceType

    company, round_, _ = context
    deck = load_document(deck_path, SourceType.PITCH_DECK)
    objections = generate_objections_rule_based(company, round_, deck)

    assert objections
    assert all(o.is_grounded for o in objections)
    assert any("revenue" in o.category or "runway" in o.category for o in objections)


def test_no_deck_produces_no_invented_objections(context):
    company, round_, _ = context
    assert generate_objections_rule_based(company, round_, None) == []


def test_the_momentum_anchor_is_described_as_what_it_is(context):
    """A strategic that cannot lead must not be shown as committing as lead."""
    strategic = make_investor(
        "Grandview Strategic Ventures",
        investor_type=InvestorType.CORPORATE,
        relationship=Relationship.ACTIVE_DILIGENCE,
        diligence=DiligenceStage.DILIGENCE,
    )
    follower = make_investor("Followell Capital", leads_rounds_stated=False)
    investors = [strategic, follower]
    _classified(investors, context)
    derive_dependencies(investors, has_credible_lead=False)

    steps = build_momentum_sequence(investors, identify_highest_pull(investors))
    assert steps[0].investor_name == "Grandview Strategic Ventures"
    assert steps[0].event == "commits as strategic anchor"
    assert "does not price" in steps[0].effect


def test_a_co_lead_anchor_is_not_called_a_lead(context):
    co_lead = make_investor(
        "Small Specialist Fund",
        check=(500_000, 1_000_000),
        lead_history=[("Vessl Dx", "Series A", "led")],
    )
    _classified([co_lead], context)
    steps = build_momentum_sequence([co_lead], identify_highest_pull([co_lead]))
    assert steps[0].event == "commits as co-lead"
