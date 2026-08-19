"""Thread-safe process-local registry for the optional calendar summary provider."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from .protocols import CalendarSummaryProvider


def unavailable_calendar_summary() -> Dict[str, Any]:
    """Return a fresh, stable result when calendar is absent or unavailable."""

    return {
        "available": False,
        "error_code": "calendar_unavailable",
        "message": "",
        "skills": [],
    }


class CalendarSummaryProviderRegistry:
    """Hold at most one calendar provider without coupling consumers to PK-190."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._provider: Optional[CalendarSummaryProvider] = None

    def register_calendar_summary_provider(
        self,
        provider: CalendarSummaryProvider,
    ) -> None:
        if not callable(provider):
            raise TypeError("calendar summary provider must be callable")
        with self._lock:
            if self._provider is provider:
                return
            if self._provider is not None:
                raise ValueError("calendar summary provider is already registered")
            self._provider = provider

    def unregister_calendar_summary_provider(
        self,
        provider: Optional[CalendarSummaryProvider] = None,
    ) -> None:
        with self._lock:
            if self._provider is None:
                return
            if provider is not None and self._provider is not provider:
                return
            self._provider = None

    def get(self) -> Optional[CalendarSummaryProvider]:
        with self._lock:
            return self._provider

    def summary(self, day: Optional[str] = None) -> Dict[str, Any]:
        provider = self.get()
        if provider is None:
            return unavailable_calendar_summary()
        try:
            raw = provider(day)
        except TypeError:
            # Compatibility providers predating the public protocol accepted no day.
            try:
                raw = provider()
            except Exception:
                return unavailable_calendar_summary()
        except Exception:
            return unavailable_calendar_summary()
        if not isinstance(raw, dict):
            try:
                raw = dict(raw)
            except Exception:
                return unavailable_calendar_summary()
        result = dict(raw)
        result.setdefault("available", True)
        result.setdefault("error_code", None)
        result.setdefault("message", "")
        result.setdefault("skills", [])
        if not isinstance(result["skills"], list):
            result["skills"] = []
        return result


calendar_summary_registry = CalendarSummaryProviderRegistry()


def get_calendar_summary(day: Optional[str] = None) -> Dict[str, Any]:
    return calendar_summary_registry.summary(day)


__all__ = [
    "CalendarSummaryProviderRegistry",
    "calendar_summary_registry",
    "get_calendar_summary",
    "unavailable_calendar_summary",
]
