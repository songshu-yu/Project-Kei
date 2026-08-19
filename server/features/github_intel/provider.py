"""Core CollectorRegistry provider seam for the GitHub source module."""

from __future__ import annotations

from typing import Any

from core.intel_contracts import CollectorRegistry

from .collector import GitHubCollector


REGISTRY_STATE_ATTRIBUTE = "intel_collector_registry"
COLLECTOR_STATE_ATTRIBUTE = "github_intel_collector"


def register(app: Any) -> GitHubCollector:
    """Register one GitHub Collector in the Core-owned process registry."""
    registry = getattr(app.state, REGISTRY_STATE_ATTRIBUTE, None)
    if not isinstance(registry, CollectorRegistry):
        registry = CollectorRegistry()
        setattr(app.state, REGISTRY_STATE_ATTRIBUTE, registry)

    managed = getattr(app.state, COLLECTOR_STATE_ATTRIBUTE, None)
    if managed is not None:
        if registry.get("github") is managed:
            return managed
        raise RuntimeError("GitHub Collector provider state is inconsistent")

    collector = GitHubCollector()
    registry.register(collector)
    setattr(app.state, COLLECTOR_STATE_ATTRIBUTE, collector)
    return collector


__all__ = [
    "COLLECTOR_STATE_ATTRIBUTE",
    "REGISTRY_STATE_ATTRIBUTE",
    "register",
]
