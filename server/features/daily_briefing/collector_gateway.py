"""Collector gateway implementations and the legacy gather adapter."""
from __future__ import annotations

import asyncio
import email.utils
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

try:
    from intel import intel_config
except ImportError:  # Installable package without legacy source modules.
    class _EmptyIntelConfig:
        MONEY_CONFIG: Mapping[str, Any] = {}
        ARXIV_CONFIG: Mapping[str, Any] = {}
        PAPER_ENABLE_CROSSREF_DAILY_SCAN = False
        PAPER_ENABLE_SEMANTIC_SCHOLAR = False

    intel_config = _EmptyIntelConfig()

from core.intel_contracts import CollectorRegistry

from .collector_contracts import Collector, CollectorProgressCallback
from .models import (
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    PUBLIC_SOURCE_ID_SET,
    SourceCoverage,
    rfc3339,
    sanitize_external_text,
    stable_item_id,
)
from .time_utils import localize


Clock = Callable[[], datetime]
LegacyGather = Callable[..., Awaitable[Mapping[str, Any]]]
SourceConfigLoader = Callable[[], Mapping[str, Any]]


def _aware_now(clock: Clock) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("collector gateway clock must return an aware datetime")
    return value


def _warning_text(value: object, source_id: str) -> str:
    text = sanitize_external_text(value, limit=2_000)
    if not text:
        return ""
    text = re.sub(
        r"https?://[^\s]+",
        lambda match: _safe_warning_url(match.group(0)),
        text,
    )
    text = sanitize_external_text(text, limit=220)
    return f"{source_id}: {text}"[:240]


def _safe_warning_url(value: str) -> str:
    try:
        parsed = urlsplit(value.rstrip(".,);"))
        host = parsed.hostname or "upstream"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return "<upstream-url>"


def _legacy_timestamp(value: object, timezone_name: str) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(text_value)
        except (TypeError, ValueError, OverflowError):
            parsed = None
    if parsed is None:
        try:
            day = date.fromisoformat(text_value[:10])
        except ValueError:
            return ""
        parsed = localize(datetime.combine(day, time.min), timezone_name)
    elif parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = localize(parsed, timezone_name)
    return rfc3339(parsed)


def _source_configured(source_id: str, snapshot: Mapping[str, Any]) -> bool:
    authors = (
        list(snapshot.get("paper_priority_authors", []) or [])
        + list(snapshot.get("paper_secondary_authors", []) or [])
        + list(snapshot.get("paper_ai_authors", []) or [])
    )
    if source_id == "twitter":
        return bool(list(snapshot.get("twitter_users", []) or []) + list(snapshot.get("money_twitter_users", []) or []))
    if source_id == "github":
        return bool(list(snapshot.get("github_users", []) or []) + list(snapshot.get("github_repos", []) or []))
    if source_id == "bilibili":
        return bool(snapshot.get("bilibili_uids", []))
    if source_id == "youtube":
        return bool(snapshot.get("youtube_channel_ids", []))
    if source_id == "money":
        return bool(getattr(intel_config, "MONEY_CONFIG", {}).get("rss_feeds"))
    if source_id == "arxiv":
        return bool(getattr(intel_config, "ARXIV_CONFIG", {})) or bool(authors)
    if source_id == "crossref":
        enabled = os.getenv(
            "PAPER_ENABLE_CROSSREF_DAILY_SCAN",
            str(getattr(intel_config, "PAPER_ENABLE_CROSSREF_DAILY_SCAN", True)),
        ).strip().lower() in {"1", "true", "yes", "on"}
        return enabled and bool(authors)
    if source_id == "semantic":
        enabled = os.getenv(
            "PAPER_ENABLE_SEMANTIC_SCHOLAR",
            str(getattr(intel_config, "PAPER_ENABLE_SEMANTIC_SCHOLAR", True)),
        ).strip().lower() in {"1", "true", "yes", "on"}
        return enabled and bool(authors)
    return False


def _paper_source(value: object) -> str:
    field = str(getattr(value, "field", "") or getattr(value, "source", "") or "").casefold()
    if field == "crossref":
        return "crossref"
    if field in {"semantic", "semantic_scholar", "semanticscholar"}:
        return "semantic"
    return "arxiv"


def _legacy_values(payload: Mapping[str, Any], source_id: str) -> Sequence[object]:
    if source_id == "twitter":
        return payload.get("twitter", []) or []
    if source_id == "github":
        return list(payload.get("github_users", []) or []) + list(payload.get("github_repos", []) or [])
    if source_id == "bilibili":
        return payload.get("bilibili", []) or []
    if source_id == "youtube":
        return payload.get("youtube", []) or []
    if source_id == "money":
        return payload.get("money_tips", []) or []
    if source_id in {"arxiv", "crossref", "semantic"}:
        return [value for value in payload.get("papers", []) or [] if _paper_source(value) == source_id]
    return []


