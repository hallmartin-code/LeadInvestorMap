"""Generate the synthetic sample inputs used by the README walkthrough and the tests.

The scenario is deliberately built to contain the traps the application exists to catch:
a famous fund that only ever participated, a small specialist that has genuinely led, a
strategic with high signal and no ability to lead, a follower that needs a lead, a fund
between funds, one warm introduction, and one portfolio conflict.

Run:  python sample_data/make_samples.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdfcanvas

HERE = Path(__file__).resolve().parent

DECK_SLIDES: list[tuple[str, list[str]]] = [
    (
        "Helios Diagnostics",
        [
            "Rapid bedside detection of sepsis, 4 hours before current standard of care",
            "Series A investor presentation",
        ],
    ),
    (
        "The problem",
        [
            "Sepsis kills 350,000 adults in the United States each year.",
            "Diagnosis today relies on blood culture, which takes 24-48 hours.",
            "Each hour of delayed antibiotics raises mortality by roughly 8 percent.",
            "US hospitals spend $62B a year on sepsis care (HCUP, 2024).",
        ],
    ),
    (
        "Our solution",
        [
            "Helios Rapid Panel is a cartridge-based host-response assay.",
            "Whole blood in, risk score out, in 55 minutes on existing analysers.",
            "Runs on the installed base of analysers already in 4,100 US hospitals.",
        ],
    ),
    (
        "Clinical validation",
        [
            "Prospective study across 3 academic centres, 512 enrolled patients.",
            "Sensitivity 91 percent, specificity 88 percent against adjudicated diagnosis.",
            "Results published in a peer-reviewed journal in 2026.",
        ],
    ),
    (
        "Regulatory pathway",
        [
            "FDA De Novo pathway; pre-submission meeting held in Q1 2026.",
            "Breakthrough Device designation granted 2025.",
            "Submission targeted for Q3 2027 following the pivotal study.",
        ],
    ),
    (
        "Business model",
        [
            "Razor/razorblade: analyser software licence plus per-test cartridge revenue.",
            "Cartridge ASP $220; gross margin 68 percent at 50,000 units.",
            "Reimbursement: CPT PLA code application filed; hospital budget purchase in the interim.",
        ],
    ),
    (
        "Traction",
        [
            "3 paying hospital pilots: Mercy General, Bayview Health, Northside University.",
            "$480,000 in pilot revenue booked in the last twelve months.",
            "$2.1M NIH SBIR Phase II grant awarded 2025.",
            "Two further LOIs signed with regional health systems.",
        ],
    ),
    (
        "Competition",
        [
            "Cepheid and Karius compete on pathogen identification, not host response.",
            "Inflammatix is the closest direct competitor with a host-response panel.",
            "Our differentiation is the 55-minute run time on installed analysers.",
        ],
    ),
    (
        "Team",
        [
            "Dr Alina Reyes, CEO - previously VP Clinical at a diagnostics company acquired in 2022.",
            "Dr Tomas Lindqvist, CTO - 14 years in assay development, 6 issued patents.",
            "Head of Regulatory hired 2025; VP Commercial is an open role.",
        ],
    ),
    (
        "Intellectual property",
        [
            "Two granted US patents covering the host-response gene signature, expiring 2041.",
            "One pending continuation on the cartridge fluidics.",
        ],
    ),
    (
        "Financials",
        [
            "Current burn $310,000 per month; 9 months of runway at 30 June 2026.",
            "Use of proceeds: pivotal study 55 percent, manufacturing scale-up 25 percent, "
            "commercial build 20 percent.",
        ],
    ),
    (
        "The ask",
        [
            "Raising $12M Series A in priced equity at a $38M pre-money valuation.",
            "$3.5M committed from existing investors and a strategic.",
            "$1.2M soft-circled from angels.",
            "Target close November 2026.",
            "Existing investors include Kestrel Seed Partners and Longview Family Office.",
        ],
    ),
]

INVESTOR_ROWS = [
    {
        "Investor": "Meridian Life Sciences Partners",
        "Type": "Venture Fund",
        "Check Size": "$4M-$8M",
        "Stage Focus": "Series A, Series B",
        "Sector Focus": "diagnostics, medical devices, clinical tools",
        "Leads Rounds": "Yes",
        "Lead History": "Led Cardiosense Series A 2025; co-led Nomad Bio Series B 2024",
        "Relationship": "Warm intro available via Dr Alina Reyes -> Prof. Sandra Ku -> Partner",
        "Status": "Intro made",
        "Fund Status": "Fund IV closed 2025, actively deploying",
        "Portfolio": "Cardiosense, Nomad Bio, Steadyline Health",
        "Contact": "Priya Raman, Partner",
        "Notes": "Diagnostics thesis published on their site. Wants pivotal study design reviewed.",
        "Next Step": "Schedule partner meeting",
        "Owner": "CEO",
    },
    {
        "Investor": "Sequoia Crest Capital",
        "Type": "Venture Fund",
        "Check Size": "$5M-$15M",
        "Stage Focus": "Series B, Series C",
        "Sector Focus": "healthcare services, digital health",
        "Leads Rounds": "Yes",
        "Lead History": "",
        "Relationship": "Cold",
        "Status": "Cold",
        "Fund Status": "Fund VII 2024, active",
        "Portfolio": "Participated in Inflammatix Series C",
        "Contact": "",
        "Notes": "Big name. Participated in the Inflammatix round but did not lead it. Enters at Series B.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Northlight Diagnostics Fund",
        "Type": "Micro VC",
        "Check Size": "$1.5M-$3M",
        "Stage Focus": "Seed, Series A",
        "Sector Focus": "diagnostics, sepsis, hospital point of care",
        "Leads Rounds": "Yes",
        "Lead History": "Led Vessl Dx Series A 2025 and took a board seat; led Coriolis Seed 2024",
        "Relationship": "First meeting completed",
        "Status": "Partner meeting",
        "Fund Status": "Fund II 2025, actively deploying",
        "Portfolio": "Vessl Dx, Coriolis, Amberline Health",
        "Contact": "Ben Okafor, Managing Partner",
        "Notes": "Specialist diagnostics fund. Prefers to lead at Series A. Asked for the health "
        "economics model.",
        "Next Step": "Send health economics model",
        "Owner": "CEO",
    },
    {
        "Investor": "Grandview Strategic Ventures",
        "Type": "Corporate / CVC",
        "Check Size": "$1M-$3M",
        "Stage Focus": "Series A, Series B",
        "Sector Focus": "hospital diagnostics, laboratory automation",
        "Leads Rounds": "No - follows a financial lead",
        "Lead History": "",
        "Relationship": "Active diligence",
        "Status": "Diligence",
        "Fund Status": "Corporate balance sheet, active",
        "Portfolio": "Labtrace, Sentinel Analytics",
        "Contact": "Maria Alvarez, Head of Ventures",
        "Notes": "Strategic arm of an analyser manufacturer. Needs a financial lead in place. "
        "Distribution conversation running in parallel.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Harbourstone Ventures",
        "Type": "Venture Fund",
        "Check Size": "$2M-$4M",
        "Stage Focus": "Series A",
        "Sector Focus": "medtech, diagnostics",
        "Leads Rounds": "Sometimes",
        "Lead History": "Co-led Pulsewave Series A 2023",
        "Relationship": "Second meeting",
        "Status": "Follow-up",
        "Fund Status": "Between funds - Fund III raising, no dry powder until 2027",
        "Portfolio": "Pulsewave, Trellis Medical",
        "Contact": "James Wu, Principal",
        "Notes": "Interested but between funds; cannot make new investments this year.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Cobalt Ridge Capital",
        "Type": "Venture Fund",
        "Check Size": "$1M-$2M",
        "Stage Focus": "Series A",
        "Sector Focus": "diagnostics, molecular testing",
        "Leads Rounds": "No",
        "Lead History": "",
        "Relationship": "Intro made",
        "Status": "First meeting",
        "Fund Status": "Fund III 2024, active",
        "Portfolio": "Inflammatix, Verity Molecular",
        "Contact": "Dana Feld, Partner",
        "Notes": "Portfolio includes Inflammatix, a direct competitor named in our deck. Would "
        "need conflict cleared before sharing clinical data.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Longview Family Office",
        "Type": "Family Office",
        "Check Size": "$500k-$1.5M",
        "Stage Focus": "Seed, Series A",
        "Sector Focus": "healthcare",
        "Leads Rounds": "No",
        "Lead History": "",
        "Relationship": "Committed",
        "Status": "Committed",
        "Fund Status": "Evergreen, active",
        "Portfolio": "Helios Diagnostics",
        "Contact": "Robert Lang",
        "Notes": "Existing investor. $1.5M committed to this round. Will follow the lead terms.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Bay Angels Collective",
        "Type": "Angel Group",
        "Check Size": "$150k-$400k",
        "Stage Focus": "Seed, Series A",
        "Sector Focus": "healthcare, life sciences",
        "Leads Rounds": "No",
        "Lead History": "",
        "Relationship": "Verbal interest",
        "Status": "Verbal",
        "Fund Status": "Active",
        "Portfolio": "",
        "Contact": "Screening committee",
        "Notes": "Wants a priced round with a named lead before syndicating to members.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Ironwood Capital Partners",
        "Type": "Venture Fund",
        "Check Size": "$3M-$6M",
        "Stage Focus": "Series B, Series C",
        "Sector Focus": "enterprise software, fintech",
        "Leads Rounds": "Yes",
        "Lead History": "Led Streamforge Series B 2025",
        "Relationship": "Cold",
        "Status": "Cold",
        "Fund Status": "Fund V 2023, active",
        "Portfolio": "Streamforge, Datawing",
        "Contact": "",
        "Notes": "Software focus, no life sciences investments identified.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Kestrel Seed Partners",
        "Type": "Micro VC",
        "Check Size": "$250k-$750k",
        "Stage Focus": "Pre-Seed, Seed",
        "Sector Focus": "life sciences tools",
        "Leads Rounds": "Yes",
        "Lead History": "Led Helios Diagnostics Seed 2024",
        "Relationship": "Committed",
        "Status": "Committed",
        "Fund Status": "Fund II 2023, active",
        "Portfolio": "Helios Diagnostics, Nexafold",
        "Contact": "Sara Bright",
        "Notes": "Existing seed investor, $2M committed to this round. Cannot lead at Series A "
        "size.",
        "Next Step": "",
        "Owner": "",
    },
    {
        "Investor": "Pinnacle Health Ventures",
        "Type": "Venture Fund",
        "Check Size": "",
        "Stage Focus": "Series A",
        "Sector Focus": "diagnostics",
        "Leads Rounds": "",
        "Lead History": "",
        "Relationship": "Cold",
        "Status": "Cold",
        "Fund Status": "",
        "Portfolio": "",
        "Contact": "",
        "Notes": "Suggested by an adviser; nothing verified yet.",
        "Next Step": "",
        "Owner": "",
    },
]

NOTES = """# Investor conversation notes - Helios Diagnostics Series A

