"""Email the finished Lead Investor Map via Resend.

One HTTP call to ``POST https://api.resend.com/emails`` with the one-pager attached. No
SDK: the request is a single well-understood POST, and owning it keeps the failure modes
explicit and the tests honest.

The governing rule is that **email never breaks an analysis**. A missing key, a bad
address, an unverified sending domain, an outage or a timeout all produce an
:class:`EmailOutcome` describing what happened; nothing raises into the caller. A map that
generated successfully must still be downloadable even if nobody could be told about it.
"""

from __future__ import annotations

import base64
import html
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..models.analysis import LeadInvestorMap
from ..models.investor import Tier
from ..utils.config import EmailSettings
from ..utils.logging import get_logger

log = get_logger()

RESEND_ENDPOINT = "https://api.resend.com/emails"

EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")

#: Resend caps a message at roughly 40 MB in total; stay well inside it.
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024

CONFIDENCE_COLOUR = {"HIGH": "#1B5E20", "MEDIUM": "#7A5B00", "LOW": "#8C1D18"}
INK = "#1F2937"
MUTED = "#6B7280"
NAVY = "#1F3864"
RULE = "#D1D5DB"


@dataclass
class EmailOutcome:
    """What happened. Never an exception."""

    sent: bool = False
    to: list[str] = field(default_factory=list)
    message_id: str = ""
    error: str = ""
    skipped: str = ""

    def summary(self) -> str:
        if self.sent:
            return f"Emailed to {', '.join(self.to)}"
        if self.skipped:
            return f"Email skipped: {self.skipped}"
        return f"Email failed: {self.error}"


def parse_recipients(raw: str) -> list[str]:
    """Split and validate a comma or semicolon separated recipient list."""
    candidates = [part.strip() for part in re.split(r"[,;]", raw or "") if part.strip()]
    return [c for c in candidates if EMAIL_RE.match(c)]


# --- message body ---------------------------------------------------------------------------


def build_subject(analysis: LeadInvestorMap) -> str:
    """Say the outcome in the subject line: the count is the headline finding."""
    name = analysis.company.display_name
    leads = len([p for p in analysis.prospects if p.tier == Tier.POTENTIAL_LEAD])
    stage = analysis.round.stage.value or "round"
    raise_amount = analysis.round.raise_amount.value

    scope = f"{stage} {raise_amount}" if raise_amount else stage
    if leads == 0:
        finding = "no qualified lead"
    elif leads == 1:
        finding = "1 qualified lead"
    else:
        finding = f"{leads} qualified leads"
    return f"Lead Investor Map: {name} - {scope} - {finding}"


def _row(label: str, value: str) -> str:
    return (
        "<tr>"
        f"<td style='padding:2px 12px 2px 0;font:600 11px/1.5 Arial,sans-serif;"
        f"color:{MUTED};white-space:nowrap;vertical-align:top'>{html.escape(label)}</td>"
        f"<td style='padding:2px 0;font:11px/1.5 Arial,sans-serif;color:{INK}'>"
        f"{html.escape(value)}</td></tr>"
    )


def _section(title: str, body: str) -> str:
    return (
        f"<h2 style='font:700 11px/1.4 Arial,sans-serif;color:{NAVY};margin:22px 0 6px;"
        f"letter-spacing:.06em;text-transform:uppercase'>{html.escape(title)}</h2>"
        f"<div style='border-top:1px solid {RULE};padding-top:8px'>{body}</div>"
    )


