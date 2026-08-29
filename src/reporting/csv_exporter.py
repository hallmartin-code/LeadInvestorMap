"""CSV output: one row per prospect, for CRM import and pipeline tracking."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models.analysis import LeadInvestorMap
from ..utils.money import format_money

COLUMNS = [
    "investor_name",
    "aliases",
    "investor_type",
    "tier",
    "tier_label",
    "lead_confidence",
    "lead_score",
    "check_min",
    "check_max",
    "can_write_full_lead_check",
    "lead_history_verified",
    "lead_evidence",
    "lead_history_confidence",
    "stage_fit",
    "sector_fit",
    "conflict_level",
    "portfolio_conflicts",
    "fund_status",
    "fund_vintage",
    "relationship",
    "relationship_level",
    "warm_intro_path",
    "diligence_stage",
    "signal_value",
    "investors_influenced",
    "estimated_time_to_term_sheet",
    "timeline_compatible",
    "key_dependency",
    "dependencies",
    "stated_dependencies",
    "likely_objections",
    "required_next_step",
    "next_step_owner",
    "disqualification_reasons",
    "confidence",
    "sources",
    "notes",
]


def export_csv(analysis: LeadInvestorMap, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for investor in analysis.prospects:
            writer.writerow(
                {
                    "investor_name": investor.investor_name,
                    "aliases": "; ".join(investor.aliases),
                    "investor_type": investor.investor_type.value,
                    "tier": int(investor.tier) if investor.tier else "",
                    "tier_label": investor.tier.label if investor.tier else "",
                    "lead_confidence": investor.lead_confidence.value,
                    "lead_score": investor.lead_score if investor.lead_score is not None else "",
                    "check_min": format_money(investor.estimated_check_min, none_text=""),
                    "check_max": format_money(investor.estimated_check_max, none_text=""),
                    "can_write_full_lead_check": _tri(investor.can_write_full_lead_check),
                    "lead_history_verified": "YES" if investor.has_verified_lead_history else "NOT VERIFIED",
                    "lead_evidence": investor.lead_history_display(3),
                    "lead_history_confidence": investor.lead_history_confidence.value,
                    "stage_fit": investor.stage_fit.value,
                    "sector_fit": investor.sector_fit.value,
                    "conflict_level": investor.conflict_level.value,
                    "portfolio_conflicts": "; ".join(
                        f"{c.company} ({c.level.value})" for c in investor.portfolio_conflicts
                    ),
                    "fund_status": investor.fund_status.value,
                    "fund_vintage": investor.fund_vintage or "",
                    "relationship": investor.relationship_strength.label,
                    "relationship_level": int(investor.relationship_strength),
                    "warm_intro_path": investor.warm_intro_path or "",
                    "diligence_stage": investor.current_diligence_stage.value,
                    "signal_value": investor.signal_value.value,
                    "investors_influenced": "; ".join(investor.investors_influenced),
                    "estimated_time_to_term_sheet": investor.estimated_time_to_term_sheet or "",
                    "timeline_compatible": _tri(investor.timeline_compatible),
                    "key_dependency": investor.key_dependency,
                    "dependencies": "; ".join(investor.dependencies),
                    "stated_dependencies": "; ".join(investor.stated_dependencies),
                    "likely_objections": "; ".join(investor.likely_objections),
                    "required_next_step": investor.required_next_step,
                    "next_step_owner": investor.next_step_owner,
                    "disqualification_reasons": "; ".join(r.value for r in investor.disqualification_reasons),
                    "confidence": investor.confidence.value,
                    "sources": " | ".join(s.citation() for s in investor.sources[:5]),
                    "notes": investor.notes,
                }
            )
    return path


def _tri(value: bool | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "YES" if value else "NO"
