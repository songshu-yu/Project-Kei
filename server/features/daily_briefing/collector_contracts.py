"""Compatibility re-export for the Core-owned Collector 1.0 protocols."""

from core.intel_contracts import (
    Collector,
    CollectorGateway,
    CollectorProgressCallback,
    ObservableCollectorGateway,
)

__all__ = [
    "Collector",
    "CollectorGateway",
    "CollectorProgressCallback",
    "ObservableCollectorGateway",
]