def _candidates_html(analysis: LeadInvestorMap) -> str:
    if not analysis.lead_shortlist:
        return (
            f"<p style='font:11px/1.5 Arial,sans-serif;color:{INK};margin:0'>"
            "No prospect met the lead standard on the evidence supplied: verified lead "
            "history, cheque capacity for the estimated lead requirement, stage and sector "
            "fit, and current deployment capacity. Fallback structures are set out in the "
            "attached one-pager.</p>"
        )

    header = "".join(
        f"<th style='text-align:left;padding:0 10px 6px 0;font:700 10px/1.4 Arial,sans-serif;"
        f"color:{MUTED};text-transform:uppercase;letter-spacing:.04em'>{html.escape(h)}</th>"
        for h in ("#", "Investor", "Confidence", "Cheque", "Lead evidence", "Next step")
    )

    rows = []
    for entry in analysis.lead_shortlist:
        colour = CONFIDENCE_COLOUR.get(entry.lead_confidence.value, INK)
        owner = f" ({entry.next_step_owner})" if entry.next_step_owner else ""
        cells = [
            f"<td style='padding:5px 10px 5px 0;font:11px/1.45 Arial,sans-serif;color:{MUTED};"
            f"vertical-align:top'>{entry.rank}</td>",
            f"<td style='padding:5px 10px 5px 0;font:600 11px/1.45 Arial,sans-serif;color:{INK};"
            f"vertical-align:top'>{html.escape(entry.investor_name)}</td>",
            f"<td style='padding:5px 10px 5px 0;font:700 11px/1.45 Arial,sans-serif;color:{colour};"
            f"vertical-align:top;white-space:nowrap'>{html.escape(entry.lead_confidence.value)}</td>",
            f"<td style='padding:5px 10px 5px 0;font:11px/1.45 Arial,sans-serif;color:{INK};"
            f"vertical-align:top;white-space:nowrap'>{html.escape(entry.check_display)}</td>",
            f"<td style='padding:5px 10px 5px 0;font:11px/1.45 Arial,sans-serif;color:{INK};"
            f"vertical-align:top'>{html.escape(entry.lead_evidence)}</td>",
            f"<td style='padding:5px 0;font:11px/1.45 Arial,sans-serif;color:{INK};"
            f"vertical-align:top'>{html.escape(entry.required_next_step + owner)}</td>",
        ]
        rows.append(f"<tr style='border-top:1px solid #EEF1F5'>{''.join(cells)}</tr>")

    return (
        "<table cellpadding='0' cellspacing='0' style='width:100%;border-collapse:collapse'>"
        f"<tr>{header}</tr>{''.join(rows)}</table>"
    )


def _list_html(items: Sequence[str], empty: str) -> str:
    if not items:
        return f"<p style='font:11px/1.5 Arial,sans-serif;color:{MUTED};margin:0'>{html.escape(empty)}</p>"
    entries = "".join(f"<li style='margin:0 0 4px'>{html.escape(item)}</li>" for item in items)
    return f"<ul style='font:11px/1.5 Arial,sans-serif;color:{INK};margin:0;padding-left:16px'>{entries}</ul>"


