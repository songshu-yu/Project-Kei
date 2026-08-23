"""Installable-module registration entrypoint for daily briefing."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.intel_contracts import CollectorRegistry

from .collector_gateway import RegistryCollectorGateway
from .legacy_adapter import DailyBriefingService
from .router import create_briefing_router
from .voice_adapter import AppStateBriefingVoiceProvider


_REGISTRATION_STATE = "daily_briefing_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def _loopback_request(request: Any) -> bool:
    client = getattr(request, "client", None)
    host = str(getattr(client, "host", "") or "")
    return host == "::1" or host.startswith("127.")


def _optional_provider(app: Any, name: str):
    provider = getattr(app.state, name, None)
    if (
        callable(provider)
        and not callable(getattr(provider, "synthesize_briefing", None))
        and not callable(getattr(provider, "generate_text", None))
    ):
        try:
            return provider()
        except Exception:
            return None
    return provider


def register(app: Any) -> None:
    """Register routes once and consume only explicit optional Core seams."""
    if getattr(app.state, _REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "daily_briefing_module_registered", False):
        return

    registry = getattr(app.state, "intel_collector_registry", None)
    registry_owned = not isinstance(registry, CollectorRegistry)
    if not isinstance(registry, CollectorRegistry):
        registry = CollectorRegistry()
        app.state.intel_collector_registry = registry

    clock = getattr(app.state, "daily_briefing_clock", None)
    gateway = RegistryCollectorGateway(
        registry,
        **({"clock": clock} if callable(clock) else {}),
    )
    root_dir = Path(
        getattr(
            app.state,
            "daily_briefing_root_dir",
            Path.cwd(),
        )
    )
    source_config_provider = getattr(
        app.state,
        "daily_briefing_source_config_provider",
        None,
    )
    if not callable(source_config_provider):
        source_config_provider = lambda: {}
    text_generator = _optional_provider(
        app,
        "daily_briefing_text_generator_provider",
    )
    structural_voice = AppStateBriefingVoiceProvider(app)

    def resolve_voice_provider():
        provider = _optional_provider(
            app,
            "daily_briefing_voice_provider",
        )
        if callable(getattr(provider, "synthesize_briefing", None)):
            return provider
        return structural_voice

    def read_life_forecast_today():
        provider = getattr(app.state, "life_forecast_service", None)
        read_today = getattr(provider, "get_today", None)
        if not callable(read_today):
            return None
        return read_today()

    service_kwargs = {
        "root_dir": root_dir,
        "gateway": gateway,
        "source_config_provider": source_config_provider,
        "text_generator": text_generator,
        "voice_provider_resolver": resolve_voice_provider,
        "life_forecast_provider": read_life_forecast_today,
    }
    if callable(clock):
        service_kwargs["clock"] = clock
    service = DailyBriefingService(**service_kwargs)
    local_guard = getattr(
        app.state,
        "daily_briefing_local_request_guard",
        _loopback_request,
    )
    routes_before = {id(route) for route in app.router.routes}
    previous_service = getattr(app.state, "daily_briefing_service", _MISSING)
    try:
        app.include_router(
            create_briefing_router(
                lambda: service,
                local_request_guard=local_guard,
            )
        )
        routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
        registration = {
            "routes": routes,
            "service": service,
            "registry": registry,
            "registry_owned": registry_owned,
            "previous_service": previous_service,
        }
        app.state.daily_briefing_service = service
        app.state.daily_briefing_module_registered = True
        setattr(app.state, _REGISTRATION_STATE, registration)
    except BaseException:
        _remove_routes(
            app,
            tuple(route for route in app.router.routes if id(route) not in routes_before),
        )
        if (
            registry_owned
            and getattr(app.state, "intel_collector_registry", None) is registry
            and not registry.snapshot()
        ):
            delattr(app.state, "intel_collector_registry")
        raise


def unregister(app: Any) -> None:
    registration = getattr(app.state, _REGISTRATION_STATE, None)
    if not isinstance(registration, dict):
        return
    _remove_routes(app, registration["routes"])
    service = registration["service"]
    if getattr(app.state, "daily_briefing_service", None) is service:
        previous = registration.get("previous_service", _MISSING)
        if previous is _MISSING:
            delattr(app.state, "daily_briefing_service")
        else:
            app.state.daily_briefing_service = previous
    if getattr(app.state, _REGISTRATION_STATE, None) is registration:
        delattr(app.state, _REGISTRATION_STATE)
    if getattr(app.state, "daily_briefing_module_registered", None) is True:
        delattr(app.state, "daily_briefing_module_registered")
    registry = registration["registry"]
    if (
        registration["registry_owned"]
        and getattr(app.state, "intel_collector_registry", None) is registry
        and not registry.snapshot()
    ):
        delattr(app.state, "intel_collector_registry")


__all__ = ["register", "unregister"]
