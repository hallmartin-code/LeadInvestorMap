"""The one-page Lead Investor Map.

Layout, top to bottom: header, round snapshot, lead candidates, a three-column band
(momentum / outreach sequence / disqualified as leads), gaps and required actions, and a
sourcing footer. The page is measured before anything is committed; if it does not fit,
the fitting ladder degrades it and it is measured again. The result is one page, always.

Every drawing helper takes the current y and returns the height it consumed, so the same
code path measures and draws - a measured layout cannot drift from the drawn one.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

from ..models.analysis import LeadInvestorMap
from ..models.investor import Investor, Tier
from ..utils.config import BRAND_NAME, FOOTER_NOTE, PRODUCT_NAME
from ..utils.logging import get_logger
from ..utils.text import truncate
from . import components as C
from . import theme as T
from .fitting import BASE, LADDER, FitConfig

_log = get_logger()


class RenderResult:
    def __init__(self, path: Path, pages: int, dropped: list[str], overflow: float) -> None:
        self.path = path
        self.pages = pages
        self.dropped = dropped
        self.overflow = overflow

    @property
    def fits(self) -> bool:
        return self.pages == 1 and self.overflow <= 0


class _NullCanvas:
    """Absorbs drawing calls so a layout can be measured without producing output."""

    def __getattr__(self, _name):
        def noop(*args, **kwargs):
            return None

        return noop


def _place(flow, canvas, x: float, y: float) -> None:
    """Draw a flowable, unless we are only measuring.

    Platypus flowables need a real canvas; the measuring pass has already taken the height
    it needs from wrap(), so drawing is simply skipped.
    """
    if isinstance(canvas, _NullCanvas):
        return
    flow.drawOn(canvas, x, y)


def render(analysis: LeadInvestorMap, output_path: str | Path) -> RenderResult:
    """Measure down the ladder, then draw the first configuration that fits."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chosen = LADDER[-1]
    overflow = 0.0
    for config in LADDER:
        chosen = config
        overflow = _measure(analysis, config)
        if overflow <= 0:
            break

    canvas = pdfcanvas.Canvas(str(output_path), pagesize=(T.PAGE_W, T.PAGE_H))
    canvas.setTitle(f"{analysis.company.display_name} - {PRODUCT_NAME}")
    canvas.setAuthor(BRAND_NAME)
    canvas.setSubject("Lead investor map")
    _draw_page(canvas, analysis, chosen, trimmed=overflow > 0)
    canvas.showPage()
    canvas.save()

    dropped = chosen.describe_drops(BASE)
    if overflow > 0:
        _log.warning("one-pager still overflows by %.1fpt at the last ladder rung; content was cut", overflow)
    return RenderResult(output_path, pages=1, dropped=dropped, overflow=max(0.0, overflow))


def _measure(analysis: LeadInvestorMap, config: FitConfig) -> float:
    """Height overshoot in points. <= 0 means the layout fits on one page."""
    used = _draw_page(_NullCanvas(), analysis, config, measure_only=True)
    return used - (T.Y_TOP - T.Y_BOTTOM)


def _draw_page(
    canvas,
    analysis: LeadInvestorMap,
    config: FitConfig,
    *,
    measure_only: bool = False,
    trimmed: bool = False,
) -> float:
    gap = T.SECTION_GAP * config.spacing_scale
    y = T.Y_TOP

    y -= _draw_header(canvas, analysis, config, y)
    y -= gap
    y -= _draw_snapshot(canvas, analysis, config, y)
    y -= gap
    y -= _draw_candidates(canvas, analysis, config, y)
    y -= gap
    y -= _draw_band(canvas, analysis, config, y)
    y -= gap
    y -= _draw_gaps(canvas, analysis, config, y)

    if not measure_only:
        _draw_footer(canvas, analysis, trimmed=trimmed)
    return T.Y_TOP - y


# --- header ---------------------------------------------------------------------------------


