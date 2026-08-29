"""The degradation ladder that keeps the map to exactly one page.

The order is deliberate and matches the specification: shorten narrative first, then drop
low-priority fields, then tighten spacing, and only then reduce type - never below the
readability floor. Each rung is re-measured; the first that fits is used, and whatever was
given up is recorded so the run can say so out loud.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FitConfig:
    """One rung of the ladder."""

    body_size: float = 8.0
    spacing_scale: float = 1.0
    narrative_chars: int = 150
    max_candidates: int = 8
    max_disqualified: int = 7
    max_gaps: int = 5
    max_fallbacks: int = 2
    max_phase_names: int = 5
    max_momentum_steps: int = 4
    show_objections: bool = True
    show_next_step_column: bool = True

    def describe_drops(self, base: "FitConfig") -> list[str]:
        drops: list[str] = []
        if self.narrative_chars < base.narrative_chars:
            drops.append(f"candidate narrative trimmed to {self.narrative_chars} characters")
        if not self.show_objections and base.show_objections:
            drops.append("company objections omitted")
        if self.max_gaps < base.max_gaps:
            drops.append(f"gaps trimmed to {self.max_gaps}")
        if self.max_fallbacks < base.max_fallbacks:
            drops.append(f"fallback structures trimmed to {self.max_fallbacks}")
        if self.max_disqualified < base.max_disqualified:
            drops.append(f"disqualification list trimmed to {self.max_disqualified}")
        if self.max_phase_names < base.max_phase_names:
            drops.append(f"outreach phases trimmed to {self.max_phase_names} names each")
        if self.max_candidates < base.max_candidates:
            drops.append(f"lead candidates trimmed to {self.max_candidates}")
        if self.max_momentum_steps < base.max_momentum_steps:
            drops.append(f"momentum path trimmed to {self.max_momentum_steps} steps")
        if self.spacing_scale < base.spacing_scale:
            drops.append(f"section spacing reduced {round((1 - self.spacing_scale) * 100)}%")
        if not self.show_next_step_column and base.show_next_step_column:
            drops.append("next-step column moved out of the candidate table")
        if self.body_size < base.body_size:
            drops.append(f"body type reduced {base.body_size:g}pt to {self.body_size:g}pt")
        return drops


BASE = FitConfig()

LADDER: tuple[FitConfig, ...] = (
    BASE,
    replace(BASE, narrative_chars=120),
    replace(BASE, narrative_chars=110, max_gaps=4),
    replace(BASE, narrative_chars=100, max_gaps=4, max_disqualified=6),
    replace(BASE, narrative_chars=95, max_gaps=4, max_disqualified=5, spacing_scale=0.9),
    replace(
        BASE,
        narrative_chars=90,
        max_gaps=4,
        max_disqualified=5,
        max_phase_names=4,
        spacing_scale=0.9,
    ),
    replace(
        BASE,
        narrative_chars=85,
        max_gaps=3,
        max_disqualified=4,
        max_phase_names=4,
        spacing_scale=0.85,
        show_objections=False,
        max_fallbacks=1,
    ),
    replace(
        BASE,
        body_size=7.7,
        narrative_chars=85,
        max_gaps=3,
        max_disqualified=4,
        max_phase_names=4,
        spacing_scale=0.85,
        show_objections=False,
        max_fallbacks=1,
    ),
    replace(
        BASE,
        body_size=7.5,
        narrative_chars=80,
        max_gaps=3,
        max_disqualified=4,
        max_phase_names=3,
        max_candidates=7,
        max_fallbacks=1,
        spacing_scale=0.82,
        show_objections=False,
    ),
    replace(
        BASE,
        body_size=7.5,
        narrative_chars=75,
        max_gaps=3,
        max_disqualified=3,
        max_phase_names=3,
        max_candidates=6,
        max_fallbacks=1,
        max_momentum_steps=3,
        spacing_scale=0.8,
        show_objections=False,
    ),
    replace(
        BASE,
        body_size=7.5,
        narrative_chars=70,
        max_gaps=2,
        max_disqualified=3,
        max_phase_names=3,
        max_candidates=5,
        max_fallbacks=1,
        max_momentum_steps=3,
        spacing_scale=0.78,
        show_objections=False,
        show_next_step_column=False,
    ),
)