## Northlight Diagnostics Fund - 14 July 2026
Ben Okafor ran the meeting. Northlight led the Vessl Dx Series A in 2025 and took a board
seat, and led the Coriolis seed in 2024. Ben said they prefer to lead at Series A and can
write up to $3M. They want the health economics model and the pivotal study protocol
before taking it to the full partnership. Partner meeting is provisionally 4 August.

## Meridian Life Sciences Partners - 2 July 2026
Warm introduction available through Prof. Sandra Ku, who sits on our clinical advisory
board and co-authored with the Meridian partner. Meridian led the Cardiosense Series A in
2025 and co-led the Nomad Bio Series B in 2024. Typical initial cheque is $4M to $8M.
Fund IV closed in 2025. No meeting held yet.

## Sequoia Crest Capital
No relationship. They participated in the Inflammatix Series C but did not lead it, and
their published stage focus starts at Series B. Listed here because a board member
mentioned the name.

## Grandview Strategic Ventures - 20 June 2026
Maria Alvarez confirmed they will not lead and need a financial lead in place first. They
are running commercial diligence on the analyser integration in parallel. Their
participation would be a strong technical validation for other investors.

## Harbourstone Ventures - 11 June 2026
James Wu was positive on the data but confirmed Harbourstone is between funds. Fund III
will not hold a first close until 2027, so they cannot invest in this round.