def _draw_header(canvas, analysis: LeadInvestorMap, config: FitConfig, y: float) -> float:
    company = analysis.company.display_name.upper()
    title = C.truncate_to_width(company, T.CONTENT_W * 0.5, T.FONT_BOLD, T.TITLE_SIZE)

    canvas.setFont(T.FONT_BOLD, T.TITLE_SIZE)
    canvas.setFillColor(T.INK)
    canvas.drawString(T.X0, y - T.TITLE_SIZE, title)

    canvas.setFont(T.FONT, T.SUBTITLE_SIZE)
    canvas.setFillColor(T.ACCENT)
    canvas.drawString(
        T.X0 + stringWidth(title, T.FONT_BOLD, T.TITLE_SIZE) + 9,
        y - T.TITLE_SIZE,
        PRODUCT_NAME,
    )

    canvas.setFillColor(T.MUTED)
    canvas.drawRightString(T.X1, y - T.TITLE_SIZE, analysis.metadata.generated_date)

    subtitle = analysis.company.one_liner.display()
    if subtitle == "NOT PROVIDED":
        subtitle = "Company summary NOT PROVIDED in the supplied materials"
    canvas.setFont(T.FONT, T.MICRO_SIZE + 0.6)
    canvas.setFillColor(T.MUTED)
    canvas.drawString(
        T.X0,
        y - T.TITLE_SIZE - 10,
        C.truncate_to_width(subtitle, T.CONTENT_W * 0.66, T.FONT, T.MICRO_SIZE + 0.6),
    )

    canvas.setFillColor(T.FAINT)
    canvas.drawRightString(T.X1, y - T.TITLE_SIZE - 10, _evidence_summary(analysis))

    C.rule(canvas, T.X0, y - T.HEADER_H + 4, T.CONTENT_W, color=T.NAVY, thickness=1.0)
    return T.HEADER_H


def _evidence_summary(analysis: LeadInvestorMap) -> str:
    prospects = len(analysis.prospects)
    leads = len([p for p in analysis.prospects if p.tier == Tier.POTENTIAL_LEAD])
    research = "public research ON" if analysis.metadata.public_research_enabled else "documents only"
    return f"{prospects} prospects  |  {leads} lead-qualified  |  {research}"


# --- round snapshot --------------------------------------------------------------------------


def _draw_snapshot(canvas, analysis: LeadInvestorMap, config: FitConfig, y: float) -> float:
    round_ = analysis.round
    requirement = analysis.lead_requirement
    valuation_source = round_.pre_money if round_.pre_money.is_known else round_.safe_cap

    cells = [
        ("Stage", round_.stage.display(), _status_note(round_.stage)),
        ("Raise", round_.raise_amount.display(), _status_note(round_.raise_amount)),
        ("Instrument", round_.instrument.display(), _status_note(round_.instrument)),
        ("Valuation", round_.valuation_display, _status_note(valuation_source)),
        ("Committed", round_.committed.display(), _status_note(round_.committed)),
        ("Remaining", round_.remaining.display(), "derived"),
        ("Target close", round_.target_close.display(), _status_note(round_.target_close)),
        (
            "Lead check required",
            requirement.display(),
            "ESTIMATED" if requirement.is_known else "insufficient data",
        ),
    ]

    gap = 5.0
    width = (T.CONTENT_W - gap * (len(cells) - 1)) / len(cells)
    for index, (label, value, note) in enumerate(cells):
        C.tile(
            canvas,
            T.X0 + index * (width + gap),
            y,
            width,
            T.SNAPSHOT_H,
            label,
            value,
            emphasis=(label == "Lead check required"),
            note=note,
        )
    return T.SNAPSHOT_H


def _status_note(fact) -> str:
    if not fact.is_known:
        return ""
    if fact.status.value == "VERIFIED":
        source = fact.sources[0] if fact.sources else None
        if source and source.page_or_slide:
            return f"deck p./sl. {source.page_or_slide}"
        return "from deck"
    return fact.status.value.lower()


# --- lead candidates -------------------------------------------------------------------------


