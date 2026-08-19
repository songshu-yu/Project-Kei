from __future__ import annotations
"""papers.py — 期刊论文采集器（v3 修复名字匹配）"""
import re
import os
import html
import asyncio
import xml.etree.ElementTree as ET
import httpx
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping, Optional, Sequence

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
    deduplicate_paper_items,
    normalize_doi,
    normalize_paper_title,
    publication_in_window,
    publication_rfc3339,
)
from .service import AbstractResolution
from .http import (
    PaperHttpRuntime,
    UpstreamPolicy,
    default_paper_http_runtime,
    retry_after_seconds,
)


OPTICS_JOURNALS = {
    "Nature Photonics":              {"issn": "1749-4885", "if": 35.0},
    "Nature Communications":         {"issn": "2041-1723", "if": 17.0},
    "Light: Science & Applications": {"issn": "2047-7538", "if": 21.0},
    "Optica":                        {"issn": "2334-2536", "if": 10.4},
    "Laser & Photonics Reviews":     {"issn": "1863-8880", "if": 11.0},
    "Photonics Research":            {"issn": "2327-9125", "if": 7.6},
    "APL Photonics":                 {"issn": "2378-0967", "if": 5.6},
    "Optics Express":                {"issn": "1094-4087", "if": 3.8},
    "Optics Letters":                {"issn": "0146-9592", "if": 3.6},
    "PhotoniX":                      {"issn": "2662-1991", "if": 14.0},
    "Advanced Photonics":            {"issn": "2577-5421", "if": 17.0},
}

JOURNAL_ALIASES = {
    "light, science & applications": "Light: Science & Applications",
    "light science & applications": "Light: Science & Applications",
}


@dataclass
class PaperItem:
    title: str
    authors: list
    abstract: str
    url: str
    doi: str = ""
    journal: str = ""
    published: str = ""
    source: str = ""
    is_corresponding: bool = False
    matched_author: str = ""


USER_AGENT = "ProjectKei/1.0 (paper collector)"
SS_BASE = "https://api.semanticscholar.org/graph/v1"
CROSSREF_BASE = "https://api.crossref.org"
SS_MIN_INTERVAL = float(os.getenv("SEMANTIC_SCHOLAR_MIN_INTERVAL", "2.0"))

def _clean_journal_key(journal):
    journal = html.unescape(journal or "").strip()
    journal = re.sub(r"\s+", " ", journal)
    return journal.lower().replace(":", "").replace(",", "")


def _normalize_journal_name(journal):
    journal = html.unescape(journal or "").strip()
    journal = re.sub(r"\s+", " ", journal)
    if not journal:
        return ""

    alias = JOURNAL_ALIASES.get(journal.lower())
    if alias:
        return alias

    journal_key = _clean_journal_key(journal)
    for canonical in OPTICS_JOURNALS:
        if journal_key == _clean_journal_key(canonical):
            return canonical
    return journal


def _journal_allowed(journal, allowed_journals):
    if not journal:
        return False
    allowed_keys = {_clean_journal_key(_normalize_journal_name(j)) for j in allowed_journals}
    return _clean_journal_key(_normalize_journal_name(journal)) in allowed_keys


def _parse_date_like(value):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(value[: len(fmt)], fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_recent_publication(value, since_hours=None):
    if since_hours is None:
        return True
    parsed = _parse_date_like(value)
    if parsed is None:
        return False
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=since_hours)
    if len(str(value or "").strip()) <= 10:
        return cutoff.date() <= parsed.date() <= now.date()
    return parsed >= cutoff


# ============================================================
#  严格的姓名匹配 — 修复关键bug
# ============================================================

def _tokenize_name(name):
    """把姓名拆成词列表，去除标点、点、逗号"""
    # 把 "Zuo, Chao" / "C. Zuo" / "Chao Zuo" 都规范化
    clean = name.lower().replace(",", " ").replace(".", " ")
    return [t for t in clean.split() if t]


def _name_matches(target_name, author_name):
    """严格匹配：必须姓完全相同（作为完整单词），名首字母至少一致

    "Chao Zuo" 匹配:
      ✅ "Chao Zuo"
      ✅ "C. Zuo"
      ✅ "Zuo, Chao"
      ❌ "Zhou Chao"  (姓不同)
      ❌ "Z. Chao"    (姓和名搞反了，且姓不是 zuo)
    """
    return author_name_matches(target_name, author_name)


# ============================================================
#  带重试的请求
# ============================================================

