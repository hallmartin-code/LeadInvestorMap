"""JSON output: the full analysis, and a companion sources file.

The one-pager shows what fits; the JSON keeps everything, including the per-dimension
scores behind a ranking and every source reference, so a conclusion can be audited or fed
into a CRM later.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models.analysis import LeadInvestorMap


def export_json(analysis: LeadInvestorMap, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = analysis.model_dump(mode="json")
    payload["schema_version"] = "1.0"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_sources(analysis: LeadInvestorMap, path: str | Path) -> Path:
    """Every distinct source, with freshness, so staleness is visible at a glance."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sources = []
    for source in analysis.collect_sources():
        sources.append(
            {
                "source_type": source.source_type.value,
                "source_name": source.source_name,
                "page_or_slide": source.page_or_slide,
                "source_url": source.source_url,
                "source_date": source.source_date,
                "accessed_date": source.accessed_date,
                "freshness": source.freshness.value,
                "source_text": source.source_text,
                "citation": source.citation(),
            }
        )

    payload = {
        "company": analysis.company.display_name,
        "generated_date": analysis.metadata.generated_date,
        "public_research_enabled": analysis.metadata.public_research_enabled,
        "research_backend": analysis.metadata.research_backend,
        "input_files": analysis.metadata.input_files,
        "source_count": len(sources),
        "sources": sources,
        "warnings": [w.model_dump() for w in analysis.warnings],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_json(path: str | Path) -> LeadInvestorMap:
    """Re-hydrate a saved analysis, so a PDF can be re-rendered without re-running it."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload.pop("schema_version", None)
    return LeadInvestorMap.model_validate(payload)
