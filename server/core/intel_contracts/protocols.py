"""Collector 1.0 protocols shared by source and aggregator modules."""
from __future__ import annotations

from typing import Callable, Protocol, Sequence

from .models import CollectRequest, CollectorResult


class Collector(Protocol):
    source_id: str

    async def collect(self, request: CollectRequest) -> CollectorResult:
        ...


class CollectorGateway(Protocol):
    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]:
        ...


CollectorProgressCallback = Callable[[CollectorResult], None]


class ObservableCollectorGateway(Protocol):
    async def collect_with_progress(
        self,
        request: CollectRequest,
        on_result: CollectorProgressCallback,
    ) -> Sequence[CollectorResult]:
        ...


__all__ = [
    "Collector",
    "CollectorGateway",
    "CollectorProgressCallback",
    "ObservableCollectorGateway",
]