def _retry_after_delay(resp, fallback_delay):
    return retry_after_seconds(resp, fallback_delay)


def _upstream_for_url(url: str) -> str:
    host = httpx.URL(url).host.casefold()
    if host == "api.semanticscholar.org":
        return "semantic"
    if host == "api.crossref.org":
        return "crossref"
    if host == "export.arxiv.org":
        return "arxiv"
    if host == "api.openalex.org":
        return "openalex"
    return "publisher"


class _RuntimeHttpClient:
    """Small compatibility client that always delegates to PaperHttpRuntime."""

    def __init__(self, runtime: PaperHttpRuntime, *, headers: Optional[Mapping[str, str]] = None):
        self.runtime = runtime
        self.headers = dict(headers or {})

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False

    async def get(self, url, *, params=None, max_retries=0, base_delay=1.0):
        return await self.runtime.get(
            _upstream_for_url(str(url)),
            str(url),
            params=params,
            headers=self.headers,
            max_retries=max_retries,
            base_delay=base_delay,
        )


async def _get_with_retry(
    client,
    url,
    params=None,
    max_retries=5,
    base_delay=2.0,
    rate_limit_interval=None,
    label="HTTP",
):
    del rate_limit_interval, label
    response = await client.get(
        url,
        params=params,
        max_retries=max(0, int(max_retries) - 1),
        base_delay=base_delay,
    )
    if response.status_code == 429:
        return None
    response.raise_for_status()
    return response


class _PaperRequestError(RuntimeError):
    def __init__(self, code: str, *, retry_after_seconds: Optional[float] = None):
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


class _PaperHttpCollector:
    source_id = ""

    def __init__(
        self,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        trust_env: bool = False,
        min_interval: Optional[float] = None,
        max_retries: int = 1,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic: Optional[Callable[[], float]] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        runtime: Optional[PaperHttpRuntime] = None,
    ) -> None:
        self.max_retries = max(0, int(max_retries))
        self.clock = clock
        if runtime is not None:
            self.runtime = runtime
            self._owns_runtime = False
        elif transport is not None or monotonic is not None or sleep is not asyncio.sleep or min_interval is not None:
            self.runtime = PaperHttpRuntime(
                policies={
                    self.source_id: UpstreamPolicy(
                        min_interval=(
                            SS_MIN_INTERVAL
                            if min_interval is None and self.source_id == "semantic"
                            else (0.0 if min_interval is None else min_interval)
                        ),
                        timeout=30.0,
                        trust_env=bool(trust_env),
                    )
                },
                transports={self.source_id: transport} if transport is not None else None,
                monotonic=monotonic,
                sleep=sleep,
                clock=clock,
            )
            self._owns_runtime = True
        else:
            self.runtime = default_paper_http_runtime()
            self._owns_runtime = False

    async def _get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, object]:
        try:
            response = await self.runtime.get(
                self.source_id,
                url,
                params=params,
                headers=headers,
                max_retries=self.max_retries,
                base_delay=1.0,
            )
        except httpx.HTTPError as error:
            raise _PaperRequestError(type(error).__name__) from None
        if response.status_code == 429:
            raise _PaperRequestError(
                "rate_limited",
                retry_after_seconds=retry_after_seconds(response, 1.0, clock=self.clock),
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise _PaperRequestError(f"http_{error.response.status_code}") from None
        try:
            payload = response.json()
        except ValueError as error:
            raise _PaperRequestError(type(error).__name__) from None
        if not isinstance(payload, Mapping):
            raise _PaperRequestError("invalid_payload")
        return payload

    async def aclose(self) -> None:
        if self._owns_runtime:
            await self.runtime.aclose()

    def _not_configured(self, detail: str) -> CollectorResult:
        fetched_at = rfc3339(self.clock())
        return CollectorResult(
            source_id=self.source_id,
            items=(),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail=detail),
            fetched_at=fetched_at,
            cache_status=CacheStatus.UNAVAILABLE,
        )

    def _result(
        self,
        *,
        items: Sequence[IntelItem],
        warnings: Sequence[str],
        successes: int,
        attempts: int,
        retry_seconds: Sequence[float],
        refreshed: bool,
    ) -> CollectorResult:
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
        detail = f"{successes}/{attempts} {self.source_id} author queries completed"
        return CollectorResult(
            source_id=self.source_id,
            items=deduped,
            warnings=tuple(dict.fromkeys(warnings)),
            coverage=SourceCoverage(status, len(deduped), detail=detail, retry_after=retry_after),
            fetched_at=rfc3339(self.clock()),
            retry_after=retry_after,
            cache_status=(CacheStatus.REFRESHED if refreshed else CacheStatus.FETCHED) if successes else CacheStatus.UNAVAILABLE,
        )


