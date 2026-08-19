"""Installable-module registration entrypoint for focus."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .repository import DEFAULT_STORE, FocusRepository
from .router import create_focus_router
from .service import FocusService


_REGISTRATION_STATE = "focus_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def register(app: Any) -> None:
    if getattr(app.state, _REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "focus_module_registered", False):
        return
    configured_path = getattr(app.state, "focus_state_path", DEFAULT_STORE)
    audio_synthesizer = getattr(app.state, "focus_audio_synthesizer", None)
    text_generator_provider = getattr(app.state, "focus_text_generator_provider", None)
    local_request_guard = getattr(app.state, "focus_local_request_guard", None)
    service = FocusService(FocusRepository(Path(configured_path)))
    routes_before = {id(route) for route in app.router.routes}
    previous_service = getattr(app.state, "focus_service", _MISSING)
    try:
        app.include_router(create_focus_router(
            service,
            audio_synthesizer,
            text_generator_provider=text_generator_provider,
            local_request_guard=local_request_guard,
        ))
        routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
        registration = {
            "routes": routes,
            "service": service,
            "previous_service": previous_service,
        }
        app.state.focus_service = service
        app.state.focus_module_registered = True
        setattr(app.state, _REGISTRATION_STATE, registration)
    except BaseException:
        _remove_routes(
            app,
            tuple(route for route in app.router.routes if id(route) not in routes_before),
        )
        raise


def unregister(app: Any) -> None:
    registration = getattr(app.state, _REGISTRATION_STATE, None)
    if not isinstance(registration, dict):
        return
    _remove_routes(app, registration["routes"])
    if getattr(app.state, "focus_service", None) is registration["service"]:
        previous = registration.get("previous_service", _MISSING)
        if previous is _MISSING:
            delattr(app.state, "focus_service")
        else:
            app.state.focus_service = previous
    if getattr(app.state, "focus_module_registered", None) is True:
        delattr(app.state, "focus_module_registered")
    if getattr(app.state, _REGISTRATION_STATE, None) is registration:
        delattr(app.state, _REGISTRATION_STATE)


__all__ = ["register", "unregister"]
