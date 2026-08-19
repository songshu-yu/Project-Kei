"""Stable Core boundary for Project Kei intelligence modules."""

from .models import (
    COLLECTOR_CONTRACT_VERSION,
    PUBLIC_SOURCE_IDS,
    PUBLIC_SOURCE_ID_SET,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    aware_timestamp,
    ensure_compatible_contract,
    is_valid_source_id,
    json_safe_mapping,
    normalize_source_ids,
    normalize_url,
    rfc3339,
    sanitize_external_text,
    stable_item_id,
)
from .protocols import (
    Collector,
    CollectorGateway,
    CollectorProgressCallback,
    ObservableCollectorGateway,
)
from .registry import CollectorRegistry
from .time import get_timezone, localize

__all__ = [
    "COLLECTOR_CONTRACT_VERSION",
    "PUBLIC_SOURCE_IDS",
    "PUBLIC_SOURCE_ID_SET",
    "CacheStatus",
    "CollectRequest",
    "Collector",
    "CollectorGateway",
    "CollectorProgressCallback",
    "CollectorRegistry",
    "CollectorResult",
    "CoverageStatus",
    "IntelItem",
    "ObservableCollectorGateway",
    "SourceCoverage",
    "aware_timestamp",
    "ensure_compatible_contract",
    "get_timezone",
    "is_valid_source_id",
    "json_safe_mapping",
    "localize",
    "normalize_source_ids",
    "normalize_url",
    "rfc3339",
    "sanitize_external_text",
    "stable_item_id",
]
