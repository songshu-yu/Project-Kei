"""Stable Core boundary between calendar packages and optional consumers."""

from .protocols import CalendarSummaryProvider
from .registry import (
    CalendarSummaryProviderRegistry,
    calendar_summary_registry,
    get_calendar_summary,
    unavailable_calendar_summary,
)

__all__ = [
    "CalendarSummaryProvider",
    "CalendarSummaryProviderRegistry",
    "calendar_summary_registry",
    "get_calendar_summary",
    "unavailable_calendar_summary",
]
