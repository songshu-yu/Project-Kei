from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Optional, Sequence, Union

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
from .domain import (
    author_name_matches,
    authors_from_snapshot,
    arxiv_identifier,
    deduplicate_paper_items,
    normalize_doi,
    publication_in_window,
    publication_rfc3339,
)
from .http import (
    PaperHttpRuntime,
    UpstreamPolicy,
    default_paper_http_runtime,
    retry_after_seconds,
)


@dataclass
class Paper:
    title: str
    authors: list
    abstract: str
    url: str
    category: str
    published: str
    field: str = ""


ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_MIN_INTERVAL = float(os.getenv("ARXIV_MIN_INTERVAL", "3.5"))
ARXIV_CACHE_TTL_SECONDS = int(os.getenv("ARXIV_CACHE_TTL_SECONDS", str(18 * 60 * 60)))
ARXIV_MAX_RETRIES = int(os.getenv("ARXIV_MAX_RETRIES", "0"))
ARXIV_TRUST_ENV = os.getenv("ARXIV_TRUST_ENV", "true").strip().lower() in {"1", "true", "yes", "on"}

SERVER_ROOT = Path(__file__).resolve().parents[2]
ARXIV_CACHE_DIR = SERVER_ROOT / "data" / "cache" / "arxiv"

_arxiv_failures = []


class _ArxivRequestError(RuntimeError):
    def __init__(self, code: str, *, retry_after_seconds: Optional[float] = None):
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class ArxivQuery:
    label: str
    categories: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    max_results: int = 10

    @classmethod
    def from_mapping(cls, label: object, value: Mapping[str, object]) -> "ArxivQuery":
        raw_categories = value.get("categories", ())
        raw_keywords = value.get("keywords", ())
        categories = tuple(
            str(item).strip()
            for item in (raw_categories if isinstance(raw_categories, (list, tuple)) else ())
            if str(item).strip()
        )
        keywords = tuple(
            str(item).strip()
            for item in (raw_keywords if isinstance(raw_keywords, (list, tuple)) else ())
            if str(item).strip()
        )
        maximum = max(1, min(int(value.get("max_results", 10)), 100))
        return cls(str(label or "query")[:80], categories, keywords, maximum)