def _legacy_item(value: object, source_id: str, fetched_at: str, timezone_name: str) -> IntelItem | None:
    published_at = _legacy_timestamp(getattr(value, "published", ""), timezone_name)
    metadata: dict[str, Any] = {}
    title = summary = url = author = upstream_id = ""
    category = "general"

    if source_id == "twitter":
        author = str(getattr(value, "username", "") or "").lstrip("@")
        title = str(getattr(value, "content", "") or "")
        url = str(getattr(value, "url", "") or "")
        category = "social"
        metadata = {"username": author}
    elif source_id == "github":
        author = str(getattr(value, "source", "") or "")
        title = str(getattr(value, "title", "") or "")
        summary = str(getattr(value, "description", "") or "")
        url = str(getattr(value, "url", "") or "")
        event_type = str(getattr(value, "event_type", "") or "")
        category = "development"
        metadata = {"event_type": event_type}
        upstream_id = f"{event_type}\x1f{title}\x1f{published_at}"
    elif source_id == "bilibili":
        author = str(getattr(value, "username", "") or "")
        title = str(getattr(value, "content", "") or "")
        url = str(getattr(value, "url", "") or "")
        uid = str(getattr(value, "uid", "") or "")
        dynamic_type = str(getattr(value, "dynamic_type", "") or "")
        category = "video"
        metadata = {"uid": uid, "dynamic_type": dynamic_type}
    elif source_id == "youtube":
        author = str(getattr(value, "channel", "") or "")
        title = str(getattr(value, "title", "") or "")
        url = str(getattr(value, "url", "") or "")
        category = "video"
        metadata = {"thumbnail": str(getattr(value, "thumbnail", "") or "")[:1000]}
    elif source_id == "money":
        author = str(getattr(value, "source", "") or "")
        title = str(getattr(value, "title", "") or "")
        summary = str(getattr(value, "summary", "") or "")
        url = str(getattr(value, "url", "") or "")
        category = "money"
        metadata = {"score": int(getattr(value, "score", 0) or 0)}
    else:
        title = str(getattr(value, "title", "") or "")
        summary = str(getattr(value, "abstract", "") or "")
        url = str(getattr(value, "url", "") or "")
        authors = getattr(value, "authors", []) or []
        author_values = []
        for item in authors:
            if isinstance(item, str):
                author_values.append(item)
            elif isinstance(item, Mapping):
                author_values.append(" ".join(str(item.get(key, "")) for key in ("given", "family")).strip())
        author = ", ".join(item for item in author_values if item)[:300]
        doi = str(getattr(value, "doi", "") or "").strip().casefold()
        category = "papers"
        metadata = {
            "doi": doi,
            "journal": str(getattr(value, "journal", "") or "")[:300],
            "authors": author_values[:30],
            "field": str(getattr(value, "field", "") or "")[:120],
            "upstream_source": str(getattr(value, "source", "") or "")[:120],
            "matched_author": str(getattr(value, "matched_author", "") or "")[:300],
            "category": str(getattr(value, "category", "") or "")[:120],
        }
        upstream_id = doi

    if not " ".join(title.split()):
        return None
    return IntelItem(
        stable_id=stable_item_id(
            source_id,
            upstream_id=upstream_id,
            url=url,
            title=title,
            author=author,
            published_at=published_at,
        ),
        source_id=source_id,
        category=category,
        title=title,
        summary=summary,
        url=url,
        author=author,
        published_at=published_at,
        fetched_at=fetched_at,
        metadata=metadata,
    )


class ContractCollectorGateway:
    """Run independently supplied Collectors with per-source isolation."""

    def __init__(
        self,
        collectors: Mapping[str, Collector],
        *,
        clock: Clock = lambda: datetime.now(timezone.utc),
    ):
        self._collectors = dict(collectors)
        self._clock = clock

    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]:
        return await self.collect_with_progress(request, lambda result: None)

    async def collect_with_progress(
        self,
        request: CollectRequest,
        on_result: CollectorProgressCallback,
    ) -> Sequence[CollectorResult]:
        async def one(source_id: str) -> CollectorResult:
            collector = self._collectors.get(source_id)
            fetched_at = rfc3339(_aware_now(self._clock))
            if collector is None:
                return CollectorResult(
                    source_id=source_id,
                    items=(),
                    warnings=(f"{source_id}: no collector is registered",),
                    coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail="collector unavailable"),
                    fetched_at=fetched_at,
                    cache_status=CacheStatus.UNAVAILABLE,
                )
            try:
                result = await collector.collect(request)
                if result.source_id != source_id:
                    raise ValueError("collector returned a mismatched source_id")
                return result
            except Exception:
                return CollectorResult(
                    source_id=source_id,
                    items=(),
                    warnings=(f"{source_id}: collector failed",),
                    coverage=SourceCoverage(
                        CoverageStatus.FAILED,
                        detail="collector failed",
                        retry_after=rfc3339(_aware_now(self._clock) + timedelta(minutes=30)),
                    ),
                    fetched_at=fetched_at,
                    retry_after=rfc3339(_aware_now(self._clock) + timedelta(minutes=30)),
                    cache_status=CacheStatus.UNAVAILABLE,
                )

        tasks = [asyncio.create_task(one(source_id)) for source_id in request.source_ids]
        results: list[CollectorResult] = []
        try:
            for task in asyncio.as_completed(tasks):
                result = await task
                results.append(result)
                on_result(result)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        by_source = {result.source_id: result for result in results}
        return tuple(by_source[source_id] for source_id in request.source_ids)


