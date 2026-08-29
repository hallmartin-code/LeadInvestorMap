"""Reporting: the one-page guarantee, JSON fidelity, and the CSV export."""

from __future__ import annotations

import csv
import json

import pypdf
import pytest

from src.analysis.lead_classifier import classify_all
from src.analysis.lead_ranker import build_shortlist, rank
from src.analysis.momentum_analyzer import build_momentum_sequence, identify_highest_pull
from src.analysis.outreach_sequencer import build_sequence
from src.models.analysis import Disqualification, Gap, LeadInvestorMap
from src.models.investor import DisqualificationReason, InvestorType, Relationship
from src.models.round import estimate_lead_requirement
from src.reporting.csv_exporter import export_csv
from src.reporting.json_exporter import export_json, export_sources, load_json
from src.reporting.pdf_generator import render
from tests.factories import make_company, make_investor, make_round


def build_analysis(investor_count: int = 6, gaps: int = 4) -> LeadInvestorMap:
    company = make_company()
    round_ = make_round()
    requirement = estimate_lead_requirement(round_)

    investors = []
    for index in range(investor_count):
        investors.append(
            make_investor(
                f"Investor Number {index} Capital Partners",
                lead_history=[(f"Portfolio Company {index}", "Series A", "led")] if index % 2 == 0 else [],
                check=(2_000_000, 5_000_000) if index % 2 == 0 else (200_000, 800_000),
                investor_type=InvestorType.VC if index % 3 else InvestorType.ANGEL_GROUP,
                relationship=Relationship(index % 9),
            )
        )
    classify_all(investors, round_, requirement, company)
    rank(investors, requirement)

    analysis = LeadInvestorMap(
        company=company,
        round=round_,
        lead_requirement=requirement,
        prospects=investors,
        lead_shortlist=build_shortlist(investors, requirement, round_, company),
    )
    analysis.highest_pull_commitment = identify_highest_pull(investors)
    analysis.momentum_sequence = build_momentum_sequence(investors, analysis.highest_pull_commitment)
    analysis.outreach_sequence = build_sequence(investors)
    analysis.disqualified_as_leads = [
        Disqualification(
            investor_name=i.investor_name,
            reasons=i.disqualification_reasons[:2],
            detail=i.tier_rationale,
        )
        for i in investors
        if i.disqualification_reasons
    ]
    analysis.gaps_and_risks = [
        Gap(
            gap=f"Structural gap number {index} in the prospect pipeline as supplied",
            consequence="A consequence long enough to wrap across more than one line of the table",
            suggested_addition="Add funds that match the missing profile",
            severity="high" if index == 0 else "medium",
        )
        for index in range(gaps)
    ]
    analysis.metadata.input_files = ["deck.pdf", "targets.csv", "notes.md"]
    return analysis


def page_count(path) -> int:
    return len(pypdf.PdfReader(str(path)).pages)


def test_pdf_is_exactly_one_page(tmp_path):
    result = render(build_analysis(), tmp_path / "map.pdf")
    assert result.pages == 1
    assert page_count(result.path) == 1
    assert result.overflow <= 0


def test_pdf_is_landscape(tmp_path):
    result = render(build_analysis(), tmp_path / "map.pdf")
    box = pypdf.PdfReader(str(result.path)).pages[0].mediabox
    assert float(box.width) > float(box.height)


@pytest.mark.parametrize("investor_count,gaps", [(1, 1), (12, 8), (40, 12)])
def test_pdf_stays_one_page_under_pressure(tmp_path, investor_count, gaps):
    analysis = build_analysis(investor_count=investor_count, gaps=gaps)
    result = render(analysis, tmp_path / f"map_{investor_count}.pdf")
    assert page_count(result.path) == 1


def test_overflow_degrades_content_and_says_so(tmp_path):
    analysis = build_analysis(investor_count=40, gaps=12)
    # Long narrative everywhere, to force the ladder down a few rungs.
    for entry in analysis.lead_shortlist:
        entry.why_they_can_lead = "A very long sentence about lead capability. " * 6
        entry.key_obstacle = "An obstacle described at length. " * 6
    result = render(analysis, tmp_path / "dense.pdf")
    assert page_count(result.path) == 1


