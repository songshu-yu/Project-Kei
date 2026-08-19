"""Installable-module registration entrypoint for X/Nitter monitoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .provider import (
    DEFAULT_NITTER_INSTANCES,
    get_collector_registry,
    get_source_snapshot_provider,
)
from .fxembed import fetch_fxembed_posts_window
from .router import build_router
from .service import XMonitorService
from intel.collectors.twitter import NitterCollector


OWNED_ROUTE_PATHS = frozenset({
    "/api/v1/x/profiles",
    "/api/v1/x/profiles/resolve",
    "/api/v1/x/posts",
    "/api/v1/x/posts/fetch",
    "/api/v1/x/posts/query",
    "/dashboard/intel-sources/x-profiles/resolve",
    "/dashboard/intel-sources/x-posts",
    "/dashboard/intel-sources/x-posts/fetch",
})
REGISTRATION_STATE = "x_monitor_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def _server_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == "server":
            return parent
    raise RuntimeError("x_monitor server root is unavailable")


def _route_paths(app: Any) -> Iterable[str]:
    return (
        route.path
        for route in getattr(app, "routes", ())
        if isinstance(getattr(route, "path", None), str)
    )


def register(app: Any) -> None:
    """Register the single X service, legacy/versioned routes and Collector."""
    if getattr(app.state, REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "x_monitor_module_registered", False):
        return
    duplicates = OWNED_ROUTE_PATHS.intersection(_route_paths(app))
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise RuntimeError(f"x_monitor routes are already registered: {names}")

    source_snapshot_provider = get_source_snapshot_provider(app)
    collector_registry = get_collector_registry(app)
    if collector_registry.get("twitter") is not None:
        raise RuntimeError("twitter Collector is already registered")

    configured_profile_path = getattr(app.state, "x_monitor_profile_path", None)
    configured_posts_path = getattr(app.state, "x_monitor_posts_path", None)
    if configured_profile_path is None or configured_posts_path is None:
        data_root = _server_root() / "data"
    profile_path = Path(
        configured_profile_path
        if configured_profile_path is not None
        else data_root / "x_profiles.json"
    )
    posts_path = Path(
        configured_posts_path
        if configured_posts_path is not None
        else data_root / "x_daily_posts.json"
    )
    nitter_instances = tuple(
        getattr(
            app.state,
            "x_monitor_nitter_instances",
            DEFAULT_NITTER_INSTANCES,
        )
    )
    clock = getattr(app.state, "x_monitor_clock", None)
    profile_fetcher = getattr(app.state, "x_monitor_profile_fetcher", None)
    posts_fetcher = getattr(app.state, "x_monitor_posts_fetcher", None)
    posts_query_fetcher = getattr(app.state, "x_monitor_posts_query_fetcher", None)
    fxembed_client = getattr(app.state, "x_monitor_fxembed_client", None)
    fxembed_enabled = getattr(app.state, "x_monitor_fxembed_enabled", True) is True
    collector_client = getattr(app.state, "x_monitor_collector_client", None)

    async def fxembed_query_fetcher(username, start_at, end_at, end_inclusive):
        return await fetch_fxembed_posts_window(
            username,
            start_at=start_at,
            end_at=end_at,
            end_inclusive=end_inclusive,
            client=fxembed_client,
        )

    service = XMonitorService(
        profile_path=profile_path,
        posts_path=posts_path,
        profile_fetcher=profile_fetcher,
        posts_fetcher=posts_fetcher,
        posts_query_fetcher=posts_query_fetcher,
        fxembed_query_fetcher=fxembed_query_fetcher if fxembed_enabled else None,
        nitter_instances=nitter_instances,
        clock=clock,
    )
    collector = NitterCollector(
        nitter_instances,
        client=collector_client,
        clock=clock,
        retries=0 if collector_client is not None else None,
    )
    routes_before = {id(route) for route in app.router.routes}
    previous = {
        name: getattr(app.state, name, _MISSING)
        for name in ("x_monitor_service", "x_monitor_collector")
    }
    collector_registry.register(collector)
    try:
        app.include_router(
            build_router(
                service,
                source_snapshot_provider,
                include_legacy=True,
            )
        )
    except BaseException:
        collector_registry.unregister("twitter", collector=collector)
        _remove_routes(
            app,
            tuple(route for route in app.router.routes if id(route) not in routes_before),
        )
        raise
    routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
    registration = {
        "routes": routes,
        "registry": collector_registry,
        "collector": collector,
        "service": service,
        "previous": previous,
    }
    app.state.x_monitor_service = service
    app.state.x_monitor_collector = collector
    app.state.x_monitor_module_registered = True
    setattr(app.state, REGISTRATION_STATE, registration)


def unregister(app: Any) -> None:
    registration = getattr(app.state, REGISTRATION_STATE, None)
    if not isinstance(registration, dict):
        return
    registry = registration["registry"]
    collector = registration["collector"]
    registry.unregister("twitter", collector=collector)
    _remove_routes(app, registration["routes"])
    for name, owned in (
        ("x_monitor_service", registration["service"]),
        ("x_monitor_collector", collector),
        ("x_monitor_module_registered", True),
        (REGISTRATION_STATE, registration),
    ):
        if getattr(app.state, name, object()) is owned:
            previous = registration.get("previous", {}).get(name, _MISSING)
            if previous is _MISSING:
                delattr(app.state, name)
            else:
                setattr(app.state, name, previous)


__all__ = ["OWNED_ROUTE_PATHS", "register", "unregister"]