class ArxivCollector(Collector):
    """Collector 1.0 arXiv adapter with injected HTTP, clock, and cache root."""

    source_id = "arxiv"

    def __init__(
        self,
        *,
        queries: Sequence[Union[ArxivQuery, Mapping[str, object]]] = (),
        cache_dir: Optional[Union[str, Path]] = None,
        cache_ttl_seconds: int = ARXIV_CACHE_TTL_SECONDS,
        min_interval: Optional[float] = None,
        max_retries: int = ARXIV_MAX_RETRIES,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        trust_env: bool = ARXIV_TRUST_ENV,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic: Optional[Callable[[], float]] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        runtime: Optional[PaperHttpRuntime] = None,
    ) -> None:
        normalized: list[ArxivQuery] = []
        for index, query in enumerate(queries):
            if isinstance(query, ArxivQuery):
                normalized.append(query)
            elif isinstance(query, Mapping):
                label = query.get("label", f"query-{index + 1}")
                normalized.append(ArxivQuery.from_mapping(label, query))
            else:
                raise ValueError("arXiv queries must be ArxivQuery or mapping values")
        self.queries = tuple(normalized)
        self.cache_dir = Path(cache_dir) if cache_dir is not None else ARXIV_CACHE_DIR
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.max_retries = max(0, int(max_retries))
        self.clock = clock
        if runtime is not None:
            self.runtime = runtime
            self._owns_runtime = False
        elif transport is not None or monotonic is not None or sleep is not asyncio.sleep or min_interval is not None:
            self.runtime = PaperHttpRuntime(
                policies={
                    "arxiv": UpstreamPolicy(
                        min_interval=ARXIV_MIN_INTERVAL if min_interval is None else min_interval,
                        timeout=45.0,
                        trust_env=bool(trust_env),
                    )
                },
                transports={"arxiv": transport} if transport is not None else None,
                monotonic=monotonic,
                sleep=sleep,
                clock=clock,
            )
            self._owns_runtime = True
        else:
            self.runtime = default_paper_http_runtime()
            self._owns_runtime = False

    def _instance_cache_path(self, params: Mapping[str, object]) -> Path:
        raw = json.dumps(dict(params), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return self.cache_dir / f"{hashlib.sha256(raw.encode('utf-8')).hexdigest()}.xml"

    def _read_instance_cache(self, params: Mapping[str, object]) -> Optional[str]:
        path = self._instance_cache_path(params)
        try:
            if not path.is_file():
                return None
            age = self.clock().timestamp() - path.stat().st_mtime
            if age > self.cache_ttl_seconds:
                return None
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_instance_cache(self, params: Mapping[str, object], text: str) -> None:
        path = self._instance_cache_path(params)
        temp = path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(text, encoding="utf-8")
            os.replace(temp, path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    async def _get_xml(self, params: Mapping[str, object], *, refresh: bool) -> tuple[str, bool]:
        if not refresh:
            cached = self._read_instance_cache(params)
            if cached is not None:
                return cached, True
        try:
            response = await self.runtime.get(
                "arxiv",
                ARXIV_API,
                params=params,
                max_retries=self.max_retries,
                base_delay=45.0,
                retry_after_floor=True,
            )
        except httpx.HTTPError as error:
            raise _ArxivRequestError(type(error).__name__) from None
        if response.status_code == 429:
            delay = retry_after_seconds(response, 45.0, minimum=True, clock=self.clock)
            raise _ArxivRequestError("rate_limited", retry_after_seconds=delay)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise _ArxivRequestError(f"http_{error.response.status_code}") from None
        self._write_instance_cache(params, response.text)
        return response.text, False

    @staticmethod
    def _parse_items(
        xml_text: str,
        *,
        request: CollectRequest,
        fetched_at: str,
        field_label: str,
        matched_target: str = "",
    ) -> tuple[IntelItem, ...]:
        namespace = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as error:
            raise _ArxivRequestError(type(error).__name__) from None
        items: list[IntelItem] = []
        for entry in root.findall("atom:entry", namespace):
            published_raw = entry.findtext("atom:published", "", namespace)
            if not publication_in_window(published_raw, request, datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))):
                continue
            authors = [
                " ".join((author.findtext("atom:name", "", namespace) or "").split())
                for author in entry.findall("atom:author", namespace)
            ]
            authors = [author for author in authors if author]
            if matched_target and not any(author_name_matches(matched_target, author) for author in authors):
                continue
            entry_id = " ".join(entry.findtext("atom:id", "", namespace).split())
            arxiv_id = arxiv_identifier(entry_id) or entry_id.rstrip("/").rsplit("/", 1)[-1]
            url = entry_id.replace("http://", "https://", 1)
            for link in entry.findall("atom:link", namespace):
                if link.get("rel") == "alternate" and link.get("href"):
                    url = str(link.get("href")).replace("http://", "https://", 1)
                    break
            title = " ".join(entry.findtext("atom:title", "", namespace).split())
            if not title:
                continue
            abstract = " ".join(entry.findtext("atom:summary", "", namespace).split())
            category_element = entry.find("atom:primary_category", namespace)
            if category_element is None:
                category_element = entry.find("atom:category", namespace)
            category = category_element.get("term", "") if category_element is not None else ""
            doi = normalize_doi(entry.findtext("arxiv:doi", "", namespace))
            published_at, precision = publication_rfc3339(published_raw)
            metadata = {
                "authors": authors[:50],
                "arxiv_id": arxiv_id,
                "doi": doi,
                "paper_field": field_label,
                "paper_category": category,
                "publication_precision": precision,
                "matched_authors": [matched_target] if matched_target else [],
            }
            items.append(
                IntelItem(
                    stable_id=stable_item_id("arxiv", upstream_id=arxiv_id, url=url, title=title),
                    source_id="arxiv",
                    category="papers",
                    title=title,
                    summary=abstract,
                    url=url,
                    author=", ".join(authors[:8]),
                    published_at=published_at,
                    fetched_at=fetched_at,
                    metadata=metadata,
                )
            )
        return tuple(items)

    async def collect(self, request: CollectRequest) -> CollectorResult:
        fetched_at = rfc3339(self.clock())
        authors = authors_from_snapshot(request.source_config_snapshot)
        work: list[tuple[dict[str, object], str, str]] = []
        for query in self.queries:
            search_query = _build_query(query.categories, query.keywords)
            if search_query:
                work.append(({
                    "search_query": search_query,
                    "start": 0,
                    "max_results": query.max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }, query.label, ""))
        author_limit = request.source_config_snapshot.get("arxiv_author_limit", len(authors))
        try:
            author_limit = max(0, min(int(author_limit), len(authors)))
        except (TypeError, ValueError):
            author_limit = len(authors)
        author_max = request.source_config_snapshot.get("arxiv_author_max_results", 10)
        try:
            author_max = max(1, min(int(author_max), 100))
        except (TypeError, ValueError):
            author_max = 10
        for author in authors[:author_limit]:
            escaped = author.replace("\\", " ").replace('"', " ")
            work.append(({
                "search_query": f'au:"{escaped}"',
                "start": 0,
                "max_results": author_max,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }, "tracked_authors", author))
        if not work:
            detail = "arxiv source has no active topic or author configuration"
            return CollectorResult(
                source_id=self.source_id,
                items=(),
                warnings=(),
                coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail=detail),
                fetched_at=fetched_at,
                cache_status=CacheStatus.UNAVAILABLE,
            )

        items: list[IntelItem] = []
        warnings: list[str] = []
        successes = 0
        cache_hits = 0
        retry_seconds: list[float] = []
        for params, label, matched_target in work:
            try:
                xml_text, cache_hit = await self._get_xml(params, refresh=request.refresh)
                parsed = self._parse_items(
                    xml_text,
                    request=request,
                    fetched_at=fetched_at,
                    field_label=label,
                    matched_target=matched_target,
                )
                items.extend(parsed)
                successes += 1
                cache_hits += int(cache_hit)
            except _ArxivRequestError as error:
                warnings.append(f"arxiv query failed ({error.code})")
                if error.retry_after_seconds is not None:
                    retry_seconds.append(error.retry_after_seconds)
            except Exception as error:
                warnings.append(f"arxiv query failed ({type(error).__name__})")
        deduped = deduplicate_paper_items(items)
        retry_after = None
        if retry_seconds:
            retry_after = rfc3339(self.clock() + timedelta(seconds=max(retry_seconds)))
        if successes == 0 or (warnings and not deduped):
            status = CoverageStatus.FAILED
        elif warnings:
            status = CoverageStatus.PARTIAL
        elif deduped:
            status = CoverageStatus.COMPLETE
        else:
            status = CoverageStatus.EMPTY
        cache_status = CacheStatus.REFRESHED if request.refresh else (CacheStatus.HIT if cache_hits == len(work) else CacheStatus.FETCHED)
        detail = f"{successes}/{len(work)} arxiv queries completed"
        return CollectorResult(
            source_id=self.source_id,
            items=deduped,
            warnings=tuple(dict.fromkeys(warnings)),
            coverage=SourceCoverage(status, len(deduped), detail=detail, retry_after=retry_after),
            fetched_at=fetched_at,
            retry_after=retry_after,
            cache_status=cache_status if successes else CacheStatus.UNAVAILABLE,
        )

    async def aclose(self) -> None:
        if self._owns_runtime:
            await self.runtime.aclose()