## Cobalt Ridge Capital - 25 June 2026
Dana Feld was engaged on the science. Cobalt Ridge holds Inflammatix, which our deck names
as our closest direct competitor. We should clear the conflict in writing before sharing
the pivotal protocol.

## Bay Angels Collective
Verbal interest from the screening committee. They will syndicate to members only once a
priced round with a named lead exists.
"""


def build_deck(path: Path) -> Path:
    width, height = letter
    canvas = pdfcanvas.Canvas(str(path), pagesize=letter)
    for index, (title, lines) in enumerate(DECK_SLIDES, start=1):
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawString(56, height - 80, title)
        canvas.setFont("Helvetica", 12)
        y = height - 120
        for line in lines:
            canvas.drawString(56, y, line)
            y -= 20
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width - 56, 40, f"Helios Diagnostics - slide {index}")
        canvas.showPage()
    canvas.save()
    return path


def build_investor_csv(path: Path) -> Path:
    fieldnames = list(INVESTOR_ROWS[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(INVESTOR_ROWS)
    return path


def build_notes(path: Path) -> Path:
    path.write_text(NOTES, encoding="utf-8")
    return path


def build_all(directory: Path | None = None) -> dict[str, Path]:
    directory = Path(directory or HERE)
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "deck": build_deck(directory / "helios_diagnostics_deck.pdf"),
        "investors": build_investor_csv(directory / "investor_target_list.csv"),
        "notes": build_notes(directory / "investor_meeting_notes.md"),
    }


if __name__ == "__main__":
    for name, path in build_all().items():
        print(f"{name}: {path}")