def _candidate_columns(config: FitConfig) -> tuple[list[str], list[float]]:
    if config.show_next_step_column:
        headers = [
            "#",
            "INVESTOR",
            "TIER",
            "LEAD CONF",
            "CHECK",
            "LEAD EVIDENCE",
            "FIT STAGE/SECTOR",
            "RELATIONSHIP",
            "KEY DEPENDENCY",
            "NEXT STEP (OWNER)",
        ]
        ratios = [0.022, 0.130, 0.068, 0.056, 0.082, 0.168, 0.090, 0.076, 0.140, 0.168]
    else:
        headers = [
            "#",
            "INVESTOR",
            "TIER",
            "LEAD CONF",
            "CHECK",
            "LEAD EVIDENCE",
            "FIT STAGE/SECTOR",
            "RELATIONSHIP",
            "KEY DEPENDENCY",
        ]
        ratios = [0.024, 0.152, 0.078, 0.064, 0.092, 0.208, 0.100, 0.090, 0.192]
    return headers, [T.CONTENT_W * r for r in ratios]


def _draw_candidates(canvas, analysis: LeadInvestorMap, config: FitConfig, y: float) -> float:
    used = C.section_label(canvas, T.X0, y, "LEAD CANDIDATES", T.CONTENT_W)
    shortlist = analysis.lead_shortlist[: config.max_candidates]
    body = C.style(config.body_size, color=T.BODY)

    if not shortlist:
        message = (
            "No prospect in the supplied materials meets the lead standard: verified lead history, "
            "cheque capacity for the estimated lead requirement, stage and sector fit, and current "
            "deployment capacity. Fallback structures are set out below."
        )
        flow = C.para(message, body)
        height = C.measure(flow, T.CONTENT_W)
        _place(flow, canvas, T.X0, y - used - height)
        return used + height

    headers, widths = _candidate_columns(config)
    cell = C.style(config.body_size, color=T.BODY)
    cell_bold = C.style(config.body_size, bold=True, color=T.INK)
    micro = C.style(max(6.2, config.body_size - 1.2), color=T.MUTED)

    rows: list[list] = [headers]
    for entry in shortlist:
        investor = analysis.prospect(entry.investor_name)
        row = [
            C.para(str(entry.rank), cell_bold),
            C.para(entry.investor_name, cell_bold),
            C.para(investor.tier.short_label if investor and investor.tier else "-", micro),
            C.para(entry.lead_confidence.value, cell_bold),
            C.para(entry.check_display, cell),
            C.para(_lead_evidence_cell(entry, investor, config), cell),
            C.para(_fit_cell(investor), cell),
            C.para(entry.relationship, cell),
            C.para(truncate(_dependency_cell(investor, entry), config.narrative_chars), cell),
        ]
        if config.show_next_step_column:
            row.append(C.para(_next_step_cell(entry), cell))
        rows.append(row)

    built = C.table(rows, widths, font_size=config.body_size, padding=2.6 * config.spacing_scale)
    height = C.measure(built, T.CONTENT_W)
    _place(built, canvas, T.X0, y - used - height)
    used += height + 2

    # One line of case-for under the table keeps the "why" on the page without a column.
    top = shortlist[0]
    note = C.style(max(6.4, config.body_size - 1.0), color=T.MUTED, italic=True)
    text = f"#1 {top.investor_name}: {top.why_they_can_lead} {top.why_they_fit} Obstacle: {top.key_obstacle}"
    flow = C.para(truncate(text, config.narrative_chars * 3), note)
    height = C.measure(flow, T.CONTENT_W)
    _place(flow, canvas, T.X0, y - used - height)
    return used + height


def _lead_evidence_cell(entry, investor: Investor | None, config: FitConfig) -> str:
    if investor is None:
        return entry.lead_evidence
    if investor.has_verified_lead_history:
        return truncate(investor.lead_history_display(2), config.narrative_chars)
    if investor.leads_rounds_stated is True:
        return "Says it leads; NOT VERIFIED"
    return "NOT VERIFIED"


def _fit_cell(investor: Investor | None) -> str:
    if investor is None:
        return "UNKNOWN"
    return f"{investor.stage_fit.value.title()} / {investor.sector_fit.value.title()}"


def _dependency_cell(investor: Investor | None, entry=None) -> str:
    """What has to become true. With no dependency on file, show the condition to commit.

    An empty cell against a lead candidate reads as "nothing to do", which is never the
    case for an investor that has not yet committed.
    """
    if investor is None:
        return "Not identified"
    dependency = investor.key_dependency
    if dependency and dependency != "None identified":
        return dependency
    if entry is not None and entry.what_must_go_right:
        return entry.what_must_go_right
    return "None identified"


