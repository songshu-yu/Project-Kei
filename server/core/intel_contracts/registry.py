"""Process-local collector registry for independently installed source modules."""
from __future__ import annotations

import threading
from typing import Dict, Iterable, Optional

from .models import normalize_source_ids
from .protocols import Collector


class CollectorRegistry:
    """Register at most one Collector 1.0 implementation per source ID."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._collectors: Dict[str, Collector] = {}

    def register(self, collector: Collector) -> None:
        source_id = normalize_source_ids([getattr(collector, "source_id", "")])[0]
        if not callable(getattr(collector, "collect", None)):
            raise TypeError("collector must provide async collect(request)")
        with self._lock:
            existing = self._collectors.get(source_id)
            if existing is collector:
                return
            if existing is not None:
                raise ValueError(f"collector already registered: {source_id}")
            self._collectors[source_id] = collector

    def unregister(self, source_id: str, *, collector: Optional[Collector] = None) -> None:
        normalized = normalize_source_ids([source_id])[0]
        with self._lock:
            existing = self._collectors.get(normalized)
            if existing is None:
                return
            if collector is not None and existing is not collector:
                return
            del self._collectors[normalized]

    def get(self, source_id: str) -> Optional[Collector]:
        normalized = normalize_source_ids([source_id])[0]
        with self._lock:
            return self._collectors.get(normalized)

    def snapshot(self, source_ids: Optional[Iterable[object]] = None) -> Dict[str, Collector]:
        requested = normalize_source_ids(source_ids)
        with self._lock:
            return {
                source_id: self._collectors[source_id]
                for source_id in requested
                if source_id in self._collectors
            }


__all__ = ["CollectorRegistry"]
