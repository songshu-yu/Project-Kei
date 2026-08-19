"""Installable-module registration entrypoint for demon slayer."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Tuple

from .repository import DEFAULT_STORE, DemonSlayerStore
from .router import create_demon_slayer_router
from .service import DemonSlayerService


_REGISTRATION_STATE = "demon_slayer_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def _route_signatures(routes: Iterable[Any]) -> set[Tuple[str, str, str]]:
    signatures: set[Tuple[str, str, str]] = set()
    for route in routes:
        path = getattr(route, "path", None)
        name = getattr(route, "name", None)
        methods = getattr(route, "methods", None)
        if not isinstance(path, str) or not isinstance(name, str) or not methods:
            continue
        for method in methods:
            signatures.add((path, str(method).upper(), name))
    return signatures


def _text_generator_provider(app: Any):
    provider = getattr(app.state, "demon_slayer_text_generator_provider", None)
    return provider if callable(provider) else (lambda: None)


def register(app: Any) -> None:
    """Register one versioned/legacy router without reading personal state."""

    if getattr(app.state, _REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "demon_slayer_module_registered", False):
        return

    state_path = Path(getattr(app.state, "demon_slayer_state_path", DEFAULT_STORE))
    service = DemonSlayerService(
        DemonSlayerStore(state_path),
        text_generator_provider=_text_generator_provider(app),
        clock=getattr(app.state, "demon_slayer_clock", None) or date.today,
        timestamp=getattr(app.state, "demon_slayer_timestamp", None) or datetime.now,
    )
    router = create_demon_slayer_router(
        service,
        audio_synthesizer=getattr(app.state, "demon_slayer_audio_synthesizer", None),
    )
    candidate = _route_signatures(router.routes)
    existing = _route_signatures(app.routes)
    candidate_keys = {(path, method) for path, method, _name in candidate}
    existing_keys = {(path, method) for path, method, _name in existing}
    overlaps = candidate_keys & existing_keys

    if overlaps:
        if candidate_keys <= existing_keys and candidate <= existing:
            previous_mode = getattr(
                app.state, "demon_slayer_module_registration", _MISSING
            )
            app.state.demon_slayer_module_registered = True
            app.state.demon_slayer_module_registration = "preexisting_compatible_routes"
            registration = {
                "mode": "preexisting_compatible_routes",
                "previous": {
                    "demon_slayer_module_registration": previous_mode,
                },
            }
            setattr(app.state, _REGISTRATION_STATE, registration)
            return
        raise RuntimeError("demon-slayer routes conflict with an existing partial registration")

    routes_before = {id(route) for route in app.router.routes}
    previous = {
        name: getattr(app.state, name, _MISSING)
        for name in ("demon_slayer_service", "demon_slayer_module_registration")
    }
    try:
        app.include_router(router)
        routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
        registration = {
            "mode": "installed_package",
            "routes": routes,
            "service": service,
            "previous": previous,
        }
        app.state.demon_slayer_service = service
        app.state.demon_slayer_module_registered = True
        app.state.demon_slayer_module_registration = "installed_package"
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
    if registration["mode"] == "installed_package":
        _remove_routes(app, registration["routes"])
        if getattr(app.state, "demon_slayer_service", None) is registration["service"]:
            previous = registration.get("previous", {}).get(
                "demon_slayer_service", _MISSING
            )
            if previous is _MISSING:
                delattr(app.state, "demon_slayer_service")
            else:
                app.state.demon_slayer_service = previous
    if getattr(app.state, "demon_slayer_module_registered", None) is True:
        delattr(app.state, "demon_slayer_module_registered")
    if getattr(app.state, "demon_slayer_module_registration", None) == registration["mode"]:
        previous = registration.get("previous", {}).get(
            "demon_slayer_module_registration", _MISSING
        )
        if previous is _MISSING:
            delattr(app.state, "demon_slayer_module_registration")
        else:
            app.state.demon_slayer_module_registration = previous
    if getattr(app.state, _REGISTRATION_STATE, None) is registration:
        delattr(app.state, _REGISTRATION_STATE)


__all__ = ["register", "unregister"]
