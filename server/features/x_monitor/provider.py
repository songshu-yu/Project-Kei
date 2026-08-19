"""Public composition seams used by the installable X monitor module."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from core.intel_contracts import CollectorRegistry


SourceSnapshotProvider = Callable[[], Mapping[str, object]]
DEFAULT_NITTER_INSTANCES = ("https://nitter.net",)


def get_source_snapshot_provider(app: Any) -> SourceSnapshotProvider:
    """Resolve only the public PK-115 snapshot provider exposed on app state."""
    provider = getattr(app.state, "intel_source_snapshot_provider", None)
    if callable(provider):
        return provider
    registry = getattr(app.state, "intel_source_registry", None)
    reader = getattr(registry, "read", None)
    if callable(reader):
        return reader
    raise RuntimeError("x_monitor requires the intel_sources snapshot provider")


def get_collector_registry(app: Any) -> CollectorRegistry:
    registry = getattr(app.state, "intel_collector_registry", None)
    if not isinstance(registry, CollectorRegistry):
        raise RuntimeError("x_monitor requires the Core CollectorRegistry")
    return registry


__all__ = [
    "DEFAULT_NITTER_INSTANCES",
    "SourceSnapshotProvider",
    "get_collector_registry",
    "get_source_snapshot_provider",
]
