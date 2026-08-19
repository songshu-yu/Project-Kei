"""Stable public protocols for optional calendar consumers."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol


class CalendarSummaryProvider(Protocol):
    """Return the public calendar summary without exposing storage or services."""

    def __call__(self, day: Optional[str] = None) -> Mapping[str, Any]:
        ...


__all__ = ["CalendarSummaryProvider"]