def build_html(analysis: LeadInvestorMap, disclaimer: str) -> str:
    round_ = analysis.round
    snapshot = "".join(
        [
            _row("Stage", round_.stage.display()),
            _row("Raise", round_.raise_amount.display()),
            _row("Instrument", round_.instrument.display()),
            _row("Valuation", round_.valuation_display),
            _row("Committed", round_.committed.display()),
            _row("Remaining", round_.remaining.display()),
            _row("Target close", round_.target_close.display()),
            _row("Lead cheque required", f"{analysis.lead_requirement.display()} (estimated)"),
        ]
    )

    pull = analysis.highest_pull_commitment
    if pull.investor_name:
        momentum = (
            f"<p style='font:11px/1.5 Arial,sans-serif;color:{INK};margin:0 0 6px'>"
            f"<strong>Highest pull:</strong> {html.escape(pull.investor_name)} "
            f"({html.escape(pull.confidence)} confidence)</p>"
            f"<p style='font:11px/1.5 Arial,sans-serif;color:{MUTED};margin:0 0 6px'>"
            f"{html.escape(pull.rationale)}</p>"
        )
    else:
        momentum = (
            f"<p style='font:11px/1.5 Arial,sans-serif;color:{INK};margin:0 0 6px'>"
            "<strong>Highest pull:</strong> NOT ESTABLISHED</p>"
        )
    steps = [f"{s.investor_name} {s.event}" for s in analysis.momentum_sequence]
    if steps:
        momentum += (
            f"<p style='font:11px/1.5 Arial,sans-serif;color:{INK};margin:0'>"
            f"{html.escape('  >  '.join(steps))}</p>"
        )

    sequence = analysis.outreach_sequence
    if sequence is not None:
        phases = "".join(
            _row(label, ", ".join(phase.investors) or "none identified")
            for label, phase in (
                ("Now", sequence.phase_1),
                ("Next", sequence.phase_2),
                ("On momentum", sequence.phase_3),
                ("Completion", sequence.phase_4),
                ("Hold back", sequence.hold_back),
            )
        )
        outreach = f"<table cellpadding='0' cellspacing='0'>{phases}</table>"
    else:
        outreach = ""

    gaps = _list_html(
        [f"{gap.gap} - {gap.consequence}" for gap in analysis.gaps_and_risks[:4]],
        "No structural pipeline gaps identified.",
    )
    disqualified = _list_html(
        [item.display() for item in analysis.disqualified_as_leads[:6]],
        "No prospect was ruled out as a lead.",
    )

    warnings = [w for w in analysis.warnings if w.severity in {"warning", "error"}]
    warning_block = ""
    if warnings:
        warning_block = _section(
            "Data warnings",
            _list_html([w.message for w in warnings[:5]], ""),
        )

    metadata = analysis.metadata
    engine = metadata.llm_provider + (f" / {metadata.llm_model}" if metadata.llm_model else "")
    footer_rows = "".join(
        [
            _row("Prospects analysed", str(len(analysis.prospects))),
            _row("Inputs", ", ".join(metadata.input_files) or "none recorded"),
            _row("Engine", engine),
            _row(
                "Public research",
                "enabled" if metadata.public_research_enabled else "disabled (documents only)",
            ),
            _row("Generated", metadata.generated_date),
        ]
    )

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#F4F6F9">
<div style="max-width:760px;margin:0 auto;padding:28px 30px;background:#FFFFFF">
  <p style="font:700 10px/1.4 Arial,sans-serif;color:{MUTED};letter-spacing:.1em;
     text-transform:uppercase;margin:0 0 4px">TEN Capital Network</p>
  <h1 style="font:700 22px/1.25 Arial,sans-serif;color:{INK};margin:0 0 2px">
    {html.escape(analysis.company.display_name)}</h1>
  <p style="font:600 12px/1.4 Arial,sans-serif;color:#2E75B6;margin:0 0 4px">
    Lead Investor Map</p>
  <p style="font:11px/1.5 Arial,sans-serif;color:{MUTED};margin:0">
    {html.escape(analysis.company.one_liner.display())}</p>

  {_section("Round snapshot", f"<table cellpadding='0' cellspacing='0'>{snapshot}</table>")}
  {_section("Lead candidates", _candidates_html(analysis))}
  {_section("Momentum", momentum)}
  {_section("Outreach sequence", outreach)}
  {_section("Gaps and risks", gaps)}
  {_section("Disqualified as leads", disqualified)}
  {warning_block}
  {_section("Run detail", f"<table cellpadding='0' cellspacing='0'>{footer_rows}</table>")}

  <p style="font:10px/1.5 Arial,sans-serif;color:{MUTED};margin:22px 0 0;
     border-top:1px solid {RULE};padding-top:10px">{html.escape(disclaimer)}</p>
  <p style="font:10px/1.5 Arial,sans-serif;color:{MUTED};margin:6px 0 0">
    The one-page PDF and the per-prospect CSV are attached. Full evidence, source
    citations and the per-investor score breakdown are in the companion JSON.</p>
