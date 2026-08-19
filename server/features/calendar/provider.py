"""Public calendar summary provider for optional consumers such as voice."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .service import CalendarService


class CalendarSummaryProvider:
    """Callable public boundary that never exposes the calendar repository."""

    module_id = "calendar"

    def __init__(self, service: CalendarService):
        self._service = service

    def __call__(self, day: Optional[str] = None) -> Dict[str, Any]:
        return self._service.today_summary(day)


__all__ = ["CalendarSummaryProvider"]