def test_body_type_never_drops_below_the_readability_floor():
    from src.reporting.fitting import LADDER

    assert min(config.body_size for config in LADDER) >= 7.5


def test_empty_analysis_still_renders(tmp_path):
    analysis = LeadInvestorMap()
    result = render(analysis, tmp_path / "empty.pdf")
    assert page_count(result.path) == 1
    text = pypdf.PdfReader(str(result.path)).pages[0].extract_text()
    assert "NOT PROVIDED" in text


def test_pdf_states_missing_values_rather_than_leaving_blanks(tmp_path):
    analysis = build_analysis()
    analysis.round.target_close = analysis.round.target_close.__class__.missing("Target close")
    result = render(analysis, tmp_path / "map.pdf")
    text = pypdf.PdfReader(str(result.path)).pages[0].extract_text()
    assert "NOT PROVIDED" in text


def test_pdf_marks_unverified_lead_history(tmp_path):
    analysis = build_analysis()
    result = render(analysis, tmp_path / "map.pdf")
    text = pypdf.PdfReader(str(result.path)).pages[0].extract_text()
    assert "LEAD CANDIDATES" in text
    assert "DISQUALIFIED AS LEADS" in text
    assert "MOMENTUM PATH" in text
    assert "OUTREACH SEQUENCE" in text


def test_markup_is_not_shown_as_text(tmp_path):
    result = render(build_analysis(), tmp_path / "map.pdf")
    text = pypdf.PdfReader(str(result.path)).pages[0].extract_text()
    assert "<b>" not in text


def test_json_round_trips(tmp_path):
    analysis = build_analysis()
    path = export_json(analysis, tmp_path / "map.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    for key in (
        "company",
        "round",
        "lead_requirement",
        "prospects",
        "lead_shortlist",
        "highest_pull_commitment",
        "momentum_sequence",
        "disqualified_as_leads",
        "outreach_sequence",
        "gaps_and_risks",
        "fallback_structures",
        "sources",
        "warnings",
    ):
        assert key in payload

    restored = load_json(path)
    assert restored.company.display_name == analysis.company.display_name
    assert len(restored.prospects) == len(analysis.prospects)
    assert restored.prospects[0].lead_score == analysis.prospects[0].lead_score


def test_json_keeps_the_score_breakdown_for_audit(tmp_path):
    analysis = build_analysis()
    payload = json.loads(export_json(analysis, tmp_path / "m.json").read_text(encoding="utf-8"))
    breakdown = payload["prospects"][0]["lead_score_breakdown"]
    assert set(breakdown) >= {"lead_history", "check_size_fit", "stage_fit"}


def test_sources_file_lists_citations_with_freshness(tmp_path):
    analysis = build_analysis()
    path = export_sources(analysis, tmp_path / "sources.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["source_count"] > 0
    first = payload["sources"][0]
    assert {"source_type", "citation", "freshness"} <= set(first)


def test_csv_has_one_row_per_prospect(tmp_path):
    analysis = build_analysis(investor_count=5)
    path = export_csv(analysis, tmp_path / "map.csv")
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 5
    assert rows[0]["investor_name"]
    assert rows[0]["tier"]
    assert rows[0]["lead_history_verified"] in {"YES", "NOT VERIFIED"}
    assert rows[0]["required_next_step"] is not None


def test_csv_reports_unknowns_as_unknown(tmp_path):
    analysis = build_analysis(investor_count=2)
    analysis.prospects[0].can_write_full_lead_check = None
    path = export_csv(analysis, tmp_path / "map.csv")
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["can_write_full_lead_check"] == "UNKNOWN"


def test_disqualification_reasons_survive_to_csv(tmp_path):
    analysis = build_analysis()
    analysis.prospects[0].disqualification_reasons = [DisqualificationReason.NO_VERIFIED_LEAD_HISTORY]
    path = export_csv(analysis, tmp_path / "map.csv")
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert "NO VERIFIED LEAD HISTORY" in rows[0]["disqualification_reasons"]
