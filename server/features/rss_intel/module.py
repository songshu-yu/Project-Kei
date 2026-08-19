"""Installable-module entrypoint for the RSS/Atom intelligence source."""

from __future__ import annotations

from typing import Any, Mapping

from core.intel_contracts import CollectorRegistry

from .collector import SOURCE_ID
from .provider import RSSIntelCollectorProvider


COLLECTOR_REGISTRY_STATE = "intel_collector_registry"
COLLECTOR_PROVIDER_STATE = "rss_intel_collector_provider"
SOURCE_CONFIG_PROVIDER_STATE = "rss_intel_source_config_provider"
COLLECTOR_STATE = "rss_intel_collector"
REGISTERED_STATE = "rss_intel_module_registered"
OWNED_PROVIDER_STATE = "rss_intel_collector_provider_owned"


def _registry(app: Any) -> CollectorRegistry:
    registry = getattr(app.state, COLLECTOR_REGISTRY_STATE, None)
    if registry is None:
        registry = CollectorRegistry()
        setattr(app.state, COLLECTOR_REGISTRY_STATE, registry)
    if not isinstance(registry, CollectorRegistry):
        raise TypeError("app.state.intel_collector_registry must be a CollectorRegistry")
    return registry


def _source_config_mapping(provider):
    value = provider()
    if not isinstance(value, Mapping):
        raise ValueError(
            "app.state.rss_intel_source_config_provider must return a mapping"
        )
    allowed = {"rss_feeds", "keywords", "allowed_redirect_hosts"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(
            f"unknown RSS app-state config field: {sorted(unknown)[0]}"
        )
    return {
        "feed_urls": value.get("rss_feeds", ()),
        "keywords": value.get("keywords", ()),
        "allowed_redirect_hosts": value.get("allowed_redirect_hosts", ()),
    }


def _collector(app: Any):
    provider = getattr(app.state, COLLECTOR_PROVIDER_STATE, None)
    owned_provider = False
    if provider is None:
        source_config_provider = getattr(app.state, SOURCE_CONFIG_PROVIDER_STATE, None)
        if source_config_provider is not None and not callable(source_config_provider):
            raise TypeError(
                "app.state.rss_intel_source_config_provider must be callable"
            )
        provider = RSSIntelCollectorProvider(
            (
                (lambda: _source_config_mapping(source_config_provider))
                if source_config_provider is not None
                else None
            )
        )
        owned_provider = True
    create_collector = getattr(provider, "create_collector", None)
    if not callable(create_collector):
        raise TypeError(
            "app.state.rss_intel_collector_provider must provide "
            "create_collector()"
        )
    collector = create_collector()
    if collector.source_id != SOURCE_ID:
        raise ValueError("RSS provider returned a Collector with the wrong source_id")
    if owned_provider:
        setattr(app.state, COLLECTOR_PROVIDER_STATE, provider)
        setattr(app.state, OWNED_PROVIDER_STATE, True)
    return collector


def register(app: Any) -> None:
    if getattr(app.state, REGISTERED_STATE, False):
        return
    registry = _registry(app)
    collector = _collector(app)
    registry.register(collector)
    setattr(app.state, COLLECTOR_STATE, collector)
    setattr(app.state, REGISTERED_STATE, True)


def unregister(app: Any) -> None:
    registry = getattr(app.state, COLLECTOR_REGISTRY_STATE, None)
    collector = getattr(app.state, COLLECTOR_STATE, None)
    if isinstance(registry, CollectorRegistry) and collector is not None:
        registry.unregister(SOURCE_ID, collector=collector)
    if getattr(app.state, OWNED_PROVIDER_STATE, False):
        for name in (COLLECTOR_PROVIDER_STATE, OWNED_PROVIDER_STATE):
            if hasattr(app.state, name):
                delattr(app.state, name)
    for name in (COLLECTOR_STATE, REGISTERED_STATE):
        if hasattr(app.state, name):
            delattr(app.state, name)


__all__ = [
    "COLLECTOR_PROVIDER_STATE",
    "COLLECTOR_REGISTRY_STATE",
    "COLLECTOR_STATE",
    "OWNED_PROVIDER_STATE",
    "REGISTERED_STATE",
    "SOURCE_CONFIG_PROVIDER_STATE",
    "register",
    "unregister",
]
