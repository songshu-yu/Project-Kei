"""Installable-module registration entrypoint for fitness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .repository import FitnessRepository
from .router import create_fitness_router
from .security import FitnessOriginGuardMiddleware
from .service import FitnessService


_ROUTE_NAMES = {
    "/api/v1/fitness/status": "fitness_status_versioned",
    "/api/v1/fitness/checkins": "fitness_checkin_versioned",
    "/fitness/status": "fitness_status_legacy",
    "/fitness/checkin": "fitness_checkin_legacy",
    "/fitness/reset": "fitness_reset_legacy",
}
_REGISTRATION_STATE = "fitness_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def _remove_middleware(app: Any, middleware: object | None) -> None:
    if middleware is None:
        return
    app.user_middleware[:] = [item for item in app.user_middleware if item is not middleware]


def _reuse_complete_legacy_assembly(app: Any) -> bool:
    """Reuse the frozen transition assembly without creating duplicate routes."""

    matches = {
        path: [
            route
            for route in app.routes
            if getattr(route, "path", None) == path
        ]
        for path in _ROUTE_NAMES
    }
    present = {path for path, routes in matches.items() if routes}
    if not present:
        return False
    if present != set(_ROUTE_NAMES):
        raise RuntimeError("fitness route assembly is incomplete")
    if any(
        len(matches[path]) != 1
        or getattr(matches[path][0], "name", None) != expected_name
        for path, expected_name in _ROUTE_NAMES.items()
    ):
        raise RuntimeError("fitness route assembly conflicts with the module contract")
    app.state.fitness_module_registration_mode = "existing_routes"
    return True


def register(app: Any) -> None:
    """Register one shared fitness service for versioned and legacy HTTP."""

    if getattr(app.state, _REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "fitness_module_registered", False):
        return
    previous_mode = getattr(app.state, "fitness_module_registration_mode", _MISSING)
    if _reuse_complete_legacy_assembly(app):
        app.state.fitness_module_registered = True
        registration = {
            "mode": "existing_routes",
            "previous": {"fitness_module_registration_mode": previous_mode},
        }
        setattr(app.state, _REGISTRATION_STATE, registration)
        return

    configured_path = getattr(app.state, "fitness_state_path", None)
    if configured_path is None:
        raise RuntimeError("fitness state path is not configured")

    service = FitnessService(FitnessRepository(Path(configured_path)))
    router_options = {}
    audio_synthesizer = getattr(app.state, "fitness_audio_synthesizer", None)
    local_control_guard = getattr(app.state, "fitness_local_control_guard", None)
    local_read_guard = getattr(app.state, "fitness_local_read_guard", None)
    if audio_synthesizer is not None:
        router_options["audio_synthesizer"] = audio_synthesizer
    if local_control_guard is not None:
        router_options["local_control_guard"] = local_control_guard
    if local_read_guard is not None:
        router_options["local_read_guard"] = local_read_guard

    routes_before = {id(route) for route in app.router.routes}
    middleware_before = {id(item) for item in app.user_middleware}
    previous = {
        name: getattr(app.state, name, _MISSING)
        for name in ("fitness_service", "fitness_module_registration_mode")
    }
    middleware = None
    try:
        app.add_middleware(FitnessOriginGuardMiddleware)
        middleware = next(
            item for item in app.user_middleware if id(item) not in middleware_before
        )
        app.include_router(create_fitness_router(service, **router_options))
        routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
        registration = {
            "mode": "module",
            "routes": routes,
            "middleware": middleware,
            "service": service,
            "previous": previous,
        }
        app.state.fitness_service = service
        app.state.fitness_module_registration_mode = "module"
        app.state.fitness_module_registered = True
        setattr(app.state, _REGISTRATION_STATE, registration)
    except BaseException:
        _remove_routes(
            app,
            tuple(route for route in app.router.routes if id(route) not in routes_before),
        )
        for item in tuple(
            item for item in app.user_middleware if id(item) not in middleware_before
        ):
            _remove_middleware(app, item)
        raise


def unregister(app: Any) -> None:
    """Idempotently remove only this registration's state and middleware."""
    registration = getattr(app.state, _REGISTRATION_STATE, None)
    if not isinstance(registration, dict):
        return
    if registration.get("mode") == "module":
        _remove_routes(app, registration.get("routes", ()))
        _remove_middleware(app, registration.get("middleware"))
    for name, owned in (
        ("fitness_service", registration.get("service")),
        ("fitness_module_registration_mode", registration.get("mode")),
        ("fitness_module_registered", True),
        (_REGISTRATION_STATE, registration),
    ):
        current = getattr(app.state, name, object())
        if current is owned or (
            name == "fitness_module_registration_mode" and current == owned
        ):
            previous = registration.get("previous", {}).get(name, _MISSING)
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)


__all__ = ["register", "unregister"]
