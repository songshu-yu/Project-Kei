"""Project-owned production composition for the frozen Collector 1.0 sources."""
from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from features.github_intel import GitHubCollector
from features.papers import (
    ArxivCollector,
    ArxivQuery,
    CrossrefCollector,
    PaperCollectorCoordinator,
    SemanticScholarCollector,
    default_paper_http_runtime,
)
from features.rss_intel import RSSIntelCollector
from features.youtube import YouTubeCollector
from intel import intel_config
from intel.collectors.bilibili import BilibiliCollector
from intel.collectors.twitter import NitterCollector

from .collector_gateway import ContractCollectorGateway
from .collector_contracts import Collector, CollectorProgressCallback
from .models import (
    PUBLIC_SOURCE_IDS,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    SourceCoverage,
    rfc3339,
)


PAPER_SOURCE_IDS = frozenset({"arxiv", "crossref", "semantic"})


class CollectorCloseError(RuntimeError):
    """Report bounded close failures only after every unique Collector was tried."""

    def __init__(self, failures: Sequence[tuple[str, str]]) -> None:
        self.failures = tuple(failures)
        super().__init__(f"{len(self.failures)} collector(s) failed to close")


def _enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


class UnavailableCollector:
    """Finite fallback when one optional source cannot be assembled."""

    def __init__(self, source_id: str):
        self.source_id = source_id

    async def collect(self, request: CollectRequest) -> CollectorResult:
        del request
        fetched_at = rfc3339(datetime.now(timezone.utc))
        return CollectorResult(
            source_id=self.source_id,
            items=(),
            warnings=(f"{self.source_id}: collector is unavailable",),
            coverage=SourceCoverage(
                CoverageStatus.NOT_CONFIGURED,
                detail="collector is unavailable",
            ),
            fetched_at=fetched_at,
            cache_status=CacheStatus.UNAVAILABLE,
        )


def _safe_collector(source_id: str, factory: Callable[[], Collector]) -> Collector:
    try:
        return factory()
    except Exception:
        return UnavailableCollector(source_id)


class ProjectCollectorGateway:
    """Run platform Collectors concurrently and paper fallback in source order."""

    def __init__(
        self,
        collectors: Mapping[str, Collector],
        paper_coordinator: PaperCollectorCoordinator,
    ) -> None:
        self._collectors = dict(collectors)
        self._platform_gateway = ContractCollectorGateway(self._collectors)
        self._paper_coordinator = paper_coordinator

    @property
    def supported_source_ids(self) -> tuple[str, ...]:
        return tuple(PUBLIC_SOURCE_IDS)

    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]:
        return await self.collect_with_progress(request, lambda result: None)

    async def collect_with_progress(
        self,
        request: CollectRequest,
        on_result: CollectorProgressCallback,
    ) -> Sequence[CollectorResult]:
        platform_ids = tuple(source for source in request.source_ids if source not in PAPER_SOURCE_IDS)
        paper_ids = tuple(source for source in request.source_ids if source in PAPER_SOURCE_IDS)
        platform_request = replace(request, source_ids=platform_ids) if platform_ids else None
        paper_request = replace(request, source_ids=paper_ids) if paper_ids else None

        platform_call = (
            self._platform_gateway.collect_with_progress(platform_request, on_result)
            if platform_request
            else None
        )

        async def collect_papers() -> Sequence[CollectorResult]:
            results = await self._paper_coordinator.collect(paper_request)
            for result in results:
                on_result(result)
            return results

        paper_call = collect_papers() if paper_request else None
        if platform_call is not None and paper_call is not None:
            platform_results, paper_results = await asyncio.gather(platform_call, paper_call)
        elif platform_call is not None:
            platform_results, paper_results = await platform_call, ()
        elif paper_call is not None:
            platform_results, paper_results = (), await paper_call
        else:
            return ()
        by_source = {result.source_id: result for result in (*platform_results, *paper_results)}
        return tuple(by_source[source] for source in request.source_ids)

    async def aclose(self) -> None:
        seen = set()
        failures: list[tuple[str, str]] = []
        values = [
            self._paper_coordinator,
            *self._collectors.values(),
            *self._paper_coordinator.collectors.values(),
        ]
        for collector in values:
            identity = id(collector)
            if identity in seen:
                continue
            seen.add(identity)
            closer = getattr(collector, "aclose", None)
            if closer is None:
                continue
            try:
                result = closer()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                source_id = str(getattr(collector, "source_id", type(collector).__name__))[:64]
                failures.append((source_id, type(exc).__name__))
        if failures:
            raise CollectorCloseError(failures)


def create_project_collector_gateway(config: Any = intel_config) -> ProjectCollectorGateway:
    """Build all public source adapters without performing network I/O."""
    arxiv_config = getattr(config, "ARXIV_CONFIG", {}) or {}
    queries = tuple(
        ArxivQuery.from_mapping(label, value)
        for label, value in arxiv_config.items()
        if isinstance(value, Mapping)
    )
    money_config = getattr(config, "MONEY_CONFIG", {}) or {}
    if not isinstance(money_config, Mapping):
        money_config = {}

    platform_collectors: dict[str, Collector] = {
        "twitter": _safe_collector(
            "twitter",
            lambda: NitterCollector(getattr(config, "NITTER_INSTANCES", ()) or ()),
        ),
        "github": _safe_collector("github", GitHubCollector),
        "bilibili": _safe_collector("bilibili", BilibiliCollector),
        "youtube": _safe_collector("youtube", YouTubeCollector),
        "money": _safe_collector(
            "money",
            lambda: RSSIntelCollector(
                money_config.get("rss_feeds", ()) or (),
                money_config.get("keywords", ()) or (),
            ),
        ),
    }
    paper_http_runtime = default_paper_http_runtime()
    paper_collectors: dict[str, Collector] = {
        "arxiv": _safe_collector(
            "arxiv",
            lambda: ArxivCollector(queries=queries, runtime=paper_http_runtime),
        ),
    }
    if _enabled("PAPER_ENABLE_CROSSREF_DAILY_SCAN", getattr(config, "PAPER_ENABLE_CROSSREF_DAILY_SCAN", True)):
        paper_collectors["crossref"] = _safe_collector(
            "crossref",
            lambda: CrossrefCollector(
                max_results_per_author=_bounded_int(
                    getattr(config, "PAPER_CROSSREF_MAX_PER_JOURNAL", 8), 8, 1, 100
                ),
                runtime=paper_http_runtime,
            ),
        )
    if _enabled("PAPER_ENABLE_SEMANTIC_SCHOLAR", getattr(config, "PAPER_ENABLE_SEMANTIC_SCHOLAR", True)):
        semantic = _safe_collector(
            "semantic",
            lambda: SemanticScholarCollector(
                max_results_per_author=_bounded_int(
                    getattr(config, "PAPER_SEMANTIC_SCHOLAR_MAX_RESULTS", 10), 10, 1, 100
                ),
                runtime=paper_http_runtime,
            ),
        )
        paper_collectors["semantic"] = semantic
    else:
        semantic = None

    coordinator = PaperCollectorCoordinator(
        paper_collectors,
        semantic_fallback_only=_enabled(
            "PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY",
            getattr(config, "PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY", True),
        ),
        abstract_resolver=semantic if hasattr(semantic, "resolve") else None,
        http_runtime=paper_http_runtime,
    )
    return ProjectCollectorGateway(platform_collectors, coordinator)


__all__ = [
    "CollectorCloseError",
    "ProjectCollectorGateway",
    "UnavailableCollector",
    "create_project_collector_gateway",
]
