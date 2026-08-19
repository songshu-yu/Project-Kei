"""Daily briefing module public boundary."""

from .collector_contracts import (
    Collector,
    CollectorGateway,
    CollectorProgressCallback,
    ObservableCollectorGateway,
)
from .models import (
    COLLECTOR_CONTRACT_VERSION,
    PUBLIC_SOURCE_IDS,
    BriefingDocument,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    json_safe_mapping,
    normalize_url,
    sanitize_external_text,
)
from .module import register, unregister
from .providers import BriefingVoiceProvider, BriefingVoiceProviderResolver

__all__ = [
    "COLLECTOR_CONTRACT_VERSION",
    "PUBLIC_SOURCE_IDS",
    "BriefingDocument",
    "BriefingVoiceProvider",
    "BriefingVoiceProviderResolver",
    "CacheStatus",
    "CollectRequest",
    "Collector",
    "CollectorGateway",
    "CollectorProgressCallback",
    "CollectorResult",
    "CoverageStatus",
    "IntelItem",
    "ObservableCollectorGateway",
    "SourceCoverage",
    "json_safe_mapping",
    "normalize_url",
    "sanitize_external_text",
    "register",
    "unregister",
]
