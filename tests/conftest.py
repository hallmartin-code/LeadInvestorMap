"""Shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.factories import write_csv, write_pdf  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Every test runs with no credentials, no research and no email, unless it says otherwise.

    The email lockdown is not optional: the pipeline emails by default, a developer's
    ``.env`` carries a live Resend key, and a test suite that quietly mails Info@ every
    time someone runs pytest would be intolerable. Both the key and the feature flag are
    cleared, so a send needs two deliberate overrides to happen.
    """
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("ENABLE_PUBLIC_RESEARCH", "false")
    monkeypatch.setenv("RESEARCH_BACKEND", "none")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("ENABLE_EMAIL", "false")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    yield


@pytest.fixture
def deck_path(tmp_path) -> Path:
    return write_pdf(
        tmp_path / "testco_deck.pdf",
        [
            ["Testco", "Rapid sepsis detection for hospitals"],
            [
                "Traction",
                "3 paying hospital pilots signed in 2026",
                "$480,000 in pilot revenue booked",
            ],
            [
                "Competition",
                "Inflammatix is the closest direct competitor",
                "Cepheid competes on pathogen identification",
            ],
            [
                "The ask",
                "Raising $6M Series A in priced equity at a $22M pre-money valuation.",
                "$1.5M committed from existing investors.",
                "$400k soft-circled from angels.",
                "Target close December 2026.",
            ],
        ],
    )


@pytest.fixture
def investors_csv(tmp_path) -> Path:
    """The seven-trap scenario from the specification, as a target list."""
    return write_csv(
        tmp_path / "targets.csv",
        [
            {
                "Investor": "Bigname Global Partners",
                "Type": "Venture Fund",
                "Check Size": "$5M-$20M",
                "Stage Focus": "Series B, Series C",
                "Sector Focus": "healthcare, diagnostics",
                "Leads Rounds": "Yes",
                "Lead History": "",
                "Relationship": "Cold",
                "Status": "Cold",
                "Fund Status": "Fund IX 2025, active",
                "Portfolio": "Verity Molecular",
                "Notes": "Participated in the Inflammatix Series C but did not lead it.",
            },
            {
                "Investor": "Northlight Diagnostics Fund",
                "Type": "Micro VC",
                "Check Size": "$2M-$4M",
                "Stage Focus": "Seed, Series A",
                "Sector Focus": "diagnostics, sepsis, clinical tools",
                "Leads Rounds": "Yes",
                "Lead History": "Led Vessl Dx Series A 2025; led Coriolis Seed 2024",
                "Relationship": "Warm intro available via Dr Patel",
                "Status": "First meeting",
                "Fund Status": "Fund II 2025, actively deploying",
                "Portfolio": "Vessl Dx, Coriolis",
                "Notes": "Specialist diagnostics fund, prefers to lead at Series A.",
            },
            {
                "Investor": "Grandview Strategic Ventures",
                "Type": "Corporate / CVC",
                "Check Size": "$1M-$3M",
                "Stage Focus": "Series A",
                "Sector Focus": "hospital diagnostics",
                "Leads Rounds": "No - follows a financial lead",
                "Lead History": "",
                "Relationship": "Active diligence",
                "Status": "Diligence",
                "Fund Status": "Corporate balance sheet, active",
                "Portfolio": "Labtrace",
                "Notes": "Strategic arm of an analyser maker. Needs a financial lead in place.",
            },
            {
                "Investor": "Followell Capital",
                "Type": "Venture Fund",
                "Check Size": "$1M-$2M",
                "Stage Focus": "Series A",
                "Sector Focus": "diagnostics",
                "Leads Rounds": "No",
                "Lead History": "",
                "Relationship": "Intro made",
                "Status": "First meeting",
                "Fund Status": "Fund III 2024, active",
                "Portfolio": "",
                "Notes": "Will follow once a lead is in place.",
            },
            {
                "Investor": "Harbourstone Ventures",
                "Type": "Venture Fund",
                "Check Size": "$2M-$4M",
                "Stage Focus": "Series A",
                "Sector Focus": "medtech, diagnostics",
                "Leads Rounds": "Yes",
                "Lead History": "Co-led Pulsewave Series A 2023",
                "Relationship": "Second meeting",
                "Status": "Follow-up",
                "Fund Status": "Between funds - Fund III raising, no dry powder until 2028",
                "Portfolio": "Pulsewave",
                "Notes": "Interested but between funds.",
            },
            {
                "Investor": "Cobalt Ridge Capital",
                "Type": "Venture Fund",
                "Check Size": "$3M-$5M",
                "Stage Focus": "Series A",
                "Sector Focus": "diagnostics, molecular testing",
                "Leads Rounds": "Yes",
                "Lead History": "Led Verity Molecular Series A 2024",
                "Relationship": "Intro made",
                "Status": "First meeting",
                "Fund Status": "Fund III 2025, active",
                "Portfolio": "Inflammatix, Verity Molecular",
                "Notes": "Holds Inflammatix, a direct competitor.",
            },
            {
                "Investor": "Bay Angels Collective",
                "Type": "Angel Group",
                "Check Size": "$100k-$250k",
                "Stage Focus": "Seed, Series A",
                "Sector Focus": "healthcare",
                "Leads Rounds": "No",
                "Lead History": "",
                "Relationship": "Verbal interest",
                "Status": "Verbal",
                "Fund Status": "Active",
                "Portfolio": "",
                "Notes": "Syndicates to members once a lead is named.",
            },
        ],
    )


@pytest.fixture
def notes_path(tmp_path) -> Path:
    path = tmp_path / "investor_meeting_notes.md"
    path.write_text(
        "## Northlight Diagnostics Fund - 14 July 2026\n"
        "Northlight led the Vessl Dx Series A in 2025 and took a board seat. They can write "
        "up to $4M and prefer to lead at Series A. Warm introduction via Dr Patel.\n\n"
        "## Bigname Global Partners\n"
        "Bigname Global Partners participated in the Inflammatix Series C but did not lead "
        "it. No relationship today.\n\n"
        "## Grandview Strategic Ventures - 20 June 2026\n"
        "Grandview Strategic Ventures confirmed they will not lead and need a lead in place "
        "first.\n",
        encoding="utf-8",
    )
    return path
