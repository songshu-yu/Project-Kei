"""Generic RSS/Atom Collector implemented against the frozen Collector 1.0 API."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from core.intel_contracts import (
    Collector,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    rfc3339,
    stable_item_id,
)

from .http_client import (
    FeedFetchError,
    FeedURLPolicy,
    Resolver,
    fetch_feed_xml,
    normalize_entry_url,
)
from .models import RSSFeedEntry
from .parser import parse_feed, parse_published


SOURCE_ID = "money"
_ASCII_WORD_RE = re.compile(r"^[a-z0-9][a-z0-9 +._/-]*$", re.IGNORECASE)
_RSS_FAILURE_CODES = frozenset({
    "access_denied",
    "dns_rejected",
    "http_error",
    "invalid_response",
    "network_error",
    "not_found",
    "parse_error",
    "rate_limited",
    "redirect_missing_location",
    "redirect_rejected",
    "response_too_large",
    "timeout",
    "too_many_redirects",
    "upstream_failed",
    "upstream_unavailable",
})


def _normalize_keyword(value: object) -> str:
    keyword = " ".join(str(value or "").strip().split()).casefold()
    if not keyword or len(keyword) > 120:
        raise ValueError("RSS keyword must contain between 1 and 120 characters")
    return keyword


def _keyword_pattern(keyword: str) -> re.Pattern:
    escaped = re.escape(keyword).replace(r"\ ", r"\s+")
    if _ASCII_WORD_RE.fullmatch(keyword):
        escaped = r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])"
    return re.compile(escaped, re.IGNORECASE)


class RSSIntelCollector(Collector):
    """Collect a fixed, application-owned set of RSS/Atom feeds as ``money``."""

    source_id = SOURCE_ID

    def __init__(
        self,
        feed_urls: Iterable[object],
        keywords: Iterable[object] = (),
        *,
        allowed_redirect_hosts: Iterable[object] = (),
        client: Optional[httpx.AsyncClient] = None,
        resolver: Optional[Resolver] = None,
        clock=None,
        max_entries_per_feed: int = 30,
        max_results: int = 15,
        max_response_bytes: int = 1024 * 1024,
        max_redirects: int = 3,
    ) -> None:
        self._policy = FeedURLPolicy(
            feed_urls,
            allowed_redirect_hosts=allowed_redirect_hosts,
            resolver=resolver,
        )
        keyword_values = (keywords,) if isinstance(keywords, str) else tuple(keywords)
        normalized_keywords = tuple(_normalize_keyword(value) for value in keyword_values)
        if len(normalized_keywords) > 100:
            raise ValueError("too many RSS keywords")
        self._keywords = tuple(dict.fromkeys(normalized_keywords))
        self._keyword_patterns = tuple(
            (keyword, _keyword_pattern(keyword)) for keyword in self._keywords
        )
        self._client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_entries_per_feed = max(1, min(100, int(max_entries_per_feed)))
        self._max_results = max(1, min(100, int(max_results)))
        self._max_response_bytes = max(1024, min(4 * 1024 * 1024, int(max_response_bytes)))
        self._max_redirects = max(0, min(5, int(max_redirects)))

    def _matches(self, entry: RSSFeedEntry) -> Tuple[str, ...]:
        if not self._keyword_patterns:
            return ()
        haystack = f"{entry.title} {entry.summary}".casefold()
        return tuple(
            keyword
            for keyword, pattern in self._keyword_patterns
            if pattern.search(haystack)
        )

    @staticmethod
    def _candidate_rank(item: IntelItem, score: int, published: Optional[datetime]):
        return (score, published or datetime.min.replace(tzinfo=timezone.utc), item.stable_id)

    async def collect(self, request: CollectRequest) -> CollectorResult:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("RSSIntelCollector clock must return an aware datetime")
        now = now.astimezone(timezone.utc)
        fetched_at = rfc3339(now)
        if SOURCE_ID not in request.source_ids or not self._policy.feed_urls:
            return CollectorResult(
                source_id=SOURCE_ID,
                items=(),
                warnings=(),
                coverage=SourceCoverage(
                    CoverageStatus.NOT_CONFIGURED,
                    detail="No application-owned RSS feed is configured",
                ),
                fetched_at=fetched_at,
                cache_status=CacheStatus.UNAVAILABLE,
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "Project-Kei-RSS-Collector/1.0"},
            follow_redirects=False,
            trust_env=False,
        )
        failures = 0
        failure_codes: dict[str, int] = {}
        retry_times = []
        candidates = {}
        cutoff = now - timedelta(hours=request.lookback)
        try:
            for feed_url in self._policy.feed_urls:
                try:
                    xml_bytes = await fetch_feed_xml(
                        client,
                        feed_url,
                        self._policy,
                        now=now,
                        max_bytes=self._max_response_bytes,
                        max_redirects=self._max_redirects,
                    )
                    entries = parse_feed(
                        xml_bytes,
                        feed_url,
                        max_entries=self._max_entries_per_feed,
                    )
                except (FeedFetchError, ValueError, TypeError) as exc:
                    failures += 1
                    if isinstance(exc, FeedFetchError):
                        code = (
                            exc.code
                            if exc.code in _RSS_FAILURE_CODES
                            else "upstream_failed"
                        )
                    elif isinstance(exc, ValueError):
                        code = "parse_error"
                    else:
                        code = "invalid_response"
                    failure_codes[code] = failure_codes.get(code, 0) + 1
                    retry_at = exc.retry_after if isinstance(exc, FeedFetchError) else None
                    retry_times.append(retry_at or (now + timedelta(minutes=30)))
                    continue

                feed_host = str(urlsplit(feed_url).hostname or "")
                for entry in entries:
                    matched = self._matches(entry)
                    if self._keyword_patterns and not matched:
                        continue
                    published = parse_published(entry.published_raw, request.timezone)
                    if published is not None and (
                        published < cutoff or published > now + timedelta(minutes=5)
                    ):
                        continue
                    published_at = rfc3339(published) if published is not None else ""
                    item_url = normalize_entry_url(entry.url)
                    upstream_id = entry.upstream_id or ""
                    item = IntelItem(
                        stable_id=stable_item_id(
                            SOURCE_ID,
                            upstream_id=(f"{feed_host}:{upstream_id}" if upstream_id else ""),
                            url=item_url,
                            title=entry.title,
                            author=entry.author or entry.feed_title,
                            published_at=published_at,
                        ),
                        source_id=SOURCE_ID,
                        category="money",
                        title=entry.title,
                        summary=entry.summary,
                        url=item_url,
                        author=entry.author or entry.feed_title,
                        published_at=published_at,
                        fetched_at=fetched_at,
                        metadata={
                            "feed_title": entry.feed_title,
                            "feed_host": feed_host,
                            "keyword_score": len(matched),
                            "matched_keywords": list(matched),
                            "published_status": (
                                "parsed" if published is not None else
                                ("invalid" if entry.published_raw else "missing")
                            ),
                        },
                    )
                    dedupe_keys = [f"stable:{item.stable_id}"]
                    if item.url:
                        dedupe_keys.insert(0, f"url:{item.url}")
                    existing = next((candidates[key] for key in dedupe_keys if key in candidates), None)
                    candidate = (item, len(matched), published)
                    if existing is None or self._candidate_rank(*candidate) > self._candidate_rank(*existing):
                        if existing is not None:
                            for key, value in list(candidates.items()):
                                if value is existing:
                                    candidates.pop(key, None)
                        for key in dedupe_keys:
                            candidates[key] = candidate
        finally:
            if owns_client:
                await client.aclose()

        unique = {value[0].stable_id: value for value in candidates.values()}
        ranked = sorted(
            unique.values(),
            key=lambda value: self._candidate_rank(*value),
            reverse=True,
        )[: self._max_results]
        items = tuple(value[0] for value in ranked)
        retry_after = rfc3339(max(retry_times)) if retry_times else None
        warnings = []
        if failures:
            warnings.append(f"money: {failures} configured feed(s) unavailable")
            warnings.extend(
                f"money: {count} configured feed(s) failed ({code})"
                for code, count in sorted(failure_codes.items())
            )
        if items and failures:
            status = CoverageStatus.PARTIAL
            detail = "Some configured RSS feeds were unavailable"
        elif items:
            status = CoverageStatus.COMPLETE
            detail = ""
        elif failures:
            status = CoverageStatus.FAILED
            detail = "Configured RSS feeds could not provide usable items"
        else:
            status = CoverageStatus.EMPTY
            detail = "Configured RSS feeds had no matching items in the requested window"
        return CollectorResult(
            source_id=SOURCE_ID,
            items=items,
            warnings=tuple(warnings),
            coverage=SourceCoverage(status, len(items), detail, retry_after),
            fetched_at=fetched_at,
            retry_after=retry_after,
            cache_status=(
                CacheStatus.UNAVAILABLE
                if status is CoverageStatus.FAILED
                else (CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED)
            ),
        )


__all__ = ["RSSIntelCollector", "SOURCE_ID"]
