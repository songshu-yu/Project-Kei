"""Installable-module registration entrypoint for calendar."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .provider import CalendarSummaryProvider
from .repository import DEFAULT_STORE, CalendarMemoStore
from .router import create_calendar_router
from .service import CalendarService


CALENDAR_ROUTE_PATHS = frozenset({
    "/api/v1/calendar/today",
    "/api/v1/calendar/status",
    "/api/v1/calendar/events",
    "/api/v1/calendar/practice",
    "/api/v1/calendar/reset",
    "/calendar/today",
    "/calendar/status",
    "/calendar/event",
    "/calendar/practice",
    "/calendar/reset",
})


def _route_paths(app: Any) -> Iterable[str]:
    return (
        route.path
        for route in getattr(app, "routes", ())
        if isinstance(getattr(route, "path", None), str)
    )


def _register_voice_provider(app: Any, provider: CalendarSummaryProvider) -> None:
    """Offer the provider without importing or reaching into the voice module."""
    app.state.calendar_summary_provider = provider
    registry = getattr(app.state, "voice_calendar_provider_registry", None)
    if registry is not None:
        registry.register_calendar_summary_provider(provider)
        app.state.calendar_voice_provider_registry = registry


def _unregister_voice_provider(app: Any) -> None:
    registry = getattr(app.state, "calendar_voice_provider_registry", None)
    provider = getattr(app.state, "calendar_summary_provider", None)
    if registry is not None and provider is not None:
        registry.unregister_calendar_summary_provider(provider)
    for name in ("calendar_voice_provider_registry", "calendar_summary_provider"):
        if hasattr(app.state, name):
            delattr(app.state, name)


def register(app: Any) -> None:
    if getattr(app.state, "calendar_module_registered", False):
        return

    conflicts = CALENDAR_ROUTE_PATHS.intersection(_route_paths(app))
    if conflicts:
        joined = ", ".join(sorted(conflicts))
        raise RuntimeError(f"calendar routes are already registered: {joined}")

    configured_path = Path(getattr(app.state, "calendar_state_path", DEFAULT_STORE))
    service = CalendarService(CalendarMemoStore(configured_path))
    provider = CalendarSummaryProvider(service)
    app.include_router(create_calendar_router(service))
    app.state.calendar_service = service
    _register_voice_provider(app, provider)
    app.state.calendar_module_registered = True


def unregister(app: Any) -> None:
    """Release provider references; route removal still follows restart semantics."""
    _unregister_voice_provider(app)
    for name in ("calendar_service", "calendar_module_registered"):
        if hasattr(app.state, name):
            delattr(app.state, name)


__all__ = [
    "CALENDAR_ROUTE_PATHS",
    "register",
    "unregister",
]