def _next_step_cell(entry) -> str:
    owner = f" ({entry.next_step_owner})" if entry.next_step_owner else ""
    return f"{entry.required_next_step}{owner}"


# --- three-column band -----------------------------------------------------------------------


def _draw_band(canvas, analysis: LeadInvestorMap, config: FitConfig, y: float) -> float:
    width = (T.CONTENT_W - T.COLUMN_GAP * 2) / 3
    columns = (_draw_momentum, _draw_outreach, _draw_disqualified)
    heights = []
    for index, draw in enumerate(columns):
        x = T.X0 + index * (width + T.COLUMN_GAP)
        heights.append(draw(canvas, analysis, config, x, y, width))
    return max(heights)


def _draw_momentum(
    canvas, analysis: LeadInvestorMap, config: FitConfig, x: float, y: float, width: float
) -> float:
    used = C.section_label(canvas, x, y, "MOMENTUM PATH", width)
    pull = analysis.highest_pull_commitment
    body = C.style(config.body_size, color=T.BODY)
    micro = C.style(max(6.4, config.body_size - 1.0), color=T.MUTED)

    flow = (
        C.rich(
            "<b>Highest pull:</b> {name} ({confidence} confidence)",
            body,
            name=pull.investor_name,
            confidence=pull.confidence,
        )
        if pull.investor_name
        else C.rich("<b>Highest pull:</b> NOT ESTABLISHED", body)
    )
    height = C.measure(flow, width)
    _place(flow, canvas, x, y - used - height)
    used += height + 2

    if pull.rationale:
        flow = C.para(truncate(pull.rationale, config.narrative_chars + 60), micro)
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        used += height + 3

    steps = analysis.momentum_sequence[: config.max_momentum_steps]
    if steps:
        labels = [f"{s.investor_name} {s.event}" for s in steps]
        used += C.arrow_chain(canvas, x, y - used, width, labels, font_size=config.body_size) + 3
    else:
        flow = C.para(
            "No evidence-supported momentum path could be built from the supplied prospects.",
            micro,
        )
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        used += height + 3

    if pull.downstream_investors:
        flow = C.para(
            "Downstream (state they need a lead): " + ", ".join(pull.downstream_investors[:4]),
            micro,
        )
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        used += height
    return used


def _draw_outreach(
    canvas, analysis: LeadInvestorMap, config: FitConfig, x: float, y: float, width: float
) -> float:
    used = C.section_label(canvas, x, y, "OUTREACH SEQUENCE", width)
    sequence = analysis.outreach_sequence
    if sequence is None:
        return used

    micro = C.style(max(6.4, config.body_size - 1.0), color=T.BODY)
    for label, phase in (
        ("NOW", sequence.phase_1),
        ("NEXT", sequence.phase_2),
        ("ON MOMENTUM", sequence.phase_3),
        ("COMPLETION", sequence.phase_4),
        ("HOLD BACK", sequence.hold_back),
    ):
        names = phase.investors[: config.max_phase_names]
        text = ", ".join(names) if names else "none identified"
        more = len(phase.investors) - len(names)
        if more > 0:
            text += f" (+{more})"
        flow = C.rich("<b>{label}:</b> {text}", micro, label=label, text=text)
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        used += height + 1.6
    return used


def _draw_disqualified(
    canvas, analysis: LeadInvestorMap, config: FitConfig, x: float, y: float, width: float
) -> float:
    used = C.section_label(canvas, x, y, "DISQUALIFIED AS LEADS", width)
    micro = C.style(max(6.4, config.body_size - 1.0), color=T.BODY)

    items = analysis.disqualified_as_leads[: config.max_disqualified]
    if not items:
        flow = C.para("No prospect was ruled out as a lead.", micro)
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        return used + height

    for item in items:
        reasons = ", ".join(r.value for r in item.reasons[:2]) or "NOT A LEAD"
        flow = C.rich("<b>{name}</b> - {reasons}", micro, name=item.investor_name, reasons=reasons)
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        used += height + 1.4

    remaining = len(analysis.disqualified_as_leads) - len(items)
    if remaining > 0:
        flow = C.para(f"+{remaining} further prospect(s) - see companion JSON.", micro)
        height = C.measure(flow, width)
        _place(flow, canvas, x, y - used - height)
        used += height
    return used