class CrossrefCollector(_PaperHttpCollector, Collector):
    """Collector 1.0 Crossref author adapter; one bounded request per author."""

    source_id = "crossref"

    def __init__(
        self,
        *,
        allowed_journals: Optional[Sequence[str]] = None,
        max_results_per_author: int = 20,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.allowed_journals = tuple(_normalize_journal_name(value) for value in (allowed_journals or ()) if str(value).strip())
        self.max_results_per_author = max(1, min(int(max_results_per_author), 100))

    @staticmethod
    def _published(item: Mapping[str, object]) -> str:
        for key in ("published", "published-print", "published-online", "issued", "created"):
            value = item.get(key)
            if not isinstance(value, Mapping):
                continue
            parts_values = value.get("date-parts", ())
            if isinstance(parts_values, list) and parts_values and isinstance(parts_values[0], list):
                parts = parts_values[0]
                if parts:
                    return "-".join(str(part).zfill(2) for part in parts[:3])
            date_time = value.get("date-time")
            if date_time:
                return str(date_time)
        return ""

    def _parse_item(
        self,
        item: Mapping[str, object],
        *,
        target: str,
        request: CollectRequest,
        fetched_at: str,
    ) -> Optional[IntelItem]:
        title_values = item.get("title", ())
        title = str(title_values[0] if isinstance(title_values, list) and title_values else "").strip()
        if not title:
            return None
        author_values = item.get("author", ())
        authors: list[str] = []
        if isinstance(author_values, list):
            for author in author_values:
                if isinstance(author, Mapping):
                    name = " ".join(f"{author.get('given', '')} {author.get('family', '')}".split())
                    if name:
                        authors.append(name)
        matched_positions = [index for index, author in enumerate(authors) if author_name_matches(target, author)]
        if not matched_positions:
            return None
        published_raw = self._published(item)
        if not publication_in_window(published_raw, request, self.clock()):
            return None
        container = item.get("container-title", ())
        journal = _normalize_journal_name(container[0] if isinstance(container, list) and container else "")
        if self.allowed_journals and not _journal_allowed(journal, self.allowed_journals):
            return None
        doi = normalize_doi(item.get("DOI", ""))
        url = str(item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""))
        published_at, precision = publication_rfc3339(published_raw)
        upstream_id = doi or str(item.get("URL", ""))
        return IntelItem(
            stable_id=stable_item_id("crossref", upstream_id=upstream_id, url=url, title=title),
            source_id="crossref",
            category="papers",
            title=title,
            summary=_clean_abstract(item.get("abstract", ""), max_len=4000),
            url=url,
            author=", ".join(authors[:8]),
            published_at=published_at,
            fetched_at=fetched_at,
            metadata={
                "authors": authors[:50],
                "doi": doi,
                "journal": journal,
                "publication_precision": precision,
                "matched_authors": [target],
                "is_corresponding": bool(matched_positions and matched_positions[0] == len(authors) - 1),
            },
        )

    async def collect(self, request: CollectRequest) -> CollectorResult:
        authors = authors_from_snapshot(request.source_config_snapshot)
        if not authors:
            return self._not_configured("crossref source has no tracked authors")
        fetched_at = rfc3339(self.clock())
        start_date = (request.local_date - timedelta(days=max(1, request.lookback // 24 + 1))).isoformat()
        end_date = (request.local_date + timedelta(days=1)).isoformat()
        items: list[IntelItem] = []
        warnings: list[str] = []
        retry_seconds: list[float] = []
        successes = 0
        headers = {"User-Agent": USER_AGENT}
        for author in authors:
            try:
                payload = await self._get_json(
                    f"{CROSSREF_BASE}/works",
                    headers=headers,
                    params={
                        "query.author": author,
                        "filter": f"from-pub-date:{start_date},until-pub-date:{end_date}",
                        "sort": "published",
                        "order": "desc",
                        "rows": self.max_results_per_author,
                        "select": "DOI,title,author,abstract,published,published-print,published-online,issued,container-title,URL",
                    },
                )
                message = payload.get("message", {})
                raw_items = message.get("items", ()) if isinstance(message, Mapping) else ()
                if isinstance(raw_items, list):
                    for raw in raw_items:
                        if isinstance(raw, Mapping):
                            parsed = self._parse_item(raw, target=author, request=request, fetched_at=fetched_at)
                            if parsed is not None:
                                items.append(parsed)
                successes += 1
            except _PaperRequestError as error:
                warnings.append(f"crossref author query failed ({error.code})")
                if error.retry_after_seconds is not None:
                    retry_seconds.append(error.retry_after_seconds)
            except Exception as error:
                warnings.append(f"crossref author query failed ({type(error).__name__})")
        return self._result(
            items=items,
            warnings=warnings,
            successes=successes,
            attempts=len(authors),
            retry_seconds=retry_seconds,
            refreshed=request.refresh,
        )


class SemanticScholarCollector(_PaperHttpCollector, Collector):
    """Collector 1.0 Semantic Scholar adapter with environment-only key injection."""

    source_id = "semantic"

    def __init__(
        self,
        *,
        max_results_per_author: int = 20,
        api_key_provider: Callable[[], str] = lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.max_results_per_author = max(1, min(int(max_results_per_author), 100))
        self.api_key_provider = api_key_provider

    def _parse_item(
        self,
        item: Mapping[str, object],
        *,
        target: str,
        request: CollectRequest,
        fetched_at: str,
    ) -> Optional[IntelItem]:
        title = " ".join(str(item.get("title", "")).split())
        if not title:
            return None
        raw_authors = item.get("authors", ())
        authors = [str(author.get("name", "")).strip() for author in raw_authors if isinstance(author, Mapping)] if isinstance(raw_authors, list) else []
        authors = [author for author in authors if author]
        matched_positions = [index for index, author in enumerate(authors) if author_name_matches(target, author)]
        if not matched_positions:
            return None
        published_raw = str(item.get("publicationDate", "") or item.get("year", ""))
        if not publication_in_window(published_raw, request, self.clock()):
            return None
        external_ids = item.get("externalIds", {})
        external_ids = external_ids if isinstance(external_ids, Mapping) else {}
        doi = normalize_doi(external_ids.get("DOI", ""))
        arxiv_id = str(external_ids.get("ArXiv", "") or "")
        paper_id = str(item.get("paperId", "") or doi or arxiv_id)
        url = str(item.get("url", "") or (f"https://doi.org/{doi}" if doi else ""))
        journal_value = item.get("journal", {})
        journal = _normalize_journal_name(journal_value.get("name", "") if isinstance(journal_value, Mapping) else item.get("venue", ""))
        published_at, precision = publication_rfc3339(published_raw)
        return IntelItem(
            stable_id=stable_item_id("semantic", upstream_id=paper_id, url=url, title=title),
            source_id="semantic",
            category="papers",
            title=title,
            summary=_clean_abstract(item.get("abstract", ""), max_len=4000),
            url=url,
            author=", ".join(authors[:8]),
            published_at=published_at,
            fetched_at=fetched_at,
            metadata={
                "authors": authors[:50],
                "paper_id": paper_id,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "journal": journal,
                "publication_precision": precision,
                "matched_authors": [target],
                "is_corresponding": bool(matched_positions and matched_positions[0] == len(authors) - 1),
            },
        )

    async def collect(self, request: CollectRequest) -> CollectorResult:
        authors = authors_from_snapshot(request.source_config_snapshot)
        if not authors:
            return self._not_configured("semantic source has no tracked authors")
        fetched_at = rfc3339(self.clock())
        headers = self._headers()
        items: list[IntelItem] = []
        warnings: list[str] = []
        retry_seconds: list[float] = []
        successes = 0
        for author in authors:
            try:
                payload = await self._get_json(
                    f"{SS_BASE}/paper/search",
                    headers=headers,
                    params={
                        "query": author,
                        "fields": "paperId,title,authors,year,abstract,venue,publicationDate,externalIds,url,journal",
                        "limit": self.max_results_per_author,
                    },
                )
                raw_items = payload.get("data", ())
                if isinstance(raw_items, list):
                    for raw in raw_items:
                        if isinstance(raw, Mapping):
                            parsed = self._parse_item(raw, target=author, request=request, fetched_at=fetched_at)
                            if parsed is not None:
                                items.append(parsed)
                successes += 1
            except _PaperRequestError as error:
                warnings.append(f"semantic author query failed ({error.code})")
                if error.retry_after_seconds is not None:
                    retry_seconds.append(error.retry_after_seconds)
            except Exception as error:
                warnings.append(f"semantic author query failed ({type(error).__name__})")
        return self._result(
            items=items,
            warnings=warnings,
            successes=successes,
            attempts=len(authors),
            retry_seconds=retry_seconds,
            refreshed=request.refresh,
        )

    def _headers(self) -> dict:
        headers = {"User-Agent": USER_AGENT}
        api_key = str(self.api_key_provider() or "").strip()
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    async def resolve(self, item: IntelItem) -> Optional[AbstractResolution]:
        """Resolve one missing abstract by DOI, then exact normalized title."""
        doi = normalize_doi(item.metadata.get("doi", "")) or normalize_doi(item.url)
        if doi:
            try:
                payload = await self._get_json(
                    f"{SS_BASE}/paper/DOI:{doi}",
                    params={"fields": "abstract"},
                    headers=self._headers(),
                )
                abstract = _clean_abstract(payload.get("abstract", ""), max_len=4000)
                if abstract:
                    return AbstractResolution(abstract, self.source_id)
            except _PaperRequestError as error:
                if error.code not in {"http_400", "http_404"}:
                    raise
        title_key = normalize_paper_title(item.title)
        if not title_key:
            return None
        payload = await self._get_json(
            f"{SS_BASE}/paper/search",
            params={"query": item.title, "fields": "title,abstract", "limit": 3},
            headers=self._headers(),
        )
        raw_items = payload.get("data", ())
        if not isinstance(raw_items, list):
            return None
        for raw in raw_items:
            if not isinstance(raw, Mapping) or normalize_paper_title(raw.get("title", "")) != title_key:
                continue
            abstract = _clean_abstract(raw.get("abstract", ""), max_len=4000)
            if abstract:
                return AbstractResolution(abstract, self.source_id)
        return None


# ============================================================
#  Semantic Scholar — 用 paper search 而非 author search
# ============================================================

# ============================================================
#  Abstract enrichment helpers
# ============================================================

def _clean_abstract(value, max_len=900):
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for prefix in ("abstract", "summary"):
        if text.lower().startswith(prefix + ":"):
            text = text[len(prefix) + 1 :].strip()
    if max_len and len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text


def _doi_from_url_or_text(url="", doi=""):
    doi = str(doi or "").strip()
    if doi:
        return doi
    text = html.unescape(str(url or ""))
    match = re.search(r"10\.\d{4,9}/[^\s?#]+", text, flags=re.I)
    return match.group(0).rstrip("./") if match else ""


def _reconstruct_openalex_abstract(index):
    if not isinstance(index, dict) or not index:
        return ""
    words = []
    for word, positions in index.items():
        for pos in positions or []:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def _extract_meta_abstract(page_text):
    candidates = []
    patterns = [
        r'<meta[^>]+name=["\']citation_abstract["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']dc\.description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, page_text or "", flags=re.I | re.S))
    for candidate in candidates:
        abstract = _clean_abstract(candidate, max_len=900)
        if len(abstract) >= 80:
            return abstract
    return ""


async def fetch_abstract_for_doi_or_url(
    doi="",
    url="",
    title="",
    *,
    runtime: Optional[PaperHttpRuntime] = None,
):
    doi = _doi_from_url_or_text(url=url, doi=doi)
    headers = {"User-Agent": USER_AGENT}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    async with _RuntimeHttpClient(runtime or default_paper_http_runtime(), headers=headers) as client:
        if doi:
            try:
                resp = await client.get(f"{SS_BASE}/paper/DOI:{doi}", params={"fields": "abstract"})
                if resp.status_code == 200:
                    abstract = _clean_abstract(resp.json().get("abstract", ""))
                    if abstract:
                        print(f"[Enrich] Semantic Scholar abstract for {doi}: {len(abstract)} chars")
                        return abstract
            except Exception as exc:
                print(f"[Enrich] Semantic Scholar abstract failed ({type(exc).__name__})")

            try:
                resp = await client.get(f"https://api.openalex.org/works/https://doi.org/{doi}")
                if resp.status_code == 200:
                    abstract = _clean_abstract(_reconstruct_openalex_abstract(resp.json().get("abstract_inverted_index")))
                    if abstract:
                        print(f"[Enrich] OpenAlex abstract for {doi}: {len(abstract)} chars")
                        return abstract
            except Exception as exc:
                print(f"[Enrich] OpenAlex abstract failed ({type(exc).__name__})")

        if title:
            try:
                resp = await client.get(f"{SS_BASE}/paper/search", params={"query": title, "fields": "title,abstract,externalIds", "limit": 3})
                if resp.status_code == 200:
                    for item in resp.json().get("data", []) or []:
                        item_title = " ".join(str(item.get("title", "")).lower().split())
                        query_title = " ".join(str(title).lower().split())
                        if item_title == query_title or (query_title and query_title in item_title):
                            abstract = _clean_abstract(item.get("abstract", ""))
                            if abstract:
                                print(f"[Enrich] Semantic Scholar title abstract for {title[:60]}: {len(abstract)} chars")
                                return abstract
            except Exception as exc:
                print(f"[Enrich] Semantic Scholar title search failed ({type(exc).__name__})")

            try:
                resp = await client.get("https://api.openalex.org/works", params={"search": title, "per-page": 3})
                if resp.status_code == 200:
                    for item in resp.json().get("results", []) or []:
                        item_title = " ".join(str(item.get("title", "")).lower().split())
                        query_title = " ".join(str(title).lower().split())
                        if item_title == query_title or (query_title and query_title in item_title):
                            abstract = _clean_abstract(_reconstruct_openalex_abstract(item.get("abstract_inverted_index")))
                            if abstract:
                                print(f"[Enrich] OpenAlex title abstract for {title[:60]}: {len(abstract)} chars")
                                return abstract
            except Exception as exc:
                print(f"[Enrich] OpenAlex title search failed ({type(exc).__name__})")

            try:
                arxiv_query = " ".join(str(title).replace('"', " ").split())
                resp = await client.get(
                    "https://export.arxiv.org/api/query",
                    params={
                        "search_query": f'all:"{arxiv_query}"',
                        "start": 0,
                        "max_results": 5,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )
                if resp.status_code == 200:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    root = ET.fromstring(resp.text)
                    query_title = " ".join(str(title).lower().split())
                    for entry in root.findall("atom:entry", ns):
                        entry_title = " ".join(entry.findtext("atom:title", "", ns).replace("\n", " ").lower().split())
                        if entry_title == query_title or (query_title and query_title in entry_title):
                            abstract = _clean_abstract(entry.findtext("atom:summary", "", ns))
                            if abstract:
                                print(f"[Enrich] arXiv title abstract for {title[:60]}: {len(abstract)} chars")
                                return abstract
            except Exception as exc:
                print(f"[Enrich] arXiv title search failed ({type(exc).__name__})")

        page_url = url or (f"https://doi.org/{doi}" if doi else "")
        if page_url:
            try:
                resp = await client.get(page_url)
                if resp.status_code == 200:
                    abstract = _extract_meta_abstract(resp.text)
                    if abstract:
                        print(f"[Enrich] publisher meta abstract for {doi or title}: {len(abstract)} chars")
                        return abstract
            except Exception as exc:
                print(f"[Enrich] publisher abstract failed ({type(exc).__name__})")
    return ""


async def enrich_missing_abstracts(papers, *, runtime: Optional[PaperHttpRuntime] = None):
    for paper in papers or []:
        if getattr(paper, "abstract", ""):
            continue
        abstract = await fetch_abstract_for_doi_or_url(
            doi=getattr(paper, "doi", ""),
            url=getattr(paper, "url", ""),
            title=getattr(paper, "title", ""),
            runtime=runtime,
        )
        if abstract:
            paper.abstract = abstract
    return papers

async def search_by_author_semantic_scholar(
    author_name,
    max_results=20,
    year_from=None,
    allowed_journals=None,
    since_hours=None,
    *,
    runtime: Optional[PaperHttpRuntime] = None,
):
    """通过论文搜索接口搜索作者的论文（比作者搜索更准）"""
    papers = []
    headers = {"User-Agent": USER_AGENT}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    async with _RuntimeHttpClient(runtime or default_paper_http_runtime(), headers=headers) as client:
        try:
            # 直接搜索论文，把作者名作为查询词
            fields = "title,authors,year,abstract,venue,publicationDate,externalIds,url,journal"

            params = {
                "query": author_name,
                "fields": fields,
                "limit": max_results,
            }
            # Do not send Semantic Scholar's open-ended year filter (for example
            # "2026-"). It can trigger unstable 500 responses; we filter by
            # publicationDate locally with since_hours instead.

            resp = await _get_with_retry(
                client,
                f"{SS_BASE}/paper/search",
                params=params,
                rate_limit_interval=SS_MIN_INTERVAL,
                label="Semantic Scholar",
            )

            if not resp:
                print("[Semantic Scholar] ❌ author query failed")
                return []

            data = resp.json().get("data", [])

            for p in data:
                authors_list = [a.get("name", "") for a in p.get("authors", [])]

                # 必须真的包含目标作者
                matched_idx = None
                for idx, a in enumerate(authors_list):
                    if _name_matches(author_name, a):
                        matched_idx = idx
                        break

                if matched_idx is None:
                    continue  # 不包含目标作者的论文跳过

                is_corresponding = (matched_idx == len(authors_list) - 1)

                ext_ids = p.get("externalIds", {})
                doi = ext_ids.get("DOI", "")
                url = p.get("url", "") or (f"https://doi.org/{doi}" if doi else "")

                journal = ""
                if p.get("journal"):
                    journal = p["journal"].get("name", "")
                if not journal:
                    journal = p.get("venue", "")
                journal = _normalize_journal_name(journal)

                if allowed_journals and not _journal_allowed(journal, allowed_journals):
                    continue

                published = p.get("publicationDate", "") or str(p.get("year") or "")
                if not _is_recent_publication(published, since_hours):
                    continue

                papers.append(PaperItem(
                    title=p.get("title", ""),
                    authors=authors_list,
                    abstract=(p.get("abstract") or "")[:300],
                    url=url,
                    doi=doi,
                    journal=journal,
                    published=published,
                    source="semantic_scholar",
                    is_corresponding=is_corresponding,
                    matched_author=author_name,
                ))

            print(f"[Semantic Scholar] ✅ author query: {len(papers)} papers")

        except Exception as e:
            print(f"[Semantic Scholar] ❌ author query failed ({type(e).__name__})")

    return papers


# ============================================================
#  Crossref 期刊订阅
# ============================================================

async def fetch_journal_latest_crossref(
    client,
    journal_issn,
    journal_name="",
    max_results=10,
    rows=20,
    since_hours=None,
    *,
    runtime: Optional[PaperHttpRuntime] = None,
):
    papers = []
    if not isinstance(client, _RuntimeHttpClient):
        client = _RuntimeHttpClient(
            runtime or default_paper_http_runtime(),
            headers={"User-Agent": USER_AGENT},
        )
    try:
        resp = await _get_with_retry(
            client,
            f"{CROSSREF_BASE}/journals/{journal_issn}/works",
            params={
                "sort": "published",
                "order": "desc",
                "rows": rows,
                "select": "DOI,title,author,abstract,published,container-title,URL",
            },
        )
        if not resp:
            print(f"[Crossref] ❌ {journal_name}: 请求失败")
            return []

        items = resp.json().get("message", {}).get("items", [])
        for item in items[:max_results]:
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""

            authors = []
            for a in item.get("author", []):
                given = a.get("given", "")
                family = a.get("family", "")
                if given or family:
                    authors.append(f"{given} {family}".strip())

            pub_date = ""
            if item.get("published"):
                parts = item["published"].get("date-parts", [[]])[0]
                pub_date = "-".join(str(p).zfill(2) for p in parts)
            if not _is_recent_publication(pub_date, since_hours):
                continue

            cont = item.get("container-title", [])
            journal = cont[0] if cont else journal_name
            journal = _normalize_journal_name(journal)

            abstract = item.get("abstract", "")
            if abstract:
                abstract = re.sub(r"<[^>]+>", "", abstract).strip()

            doi = item.get("DOI", "")
            papers.append(PaperItem(
                title=title, authors=authors, abstract=abstract[:300],
                url=item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
                doi=doi, journal=journal, published=pub_date, source="crossref",
            ))

        print(f"[Crossref] ✅ {journal_name or journal_issn}: {len(papers)} 篇")
    except Exception as e:
        print(f"[Crossref] ❌ journal query failed ({type(e).__name__})")
    return papers


async def fetch_all_journals(
    journals,
    max_per_journal=20,
    since_hours=None,
    *,
    runtime: Optional[PaperHttpRuntime] = None,
):
    headers = {"User-Agent": USER_AGENT}
    all_papers = []
    async with _RuntimeHttpClient(runtime or default_paper_http_runtime(), headers=headers) as client:
        for journal_name in journals:
            if journal_name not in OPTICS_JOURNALS:
                continue
            issn = OPTICS_JOURNALS[journal_name]["issn"]
            papers = await fetch_journal_latest_crossref(client, issn, journal_name, max_results=max_per_journal, since_hours=since_hours)
            all_papers.append(papers)
    return all_papers


async def fetch_recent_crossref_for_authors(
    author_names,
    journals=None,
    since_hours=None,
    max_per_journal=8,
    *,
    runtime: Optional[PaperHttpRuntime] = None,
):
    """Scan each configured journal once, then match all tracked authors locally."""
    if journals is None:
        journals = list(OPTICS_JOURNALS.keys())

    crossref_results = await fetch_all_journals(
        journals,
        max_per_journal=max_per_journal,
        since_hours=since_hours,
        runtime=runtime,
    )

    matched = []
    for journal_papers in crossref_results:
        for paper in journal_papers:
            for target_name in author_names:
                for idx, author in enumerate(paper.authors):
                    if _name_matches(target_name, author):
                        paper.is_corresponding = idx == len(paper.authors) - 1
                        paper.matched_author = target_name
                        paper.source = "crossref"
                        matched.append(paper)
                        break
                if paper.matched_author:
                    break

    seen = set()
    deduped = []
    for paper in matched:
        key = paper.doi.lower() if paper.doi else paper.title.lower()[:100]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(paper)
    if deduped:
        await enrich_missing_abstracts(deduped, runtime=runtime)
    print(f"[Crossref] tracked authors: {len(deduped)} recent papers")
    return deduped


# ============================================================
#  主入口
# ============================================================

async def search_corresponding_papers(
    author_name,
    journals=None,
    max_per_journal=20,
    year_from=None,
    since_hours=None,
    *,
    runtime: Optional[PaperHttpRuntime] = None,
):
    print(f"\n{'='*60}")
    print("  🔍 搜索已配置作者的通讯论文")
    print(f"{'='*60}\n")

    if journals is None:
        journals = list(OPTICS_JOURNALS.keys())

    # 1. Semantic Scholar 论文搜索
    ss_papers = await search_by_author_semantic_scholar(
        author_name, max_results=50, year_from=year_from, allowed_journals=journals,
        since_hours=since_hours, runtime=runtime
    )

    # 2. Crossref 期刊池
    print(f"\n[Crossref] 开始扫描 {len(journals)} 本期刊...")
    crossref_results = await fetch_all_journals(
        journals,
        max_per_journal,
        since_hours=since_hours,
        runtime=runtime,
    )

    # 3. 严格匹配
    matched_in_journals = []
    for journal_papers in crossref_results:
        for paper in journal_papers:
            for idx, author in enumerate(paper.authors):
                if _name_matches(author_name, author):
                    paper.is_corresponding = (idx == len(paper.authors) - 1)
                    paper.matched_author = author_name
                    matched_in_journals.append(paper)
                    break

    print(f"\n[Match] 期刊池中匹配到 {len(matched_in_journals)} 篇含作者的论文")

    # 4. 去重
    seen = set()
    combined = []
    for p in matched_in_journals + ss_papers:
        key = p.doi.lower() if p.doi else p.title.lower()[:80]
        if key not in seen:
            seen.add(key)
            combined.append(p)

    combined.sort(key=lambda x: x.published, reverse=True)
    return combined


def print_papers(papers, only_corresponding=False):
    if only_corresponding:
        papers = [p for p in papers if p.is_corresponding]
    if not papers:
        print("❌ 未找到符合条件的论文")
        return

    print(f"\n📚 共 {len(papers)} 篇论文" + ("（仅通讯作者）" if only_corresponding else "") + ":\n")
    for i, p in enumerate(papers, 1):
        marker = "🌟" if p.is_corresponding else "  "
        print(f"{marker} [{i}] {p.title}")
        author_strs = list(p.authors[:6])
        if len(p.authors) > 6:
            author_strs.append(f"...等{len(p.authors)}人")
        print(f"     作者: {', '.join(author_strs)}")
        if p.journal: print(f"     期刊: {p.journal}")
        if p.published: print(f"     时间: {p.published}")
        if p.is_corresponding: print("     ✨ 通讯作者匹配")
        if p.abstract: print(f"     摘要: {p.abstract[:150]}...")
        if p.url: print(f"     链接: {p.url}")
        print(f"     来源: {p.source}\n")


__all__ = [
    "CrossrefCollector",
    "PaperItem",
    "SemanticScholarCollector",
    "enrich_missing_abstracts",
    "fetch_abstract_for_doi_or_url",
    "fetch_all_journals",
    "fetch_journal_latest_crossref",
    "fetch_recent_crossref_for_authors",
    "print_papers",
    "search_by_author_semantic_scholar",
    "search_corresponding_papers",
]