class RegistryCollectorGateway:
    """Resolve the current Core registry snapshot for every collection."""

    def __init__(
        self,
        registry: CollectorRegistry,
        *,
        clock: Clock = lambda: datetime.now(timezone.utc),
    ):
        self._registry = registry
        self._clock = clock

    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]:
        return await self.collect_with_progress(request, lambda result: None)

    async def collect_with_progress(
        self,
        request: CollectRequest,
        on_result: CollectorProgressCallback,
    ) -> Sequence[CollectorResult]:
        gateway = ContractCollectorGateway(
            self._registry.snapshot(request.source_ids),
            clock=self._clock,
        )
        return await gateway.collect_with_progress(request, on_result)


class LegacyCollectorGateway:
    """Adapt every current source through ``intel.briefing.gather_all_intel``."""

    def __init__(
        self,
        gather: LegacyGather,
        source_config_loader: SourceConfigLoader,
        *,
        clock: Clock = lambda: datetime.now(timezone.utc),
    ):
        self._gather = gather
        self._source_config_loader = source_config_loader
        self._clock = clock

    def source_config_snapshot(self) -> Mapping[str, Any]:
        return self._source_config_loader()

    async def _collect_one(self, source_id: str, request: CollectRequest) -> CollectorResult:
        fetched_now = _aware_now(self._clock)
        fetched_at = rfc3339(fetched_now)
        if source_id not in PUBLIC_SOURCE_ID_SET:
            return CollectorResult(
                source_id=source_id,
                items=(),
                warnings=(f"{source_id}: unsupported legacy source",),
                coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail="unsupported legacy source"),
                fetched_at=fetched_at,
                cache_status=CacheStatus.UNAVAILABLE,
            )
        if not _source_configured(source_id, request.source_config_snapshot):
            return CollectorResult(
                source_id=source_id,
                items=(),
                warnings=(),
                coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail="source has no active configuration"),
                fetched_at=fetched_at,
                cache_status=CacheStatus.UNAVAILABLE,
            )
        try:
            payload = await self._gather(
                sources=[source_id],
                source_config_snapshot=request.source_config_snapshot,
            )
        except Exception:
            return CollectorResult(
                source_id=source_id,
                items=(),
                warnings=(f"{source_id}: legacy collector failed",),
                coverage=SourceCoverage(
                    CoverageStatus.FAILED,
                    detail="legacy collector failed",
                    retry_after=rfc3339(fetched_now + timedelta(minutes=30)),
                ),
                fetched_at=fetched_at,
                retry_after=rfc3339(fetched_now + timedelta(minutes=30)),
                cache_status=CacheStatus.UNAVAILABLE,
            )

        warnings = tuple(
            warning
            for warning in (_warning_text(item, source_id) for item in payload.get("_warnings", []) or [])
            if warning
        )
        items: list[IntelItem] = []
        for value in _legacy_values(payload, source_id):
            try:
                item = _legacy_item(value, source_id, fetched_at, request.timezone)
            except (TypeError, ValueError):
                item = None
            if item is not None:
                items.append(item)
        if warnings and items:
            status = CoverageStatus.PARTIAL
        elif warnings:
            status = CoverageStatus.FAILED
        elif items:
            status = CoverageStatus.COMPLETE
        else:
            status = CoverageStatus.EMPTY
        return CollectorResult(
            source_id=source_id,
            items=tuple(items),
            warnings=warnings,
            coverage=SourceCoverage(
                status,
                len(items),
                retry_after=rfc3339(fetched_now + timedelta(minutes=30)) if status is CoverageStatus.FAILED else None,
            ),
            fetched_at=fetched_at,
            retry_after=rfc3339(fetched_now + timedelta(minutes=30)) if status is CoverageStatus.FAILED else None,
            cache_status=CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED,
        )

    async def collect(self, request: CollectRequest) -> Sequence[CollectorResult]:
        # Legacy paper adapters share process-global arXiv failure tracking, so
        # serialize them while all unrelated platform sources remain isolated.
        paper_ids = [source for source in request.source_ids if source in {"arxiv", "crossref", "semantic"}]
        other_ids = [source for source in request.source_ids if source not in {"arxiv", "crossref", "semantic"}]
        other_results = await asyncio.gather(*(self._collect_one(source, request) for source in other_ids))
        paper_results = []
        for source in paper_ids:
            paper_results.append(await self._collect_one(source, request))
        by_source = {result.source_id: result for result in [*other_results, *paper_results]}
        return [by_source[source] for source in request.source_ids]


__all__ = [
    "ContractCollectorGateway",
    "LegacyCollectorGateway",
    "RegistryCollectorGateway",
]