def clear_arxiv_failures():
    _arxiv_failures.clear()


def get_arxiv_failures():
    return list(_arxiv_failures)


def _build_query(categories, keywords):
    parts = []
    if categories:
        parts.append("(" + " OR ".join(f"cat:{c}" for c in categories) + ")")
    if keywords:
        parts.append("(" + " OR ".join(f'all:"{k}"' for k in keywords) + ")")
    return " AND ".join(parts) if len(parts) == 2 else (parts[0] if parts else "")


async def fetch_arxiv_papers(
    categories=None,
    keywords=None,
    authors=None,
    max_results=10,
    field_label="",
    since_hours=None,
    *,
    runtime: Optional[PaperHttpRuntime] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
):
    """Deprecated legacy shape backed by the Collector 1.0 implementation."""
    queries = ()
    if categories or keywords:
        queries = (
            ArxivQuery(
                field_label or "query",
                tuple(categories or ()),
                tuple(keywords or ()),
                max_results,
            ),
        )
    collector = ArxivCollector(
        queries=queries,
        cache_dir=cache_dir,
        max_retries=ARXIV_MAX_RETRIES,
        clock=clock,
        runtime=runtime,
    )
    lookback = max(1, min(int(since_hours or 24 * 30), 24 * 30))
    collect_request = CollectRequest(
        local_date=clock().date(),
        timezone="UTC",
        source_ids=("arxiv",),
        lookback=lookback,
        source_config_snapshot={
            "paper_priority_authors": list(authors or ()),
            "paper_secondary_authors": [],
            "paper_ai_authors": [],
            "arxiv_author_limit": len(authors or ()),
            "arxiv_author_max_results": max_results,
        },
    )
    result = await collector.collect(collect_request)
    _arxiv_failures.extend(result.warnings)
    return [
        Paper(
            title=item.title,
            authors=list(item.metadata.get("authors", ()))[:3],
            abstract=item.summary[:300],
            url=item.url,
            category=str(item.metadata.get("paper_category", "")),
            published=item.published_at[:10],
            field=str(item.metadata.get("paper_field", field_label)),
        )
        for item in result.items
    ]


__all__ = [
    "ArxivCollector",
    "ArxivQuery",
    "Paper",
    "clear_arxiv_failures",
    "fetch_arxiv_papers",
    "get_arxiv_failures",
]
