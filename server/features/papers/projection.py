"""Read-only projection of cached briefing items for the papers dashboard."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from core.intel_contracts import (
    IntelItem,
    SourceCoverage,
    sanitize_external_text,
)

from .domain import PAPER_SOURCE_IDS, deduplicate_paper_items


def _paper_item(value: object) -> Optional[IntelItem]:
    if not isinstance(value, Mapping) or value.get("category") != "papers":
        return None
    try:
        return IntelItem.from_dict(value)
    except (TypeError, ValueError):
        return None


def _coverage(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    for source_id in PAPER_SOURCE_IDS:
        raw = value.get(source_id)
        if not isinstance(raw, Mapping):
            continue
        try:
            projected[source_id] = SourceCoverage.from_dict(raw).to_dict()
        except (TypeError, ValueError):
            continue
    return projected


def project_today_payload(payload: object) -> dict[str, Any]:
    """Return safe paper fields without collecting, persisting, or enriching."""
    if not isinstance(payload, Mapping) or not payload.get("ready"):
        return {
            "ready": False,
            "date": sanitize_external_text(
                payload.get("date", "") if isinstance(payload, Mapping) else "",
                limit=32,
            ),
            "items": [],
            "coverage": {},
            "warnings": [],
            "script": "",
        }

    raw_items = payload.get("items", ())
    parsed = (
        item
        for value in raw_items
        if (item := _paper_item(value)) is not None
    ) if isinstance(raw_items, (list, tuple)) else ()
    items = deduplicate_paper_items(parsed)
    warnings = payload.get("warnings", ())
    return {
        "ready": True,
        "date": sanitize_external_text(payload.get("date", ""), limit=32),
        "items": [
            {
                "stable_id": item.stable_id,
                "source_id": item.source_id,
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "author": item.author,
                "published_at": item.published_at,
            }
            for item in items
        ],
        "coverage": _coverage(payload.get("coverage")),
        "warnings": [
            cleaned
            for value in (warnings if isinstance(warnings, (list, tuple)) else ())
            if (cleaned := sanitize_external_text(value, limit=240))
        ],
        "script": sanitize_external_text(payload.get("script", ""), limit=4000),
    }


__all__ = ["project_today_payload"]
