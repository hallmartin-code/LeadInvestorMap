"""The blank document template.

Two things have to stay true: the template carries no data from any real analysis, and it
exercises every zone of the layout so it cannot silently stop documenting one.
"""

from __future__ import annotations

import re

import pypdf

from app import cli, write_template
from src.models.investor import LeadConfidence, Tier
from src.reporting.pdf_generator import render
from src.reporting.template import blank_map
from src.utils.config import ExitCode


def text_of(path) -> str:
    return pypdf.PdfReader(str(path)).pages[0].extract_text()


def test_template_renders_one_page_without_degrading(tmp_path):
    result = render(blank_map(), tmp_path / "template.pdf")
    assert result.pages == 1
    assert len(pypdf.PdfReader(str(result.path)).pages) == 1
    # The template must show the full base layout, not a compressed one.
    assert result.dropped == []
    assert result.overflow <= 0


def test_template_shows_every_section(tmp_path):
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    for heading in (
        "LEAD INVESTOR MAP",
        "LEAD CANDIDATES",
        "MOMENTUM PATH",
        "OUTREACH SEQUENCE",
        "DISQUALIFIED AS LEADS",
        "GAPS / RISKS AND REQUIRED ACTION",
        "FALLBACK STRUCTURES IF NO LEAD EMERGES",
    ):
        assert heading in text, f"missing section: {heading}"


def test_template_shows_every_snapshot_tile(tmp_path):
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    for label in (
        "STAGE",
        "RAISE",
        "INSTRUMENT",
        "VALUATION",
        "COMMITTED",
        "REMAINING",
        "TARGET CLOSE",
        "LEAD CHECK REQUIRED",
    ):
        assert label in text, f"missing tile: {label}"


def test_template_shows_every_outreach_phase(tmp_path):
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    for phase in ("NOW:", "NEXT:", "ON MOMENTUM:", "COMPLETION:", "HOLD BACK:"):
        assert phase in text, f"missing phase: {phase}"


def test_template_demonstrates_the_fixed_vocabularies(tmp_path):
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    # Tiers, confidence bands and relationship terms are the vocabulary a real analysis
    # draws from, so the template prints the terms themselves rather than placeholders.
    assert "T1 LEAD" in text and "T2 CO-LEAD" in text
    for band in ("HIGH", "MEDIUM", "LOW"):
        assert band in text
    assert "NOT VERIFIED" in text
    assert "STRATEGIC ONLY" in text
    assert "NO VERIFIED LEAD HISTORY" in text
    assert "BETWEEN FUNDS" in text
    assert "PORTFOLIO CONFLICT" in text


def test_template_exercises_every_tier(tmp_path):
    analysis = blank_map()
    tiers = {investor.tier for investor in analysis.prospects}
    assert tiers == set(Tier)


def test_template_exercises_every_lead_confidence_band(tmp_path):
    analysis = blank_map()
    bands = {entry.lead_confidence for entry in analysis.lead_shortlist}
    assert bands == {LeadConfidence.HIGH, LeadConfidence.MEDIUM, LeadConfidence.LOW}


def test_template_shows_both_verified_and_unverified_lead_history():
    analysis = blank_map()
    verified = [e for e in analysis.lead_shortlist if e.lead_evidence != "NOT VERIFIED"]
    unverified = [e for e in analysis.lead_shortlist if e.lead_evidence == "NOT VERIFIED"]
    assert verified and unverified


def test_template_carries_no_company_or_investor_data(tmp_path):
    """Nothing from the sample scenario, or any other analysis, may leak into the template."""
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    forbidden = (
        "Helios",
        "Meridian",
        "Northlight",
        "Sequoia",
        "Grandview",
        "Cobalt",
        "Harbourstone",
        "Kestrel",
        "Ironwood",
        "Bay Angels",
        "Longview",
        "Pinnacle",
        "Inflammatix",
        "Vessl",
        "sepsis",
        "diagnostics",
    )
    for term in forbidden:
        assert term.lower() not in text.lower(), f"template leaked scenario data: {term}"


def test_template_contains_no_concrete_figures(tmp_path):
    """No amounts, dates or scores - only slots and vocabulary."""
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    assert not re.search(r"\$\s?\d", text), "template shows a currency amount"
    assert not re.search(r"\b(19|20)\d{2}\b", text), "template shows a calendar year"
    assert not re.search(r"\b\d+\.\d\b", text), "template shows a decimal score"


def test_every_slot_is_marked_as_a_slot(tmp_path):
    text = text_of(render(blank_map(), tmp_path / "template.pdf").path)
    assert text.count("[") >= 30, "template should be dense with bracketed field slots"
    assert "[COMPANY NAME]" in text
    assert "[LEAD CANDIDATE 1]" in text
    assert "[STAGE]" in text


def test_template_json_round_trips():
    """The template is a valid analysis object, so it can seed a run or a fixture."""
    import tempfile
    from pathlib import Path

    from src.reporting.json_exporter import export_json, load_json

    with tempfile.TemporaryDirectory() as directory:
        path = export_json(blank_map(), Path(directory) / "template.json")
        restored = load_json(path)
    assert restored.company.name.value == "[COMPANY NAME]"
    assert len(restored.prospects) == len(blank_map().prospects)


def test_cli_writes_the_template(tmp_path, capsys):
    code = write_template("template.pdf", tmp_path)
    assert code == int(ExitCode.OK)
    assert (tmp_path / "template.pdf").exists()
    assert "no company data" in capsys.readouterr().out.lower()


def test_cli_template_flag_takes_a_default_name(tmp_path, capsys):
    code = cli(["--template", "--out", str(tmp_path)])
    assert code == int(ExitCode.OK)
    assert (tmp_path / "lead_investor_map_TEMPLATE.pdf").exists()


def test_cli_template_flag_ignores_analysis_arguments(tmp_path):
    """--template is a structural export; it must not require or read a deck."""
    code = cli(["--template", "--out", str(tmp_path), "--deck", str(tmp_path / "missing.pdf")])
    assert code == int(ExitCode.OK)
    assert (tmp_path / "lead_investor_map_TEMPLATE.pdf").exists()
