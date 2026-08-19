"""Installable-module registration entrypoint for intelligence source config."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .models import SOURCE_FIELDS
from .repository import DEFAULT_PATH, IntelSourceConfigRepository
from .router import create_intel_sources_router, create_legacy_intel_sources_router
from .service import IntelSourceRegistry


DefaultsProvider = Callable[[], Mapping[str, Sequence[object]]]
_REGISTRATION_STATE = "intel_sources_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def _restore_state(app: Any, previous: Mapping[str, object]) -> None:
    for name, value in previous.items():
        if value is _MISSING:
            if hasattr(app.state, name):
                delattr(app.state, name)
        else:
            setattr(app.state, name, value)


def empty_intel_source_defaults() -> dict[str, list[object]]:
    """Safe fallback when the host does not provide legacy code defaults."""
    return {field: [] for field in SOURCE_FIELDS}


def _deny_control(_request: Any) -> bool:
    return False


def _require_registry(value: object) -> IntelSourceRegistry:
    required = ("read", "replace", "add", "update", "remove", "snapshot")
    if not all(callable(getattr(value, name, None)) for name in required):
        raise TypeError("intel source registry provider is invalid")
    return value  # type: ignore[return-value]


def _route_keys(routes: Iterable[Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            continue
        for method in getattr(route, "methods", ()) or ():
            keys.add((str(method).upper(), path))
    return keys


def _assert_routes_available(app: Any, routers: Sequence[Any]) -> None:
    existing = _route_keys(app.routes)
    staged: set[tuple[str, str]] = set()
    for router in routers:
        for key in _route_keys(router.routes):
            if key in existing or key in staged:
                raise RuntimeError(f"duplicate route registration blocked: {key[0]} {key[1]}")
            staged.add(key)


def register(app: Any) -> None:
    """Register both HTTP surfaces and stable process-local Provider seams."""
    if getattr(app.state, _REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "intel_sources_module_registered", False):
        return

    configured_registry = getattr(app.state, "intel_source_registry", None)
    if configured_registry is None:
        configured_path = Path(
            getattr(app.state, "intel_source_config_path", DEFAULT_PATH)
        )
        defaults_provider: DefaultsProvider = getattr(
            app.state,
            "intel_source_defaults_provider",
            empty_intel_source_defaults,
        )
        if not callable(defaults_provider):
            raise TypeError("intel source defaults provider must be callable")
        registry = IntelSourceRegistry(
            IntelSourceConfigRepository(configured_path),
            defaults_provider=defaults_provider,
        )
    else:
        registry = _require_registry(configured_registry)

    local_control_guard = getattr(
        app.state,
        "intel_source_local_control_guard",
        _deny_control,
    )
    local_read_guard = getattr(
        app.state,
        "intel_source_local_read_guard",
        local_control_guard,
    )
    if not callable(local_control_guard):
        raise TypeError("intel source local-control guard must be callable")
    if not callable(local_read_guard):
        raise TypeError("intel source local-read guard must be callable")

    routers = (
        create_intel_sources_router(
            registry,
            local_control_guard=local_control_guard,
            local_read_guard=local_read_guard,
        ),
        create_legacy_intel_sources_router(
            registry,
            local_control_guard=local_control_guard,
            local_read_guard=local_read_guard,
        ),
    )
    _assert_routes_available(app, routers)
    routes_before = {id(route) for route in app.router.routes}
    previous = {
        name: getattr(app.state, name, _MISSING)
        for name in (
            "intel_source_registry",
            "intel_source_config_reader",
            "intel_source_snapshot_provider",
            "intel_sources_module_registered",
            _REGISTRATION_STATE,
        )
    }
    try:
        for router in routers:
            app.include_router(router)
        routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
        reader = registry.read
        snapshot_provider = registry.snapshot
        registration = {
            "routes": routes,
            "registry": registry,
            "reader": reader,
            "snapshot_provider": snapshot_provider,
            "previous": previous,
        }
        app.state.intel_source_registry = registry
        app.state.intel_source_config_reader = reader
        app.state.intel_source_snapshot_provider = snapshot_provider
        app.state.intel_sources_module_registered = True
        setattr(app.state, _REGISTRATION_STATE, registration)
    except BaseException:
        _remove_routes(
            app,
            tuple(route for route in app.router.routes if id(route) not in routes_before),
        )
        _restore_state(app, previous)
        raise


def unregister(app: Any) -> None:
    registration = getattr(app.state, _REGISTRATION_STATE, None)
    if not isinstance(registration, dict):
        return
    _remove_routes(app, registration["routes"])
    for name, owned in (
        ("intel_source_registry", registration["registry"]),
        ("intel_source_config_reader", registration["reader"]),
        ("intel_source_snapshot_provider", registration["snapshot_provider"]),
        ("intel_sources_module_registered", True),
        (_REGISTRATION_STATE, registration),
    ):
        if getattr(app.state, name, object()) is owned:
            previous = registration.get("previous", {}).get(name, _MISSING)
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)
__all__ = ["empty_intel_source_defaults", "register", "unregister"]