</div>
</body></html>"""


def build_text(analysis: LeadInvestorMap, disclaimer: str) -> str:
    """Plain-text alternative. Same facts, no markup."""
    round_ = analysis.round
    lines = [
        f"{analysis.company.display_name} - Lead Investor Map",
        f"{analysis.company.one_liner.display()}",
        "",
        "ROUND SNAPSHOT",
        f"  Stage                {round_.stage.display()}",
        f"  Raise                {round_.raise_amount.display()}",
        f"  Instrument           {round_.instrument.display()}",
        f"  Valuation            {round_.valuation_display}",
        f"  Committed            {round_.committed.display()}",
        f"  Remaining            {round_.remaining.display()}",
        f"  Target close         {round_.target_close.display()}",
        f"  Lead cheque required {analysis.lead_requirement.display()} (estimated)",
        "",
        "LEAD CANDIDATES",
    ]

    if analysis.lead_shortlist:
        for entry in analysis.lead_shortlist:
            owner = f" ({entry.next_step_owner})" if entry.next_step_owner else ""
            lines.append(
                f"  {entry.rank}. {entry.investor_name} - {entry.lead_confidence.value} - "
                f"{entry.check_display}"
            )
            lines.append(f"     Lead evidence: {entry.lead_evidence}")
            lines.append(f"     Next step: {entry.required_next_step}{owner}")
    else:
        lines.append(
            "  None. No prospect met the lead standard on the evidence supplied; see the "
            "fallback structures in the attached one-pager."
        )

    pull = analysis.highest_pull_commitment
    lines += ["", "MOMENTUM"]
    if pull.investor_name:
        lines.append(f"  Highest pull: {pull.investor_name} ({pull.confidence} confidence)")
        if pull.rationale:
            lines.append(f"  {pull.rationale}")
    else:
        lines.append("  Highest pull: NOT ESTABLISHED")
    for step in analysis.momentum_sequence:
        lines.append(f"  {step.step}. {step.investor_name} - {step.event}")

    sequence = analysis.outreach_sequence
    if sequence is not None:
        lines += ["", "OUTREACH SEQUENCE"]
        for label, phase in (
            ("NOW", sequence.phase_1),
            ("NEXT", sequence.phase_2),
            ("ON MOMENTUM", sequence.phase_3),
            ("COMPLETION", sequence.phase_4),
            ("HOLD BACK", sequence.hold_back),
        ):
            lines.append(f"  {label}: {', '.join(phase.investors) or 'none identified'}")

    if analysis.gaps_and_risks:
        lines += ["", "GAPS AND RISKS"]
        for gap in analysis.gaps_and_risks[:4]:
            lines.append(f"  - {gap.gap}")
            lines.append(f"    {gap.consequence}")

    if analysis.disqualified_as_leads:
        lines += ["", "DISQUALIFIED AS LEADS"]
        for item in analysis.disqualified_as_leads[:6]:
            lines.append(f"  - {item.display()}")

    warnings = [w for w in analysis.warnings if w.severity in {"warning", "error"}]
    if warnings:
        lines += ["", "DATA WARNINGS"]
        for warning in warnings[:5]:
            lines.append(f"  - {warning.message}")

    metadata = analysis.metadata
    lines += [
        "",
        "RUN DETAIL",
        f"  Prospects analysed  {len(analysis.prospects)}",
        f"  Inputs              {', '.join(metadata.input_files) or 'none recorded'}",
        f"  Engine              {metadata.llm_provider} {metadata.llm_model}".rstrip(),
        f"  Generated           {metadata.generated_date}",
        "",
        disclaimer,
        "The one-page PDF and the per-prospect CSV are attached.",
    ]
    return "\n".join(lines)


# --- attachments -----------------------------------------------------------------------------


def _attachment(path: Path) -> dict | None:
    """Base64 one file for Resend, or skip it with a warning rather than fail the send."""
    try:
        if not path.exists() or not path.is_file():
            return None
        size = path.stat().st_size
        if size == 0:
            return None
        if size > MAX_ATTACHMENT_BYTES:
            log.warning("attachment %s is %.1f MB; skipped", path.name, size / 1_048_576)
            return None
        return {
            "filename": path.name,
            "content": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
    except OSError as exc:  # pragma: no cover - unreadable file
        log.warning("could not attach %s: %s", path, exc)
        return None


# --- send -------------------------------------------------------------------------------------


DEFAULT_DISCLAIMER = (
    "Generated from the supplied materials only. Participation is not treated as lead "
    "history, and anything the sources do not establish is labelled NOT PROVIDED or "
    "NOT VERIFIED rather than estimated."
)


def send_analysis_email(
    analysis: LeadInvestorMap,
    pdf_path: str | Path | None,
    *,
    to: str = "",
    config: EmailSettings | None = None,
    disclaimer: str = DEFAULT_DISCLAIMER,
    extra_attachments: Sequence[str | Path] = (),
) -> EmailOutcome:
    """Send the finished map. Returns what happened; never raises."""
    config = config or EmailSettings.from_env()

    if not config.enabled:
        return EmailOutcome(skipped="email disabled")
    if not config.available:
        return EmailOutcome(skipped="no RESEND_API_KEY configured")

    recipients = parse_recipients(to or config.default_to)
    if not recipients:
        raw = (to or config.default_to).strip()
        return EmailOutcome(
            skipped="no recipient configured" if not raw else f"'{raw}' is not a valid email address"
        )

    attachments = []
    if pdf_path is not None:
        pdf = _attachment(Path(pdf_path))
        if pdf:
            attachments.append(pdf)
    for extra in extra_attachments:
        blob = _attachment(Path(extra))
        if blob:
            attachments.append(blob)

    payload = {
        "from": config.from_addr,
        "to": recipients,
        "subject": build_subject(analysis),
        "html": build_html(analysis, disclaimer),
        "text": build_text(analysis, disclaimer),
    }
    if attachments:
        payload["attachments"] = attachments
    if config.reply_to:
        payload["reply_to"] = config.reply_to

    try:
        import requests

        response = requests.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )
    except ImportError:  # pragma: no cover - dependency is declared
        return EmailOutcome(error="requests is not installed; run pip install requests")
    except Exception as exc:  # noqa: BLE001 - a network failure must not escape
        log.warning("Resend request failed: %s", exc)
        return EmailOutcome(to=recipients, error=f"could not reach Resend ({exc})")

    if response.status_code >= 400:
        detail = _error_detail(response)
        log.warning("Resend rejected the message (%s): %s", response.status_code, detail)
        return EmailOutcome(to=recipients, error=_explain(response.status_code, detail, config))

    message_id = ""
    try:
        message_id = str(response.json().get("id", ""))
    except Exception:  # pragma: no cover - non-JSON success body
        pass

    log.info("emailed %s to %s", analysis.company.display_name, ", ".join(recipients))
    return EmailOutcome(sent=True, to=recipients, message_id=message_id)


def _explain(status: int, detail: str, config: EmailSettings) -> str:
    """Turn a Resend rejection into something the reader can act on.

    The unverified-domain 403 is by far the most common failure: until a domain is
    verified, Resend's shared sender delivers only to the account owner, so any other
    recipient looks like a broken integration.
    """
    lowered = detail.lower()
    if status == 403 and ("verify a domain" in lowered or "own email address" in lowered):
        return (
            "Resend will only deliver to the account owner until a sending domain is "
            "verified. Verify the domain at resend.com/domains, then set RESEND_FROM to an "
            f"address on it (currently {config.from_addr}). Resend said: {detail}"
        )
    if status == 401:
        return f"Resend rejected the API key. Check RESEND_API_KEY. Resend said: {detail}"
    if status == 422:
        return f"Resend could not accept the message. Resend said: {detail}"
    if status == 429:
        return f"Resend rate limit reached. Resend said: {detail}"
    return f"Resend returned {status}: {detail}"


def _error_detail(response) -> str:
    try:
        body = response.json()
    except Exception:  # pragma: no cover - non-JSON error body
        return str(getattr(response, "text", ""))[:200]
    return str(body.get("message") or body.get("error") or body)[:300]
