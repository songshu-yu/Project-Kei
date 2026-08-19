"""Installable-module registration entrypoint for the YouTube Collector."""

from __future__ import annotations

from typing import Any, Callable

from core.intel_contracts import Collector, CollectorRegistry

from .collector import SOURCE_ID, YouTubeCollector


REGISTRY_STATE_ATTRIBUTE = "collector_registry"
PROVIDER_STATE_ATTRIBUTE = "youtube_collector_provider"
COLLECTOR_STATE_ATTRIBUTE = "youtube_collector"
MODULE_REGISTERED_STATE_ATTRIBUTE = "youtube_module_registered"
REGISTRATION_STATE_ATTRIBUTE = "youtube_module_registration"


def _registry(app: Any) -> tuple[CollectorRegistry, bool]:
    state = getattr(app, "state", None)
    if state is None:
        raise TypeError("YouTube module requires an application state object")
    registry = getattr(state, REGISTRY_STATE_ATTRIBUTE, None)
    owned = registry is None
    if registry is None:
        registry = CollectorRegistry()
        setattr(state, REGISTRY_STATE_ATTRIBUTE, registry)
    if not isinstance(registry, CollectorRegistry):
        raise TypeError("app.state.collector_registry must be a Core CollectorRegistry")
    return registry, owned


def _collector_provider(app: Any) -> Callable[[], Collector]:
    provider = getattr(app.state, PROVIDER_STATE_ATTRIBUTE, None)
    if provider is None:
        return YouTubeCollector
    if not callable(provider):
        raise TypeError("app.state.youtube_collector_provider must be callable")
    return provider


def register(app: Any) -> None:
    """Register one YouTube Collector without reading configuration or networking."""
    if getattr(app.state, REGISTRATION_STATE_ATTRIBUTE, None) is not None:
        return
    if getattr(app.state, MODULE_REGISTERED_STATE_ATTRIBUTE, False):
        return
    registry, registry_owned = _registry(app)
    existing = getattr(app.state, COLLECTOR_STATE_ATTRIBUTE, None)
    if existing is not None and registry.get(SOURCE_ID) is existing:
        registration = {
            "registry": registry,
            "registry_owned": registry_owned,
            "collector": existing,
            "collector_owned": False,
        }
        setattr(app.state, MODULE_REGISTERED_STATE_ATTRIBUTE, True)
        setattr(app.state, REGISTRATION_STATE_ATTRIBUTE, registration)
        return

    try:
        collector = _collector_provider(app)()
        if getattr(collector, "source_id", None) != SOURCE_ID:
            raise ValueError("YouTube Collector provider returned the wrong source_id")
        if not callable(getattr(collector, "collect", None)):
            raise TypeError("YouTube Collector provider must return Collector 1.0")

        registry.register(collector)
        registration = {
            "registry": registry,
            "registry_owned": registry_owned,
            "collector": collector,
            "collector_owned": True,
        }
        setattr(app.state, COLLECTOR_STATE_ATTRIBUTE, collector)
        setattr(app.state, MODULE_REGISTERED_STATE_ATTRIBUTE, True)
        setattr(app.state, REGISTRATION_STATE_ATTRIBUTE, registration)
    except BaseException:
        collector = locals().get("collector")
        if collector is not None:
            registry.unregister(SOURCE_ID, collector=collector)
        if registry_owned and getattr(app.state, REGISTRY_STATE_ATTRIBUTE, None) is registry:
            delattr(app.state, REGISTRY_STATE_ATTRIBUTE)
        raise


def unregister(app: Any) -> None:
    """Remove only the Collector and state created by this registration."""
    registration = getattr(app.state, REGISTRATION_STATE_ATTRIBUTE, None)
    if not isinstance(registration, dict):
        return
    registry = registration.get("registry")
    collector = registration.get("collector")
    if (
        registration.get("collector_owned")
        and isinstance(registry, CollectorRegistry)
        and collector is not None
    ):
        registry.unregister(SOURCE_ID, collector=collector)
    owned_state = [
        (MODULE_REGISTERED_STATE_ATTRIBUTE, True),
        (REGISTRATION_STATE_ATTRIBUTE, registration),
    ]
    if registration.get("collector_owned"):
        owned_state.append((COLLECTOR_STATE_ATTRIBUTE, collector))
    for name, owned in owned_state:
        if getattr(app.state, name, object()) is owned:
            delattr(app.state, name)
    if (
        registration.get("registry_owned")
        and getattr(app.state, REGISTRY_STATE_ATTRIBUTE, None) is registry
        and not registry.snapshot()
    ):
        delattr(app.state, REGISTRY_STATE_ATTRIBUTE)


__all__ = [
    "COLLECTOR_STATE_ATTRIBUTE",
    "MODULE_REGISTERED_STATE_ATTRIBUTE",
    "PROVIDER_STATE_ATTRIBUTE",
    "REGISTRY_STATE_ATTRIBUTE",
    "register",
    "unregister",
]
