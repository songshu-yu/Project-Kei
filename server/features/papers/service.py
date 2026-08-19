"""Failure-isolated orchestration for the three independent paper sources."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Mapping, Optional, Protocol, Sequence

from core.intel_contracts import (
    Collector,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    rfc3339,
)

from .domain import (
    PAPER_SOURCE_IDS,
    authors_from_snapshot,
    covered_authors,
    deduplicate_paper_items,
    normalize_author_name,
    paper_identity_key,
    request_with_authors,
)
from .http import PaperHttpRuntime


@dataclass(frozen=True)
class PaperCollectionBatch:
    results: tuple[CollectorResult, ...]
    deduplicated_items: tuple[IntelItem, ...]


@dataclass(frozen=True)
class AbstractResolution:
    text: str
    source_id: str


class AbstractResolver(Protocol):
    async def resolve(self, item: IntelItem) -> Optional[AbstractResolution]:
        ...


class PaperCollectorCoordinator:
    """Coordinate fallback without collapsing source-specific result objects."""

    def __init__(
        self,
        collectors: Mapping[str, Collector],
        *,
        semantic_fallback_only: bool = True,
        abstract_resolver: Optional[AbstractResolver] = None,
        http_runtime: Optional[PaperHttpRuntime] = None,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.collectors = {source_id: collectors[source_id] for source_id in PAPER_SOURCE_IDS if source_id in collectors}
        self.semantic_fallback_only = semantic_fallback_only
        self.abstract_resolver = abstract_resolver
        self.http_runtime = http_runtime
        self.clock = clock

    def _failed(self, source_id: str, error: BaseException) -> CollectorResult:
        fetched_at = rfc3339(self.clock())
        detail = f"{source_id} collection failed ({type(error).__name__})"
        return CollectorResult(
            source_id=source_id,
            items=(),
            warnings=(detail,),
            coverage=SourceCoverage(CoverageStatus.FAILED, detail=detail),
            fetched_at=fetched_at,
            cache_status=CacheStatus.UNAVAILABLE,
        )

    def _not_configured(self, source_id: str) -> CollectorResult:
        fetched_at = rfc3339(self.clock())
        return CollectorResult(
            source_id=source_id,
            items=(),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail=f"{source_id} collector is not registered"),
            fetched_at=fetched_at,
            cache_status=CacheStatus.UNAVAILABLE,
        )

    def _fallback_covered(self) -> CollectorResult:
        fetched_at = rfc3339(self.clock())
        return CollectorResult(
            source_id="semantic",
            items=(),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.EMPTY, detail="fallback authors already covered by other paper sources"),
            fetched_at=fetched_at,
            cache_status=CacheStatus.BYPASS,
        )

    async def _collect_one(self, source_id: str, request: CollectRequest) -> CollectorResult:
        collector = self.collectors.get(source_id)
        if collector is None:
            return self._not_configured(source_id)
        try:
            result = await collector.collect(request)
        except Exception as error:
            return self._failed(source_id, error)
        if result.source_id != source_id:
            return self._failed(source_id, ValueError("collector returned another source"))
        return result

    async def collect_batch(self, request: CollectRequest) -> PaperCollectionBatch:
        requested = tuple(source_id for source_id in PAPER_SOURCE_IDS if source_id in request.source_ids)
        results: dict[str, CollectorResult] = {}
        for source_id in requested:
            if source_id == "semantic" and self.semantic_fallback_only:
                authors = authors_from_snapshot(request.source_config_snapshot)
                covered = covered_authors(
                    (item for result in results.values() for item in result.items),
                    authors,
                )
                remaining = [author for author in authors if normalize_author_name(author) not in covered]
                if authors and not remaining:
                    results[source_id] = self._fallback_covered()
                    continue
                source_request = request_with_authors(request, remaining) if authors else request
            else:
                source_request = request
            results[source_id] = await self._collect_one(source_id, source_request)
        ordered = tuple(results[source_id] for source_id in requested)
        if self.abstract_resolver is not None:
            ordered = await self._enrich_missing_abstracts(ordered)
        return PaperCollectionBatch(
            results=ordered,
            deduplicated_items=deduplicate_paper_items(item for result in ordered for item in result.items),
        )

    async def _enrich_missing_abstracts(
        self,
        results: Sequence[CollectorResult],
    ) -> tuple[CollectorResult, ...]:
        cache: dict[tuple[str, str], Optional[AbstractResolution]] = {}
        updated_results: list[CollectorResult] = []
        for result in results:
            updated_items: list[IntelItem] = []
            enrichment_failed = False
            for item in result.items:
                if item.summary:
                    updated_items.append(item)
                    continue
                identity = paper_identity_key(item)
                if identity not in cache:
                    try:
                        cache[identity] = await self.abstract_resolver.resolve(item)
                    except Exception:
                        cache[identity] = None
                        enrichment_failed = True
                resolution = cache[identity]
                if resolution is None or not resolution.text.strip():
                    updated_items.append(item)
                    continue
                metadata = dict(item.metadata)
                metadata["abstract_source"] = resolution.source_id
                updated_items.append(replace(item, summary=resolution.text, metadata=metadata))
            if not enrichment_failed:
                updated_results.append(replace(result, items=tuple(updated_items)))
                continue
            warning = f"{result.source_id} abstract enrichment failed"
            status = CoverageStatus.PARTIAL if updated_items else result.coverage.status
            detail = f"{result.source_id} items available; abstract enrichment incomplete"
            updated_results.append(
                replace(
                    result,
                    items=tuple(updated_items),
                    warnings=tuple((*result.warnings, warning)),
                    coverage=SourceCoverage(
                        status,
                        len(updated_items),
                        detail=detail,
                        retry_after=result.coverage.retry_after,
                    ),
                )
            )
        return tuple(updated_results)

    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]:
        return (await self.collect_batch(request)).results

    async def aclose(self) -> None:
        if self.http_runtime is not None:
            await self.http_runtime.aclose()


__all__ = [
    "AbstractResolution",
    "AbstractResolver",
    "PaperCollectionBatch",
    "PaperCollectorCoordinator",
]