# --- gaps -----------------------------------------------------------------------------------


def _severity_label(severity: str) -> str:
    return {"high": "HIGH", "medium": "MED", "low": "LOW"}.get(
        (severity or "").lower(), (severity or "").upper()[:4]
    )


def _draw_gaps(canvas, analysis: LeadInvestorMap, config: FitConfig, y: float) -> float:
    label = "GAPS / RISKS AND REQUIRED ACTION"
    if analysis.fallback_structures:
        label += "  |  FALLBACK STRUCTURES IF NO LEAD EMERGES"
    used = C.section_label(canvas, T.X0, y, label, T.CONTENT_W)

    cell = C.style(config.body_size, color=T.BODY)
    head = C.style(max(6.2, config.body_size - 1.4), bold=True, color=T.MUTED)

    rows: list[list] = [
        [
            C.para("GAP / RISK", head),
            C.para("CONSEQUENCE", head),
            C.para("REQUIRED ACTION", head),
            C.para("SEV", head),
        ]
    ]
    for gap in analysis.gaps_and_risks[: config.max_gaps]:
        rows.append(
            [
                C.para(gap.gap, cell),
                C.para(gap.consequence, cell),
                C.para(gap.suggested_addition or "-", cell),
                C.para(_severity_label(gap.severity), cell),
            ]
        )

    # Fallbacks only exist when no credible lead was found, and in that case the founder
    # needs them on the page rather than in the companion JSON.
    for structure in analysis.fallback_structures[: config.max_fallbacks]:
        rows.append(
            [
                C.rich(
                    "<b>Fallback:</b> {structure} ({viability})",
                    cell,
                    structure=structure.structure,
                    viability=structure.viability,
                ),
                C.para(f"Risk: {structure.primary_risk}", cell),
                C.para(f"Needs {structure.capital_required}. {structure.milestone_required}", cell),
                C.para("ALT", cell),
            ]
        )

    if config.show_objections and analysis.company.objections:
        top = analysis.company.objections[0]
        rows.append(
            [
                C.para(f"Likely objection: {top.objection}", cell),
                C.para(top.evidence, cell),
                C.para("Prepare a direct answer before phase 2 outreach.", cell),
                C.para(_severity_label(top.severity), cell),
            ]
        )

    if len(rows) == 1:
        flow = C.para("No structural pipeline gaps identified.", cell)
        height = C.measure(flow, T.CONTENT_W)
        _place(flow, canvas, T.X0, y - used - height)
        return used + height

    widths = [T.CONTENT_W * r for r in (0.30, 0.32, 0.30, 0.08)]
    built = C.table(rows, widths, font_size=config.body_size, padding=2.4 * config.spacing_scale)
    height = C.measure(built, T.CONTENT_W)
    _place(built, canvas, T.X0, y - used - height)
    return used + height


# --- footer ---------------------------------------------------------------------------------


def _draw_footer(canvas, analysis: LeadInvestorMap, *, trimmed: bool = False) -> None:
    y = T.MARGIN + 14
    C.rule(canvas, T.X0, y + 6, T.CONTENT_W, color=T.HAIRLINE)

    canvas.setFont(T.FONT, T.FOOTNOTE_SIZE)
    canvas.setFillColor(T.MUTED)
    canvas.drawString(T.X0, y - 2, FOOTER_NOTE)

    sources = analysis.metadata.input_files
    detail = f"Inputs: {', '.join(sources[:4])}" if sources else "Inputs: none recorded"
    if len(sources) > 4:
        detail += f" (+{len(sources) - 4})"
    canvas.drawString(T.X0, y - 10, C.truncate_to_width(detail, T.CONTENT_W * 0.6, T.FONT, T.FOOTNOTE_SIZE))

    canvas.drawRightString(T.X1, y - 2, f"Generated {analysis.metadata.generated_date} by {BRAND_NAME}")

    warnings = len([w for w in analysis.warnings if w.severity in {"warning", "error"}])
    note = f"{warnings} data warning(s) - see companion JSON" if warnings else "No data warnings"
    if trimmed:
        note += " | content trimmed to fit one page"
    canvas.drawRightString(T.X1, y - 10, note)
