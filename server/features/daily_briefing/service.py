"""PK-110 briefing aggregation, cache, patch and Kei rewrite use cases."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from .collector_contracts import CollectorGateway
from .generation_status import BriefingGenerationTracker
from .models import (
    PUBLIC_SOURCE_IDS,
    BriefingDocument,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    normalize_source_ids,
    rfc3339,
    sanitize_external_text,
)
from .prompt_builder import BriefingPromptBuilder
from .providers import BriefingTextGenerator
from .repository import BriefingCachePersistenceError, BriefingRepository, document_digest
from .time_utils import get_timezone, localize


Clock = Callable[[], datetime]
SourceConfigProvider = Callable[[], Mapping[str, Any]]


class BriefingService:
    def __init__(
        self,
        gateway: CollectorGateway,
        repository: BriefingRepository,
        *,
        text_generator: Optional[BriefingTextGenerator] = None,
        source_config_provider: SourceConfigProvider = lambda: {},
        prompt_builder: Optional[BriefingPromptBuilder] = None,
        timezone_name: str = "Asia/Shanghai",
        clock: Clock = lambda: datetime.now(timezone.utc),
        patch_cooldown: timedelta = timedelta(minutes=30),
        rewrite_timeout: float = 60.0,
        section_limits: Optional[Mapping[str, int]] = None,
    ):
        get_timezone(timezone_name)
        self.gateway = gateway
        self.repository = repository
        self.text_generator = text_generator
        self.source_config_provider = source_config_provider
        self.prompt_builder = prompt_builder or BriefingPromptBuilder()
        self.timezone_name = timezone_name
        self.clock = clock
        self.patch_cooldown = patch_cooldown
        self.rewrite_timeout = max(0.01, float(rewrite_timeout))
        self.section_limits = {
            "papers": 30,
            "social": 5,
            "development": 5,
            "video": 5,
            "money": 5,
            "general": 5,
            **{str(key): max(0, int(value)) for key, value in (section_limits or {}).items()},
        }
        # Python 3.8 binds asyncio primitives to the current loop at creation.
        # Installable modules are registered synchronously before an ASGI loop
        # exists, so create the lock lazily on the first mutation request.
        self._mutation_lock: Optional[asyncio.Lock] = None
        self._generation = BriefingGenerationTracker()

    def _mutation_guard(self) -> asyncio.Lock:
        if self._mutation_lock is None:
            self._mutation_lock = asyncio.Lock()
        return self._mutation_lock

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("briefing clock must return an aware datetime")
        return value

    def today(self) -> date:
        return self._now().astimezone(get_timezone(self.timezone_name)).date()

    def read_today(self) -> Optional[BriefingDocument]:
        today = self.today()
        self.repository.invalidate_stale_summary(today)
        return self.repository.load(today)

    def read(self, local_date: date) -> Optional[BriefingDocument]:
        if local_date == self.today():
            self.repository.invalidate_stale_summary(local_date)
        return self.repository.load(local_date)

    @staticmethod
    def _parse_timestamp(value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    def _eligible(self, item: IntelItem, request: CollectRequest, now: datetime) -> bool:
        published = self._parse_timestamp(item.published_at)
        if published is None:
            return True
        if published > now.astimezone(timezone.utc) + timedelta(minutes=5):
            return False
        local_zone = get_timezone(request.timezone)
        local_now = now.astimezone(local_zone)
        if request.local_date == local_now.date():
            end = now
        else:
            end = localize(datetime.combine(request.local_date + timedelta(days=1), time.min), request.timezone)
        cutoff = end - timedelta(hours=request.lookback)
        return cutoff.astimezone(timezone.utc) <= published <= end.astimezone(timezone.utc)

    @staticmethod
    def _title_key(item: IntelItem) -> str:
        title = " ".join(item.title.casefold().split())
        author = " ".join(item.author.casefold().split())
        return f"{title}\x1f{author}"

    @staticmethod
    def _paper_sources(item: IntelItem) -> list[str]:
        values = item.metadata.get("discovery_sources", [item.source_id])
        result = []
        for value in values if isinstance(values, list) else [item.source_id]:
            source = str(value)
            if source not in result:
                result.append(source)
        if item.source_id not in result:
            result.insert(0, item.source_id)
        return result

    def _dedupe_keys(self, item: IntelItem) -> list[tuple[str, str]]:
        keys: list[tuple[str, str]] = []
        doi = str(item.metadata.get("doi", "")).strip().casefold()
        if item.category == "papers" and doi:
            normalized_doi = doi
            for prefix in ("https://doi.org/", "doi:"):
                if normalized_doi.startswith(prefix):
                    normalized_doi = normalized_doi[len(prefix):]
            keys.append(("paper-doi", normalized_doi))
        if item.url:
            keys.append(("url", item.url.casefold()))
        keys.append(("stable", f"{item.source_id}\x1f{item.stable_id}"))
        if item.category == "papers":
            keys.append(("paper-title", " ".join(item.title.casefold().split())))
        else:
            keys.append(("source-title", f"{item.source_id}\x1f{self._title_key(item)}"))
        return keys

    @staticmethod
    def _source_priority(source_id: str) -> tuple[int, str]:
        try:
            return PUBLIC_SOURCE_IDS.index(source_id), source_id
        except ValueError:
            return len(PUBLIC_SOURCE_IDS), source_id

    def _merge_items(self, first: IntelItem, second: IntelItem, key: tuple[str, str]) -> IntelItem:
        sources = sorted(
            set(self._paper_sources(first) + self._paper_sources(second)),
            key=self._source_priority,
        )
        source_id = sources[0]
        metadata = dict(first.metadata)
        for name, value in second.metadata.items():
            if name not in metadata or metadata[name] in ("", None, []):
                metadata[name] = value
        metadata["discovery_sources"] = sources
        metadata["alternate_stable_ids"] = sorted(set(
            list(metadata.get("alternate_stable_ids", []) or [])
            + [first.stable_id, second.stable_id]
        ))[:20]
        cross_source = first.source_id != second.source_id or len(sources) > 1
        stable_id = min(first.stable_id, second.stable_id)
        if cross_source:
            digest = hashlib.sha256(f"{key[0]}\x1f{key[1]}".encode("utf-8")).hexdigest()[:32]
            stable_id = f"shared:{digest}"
        summary = max((first.summary, second.summary), key=lambda value: (len(value), value))
        title = max((first.title, second.title), key=lambda value: (len(value), value.casefold()))
        author = max((first.author, second.author), key=lambda value: (len(value), value.casefold()))
        published_candidates = [value for value in (first.published_at, second.published_at) if value]
        published_at = min(published_candidates) if published_candidates else ""
        url = first.url or second.url
        fetched_at = max(first.fetched_at, second.fetched_at)
        return IntelItem(
            stable_id=stable_id,
            source_id=source_id,
            category=first.category if first.category == second.category else "general",
            title=title,
            summary=summary,
            url=url,
            author=author,
            published_at=published_at,
            fetched_at=fetched_at,
            metadata=metadata,
        )

    def _normalize_items(self, items: Iterable[IntelItem], request: CollectRequest, now: datetime) -> list[IntelItem]:
        deduped: dict[tuple[str, str], IntelItem] = {}
        aliases: dict[tuple[str, str], tuple[str, str]] = {}
        for item in items:
            if not self._eligible(item, request, now):
                continue
            keys = self._dedupe_keys(item)
            primary = next((aliases[key] for key in keys if key in aliases), keys[0])
            existing = deduped.get(primary)
            merged = item if existing is None else self._merge_items(existing, item, primary)
            deduped[primary] = merged
            for key in [*keys, *self._dedupe_keys(merged)]:
                aliases[key] = primary

        def sort_key(item: IntelItem) -> tuple[float, str]:
            published = self._parse_timestamp(item.published_at)
            stamp = published.timestamp() if published else float("-inf")
            return -stamp, item.stable_id

        grouped: dict[str, list[IntelItem]] = {}
        for item in deduped.values():
            grouped.setdefault(item.category or "general", []).append(item)
        result: list[IntelItem] = []
        order = ("papers", "social", "development", "video", "money", "general")
        for category in (*order, *sorted(set(grouped) - set(order))):
            values = sorted(grouped.get(category, []), key=sort_key)
            limit = self.section_limits.get(category, self.section_limits["general"])
            result.extend(values[:limit])
        return result

    def _failed_result(self, source_id: str, now: datetime, message: str) -> CollectorResult:
        retry_after = rfc3339(now + self.patch_cooldown)
        return CollectorResult(
            source_id=source_id,
            items=(),
            warnings=(f"{source_id}: {message}",),
            coverage=SourceCoverage(CoverageStatus.FAILED, detail=message, retry_after=retry_after),
            fetched_at=rfc3339(now),
            retry_after=retry_after,
            cache_status=CacheStatus.UNAVAILABLE,
        )

    async def _collect(
        self,
        request: CollectRequest,
        now: datetime,
        *,
        run_token: int,
    ) -> list[CollectorResult]:
        self._generation.collecting(run_token, request.source_ids)

        def report(result: CollectorResult) -> None:
            if isinstance(result, CollectorResult):
                self._generation.source_finished(run_token, result)

        try:
            observable = getattr(self.gateway, "collect_with_progress", None)
            if callable(observable):
                values = list(await observable(request, report))
            else:
                values = list(await self.gateway.collect(request))
        except Exception:
            failed = [self._failed_result(source, now, "collector gateway failed") for source in request.source_ids]
            for value in failed:
                report(value)
            return failed
        by_source: dict[str, CollectorResult] = {}
        for value in values:
            if not isinstance(value, CollectorResult):
                continue
            if value.source_id in request.source_ids and value.source_id not in by_source:
                by_source[value.source_id] = value
        normalized = [
            by_source.get(source) or self._failed_result(source, now, "collector returned no result")
            for source in request.source_ids
        ]
        for value in normalized:
            report(value)
        return normalized

    @staticmethod
    def _warnings(results: Sequence[CollectorResult]) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for result in results:
            for warning in result.warnings:
                if warning not in seen:
                    seen.add(warning)
                    values.append(warning)
        return values

    @staticmethod
    def _coverage(results: Sequence[CollectorResult]) -> dict[str, SourceCoverage]:
        return {
            result.source_id: SourceCoverage(
                result.coverage.status,
                result.coverage.item_count,
                result.coverage.detail,
                result.retry_after or result.coverage.retry_after,
            )
            for result in results
        }

    def _document_from_results(self, request: CollectRequest, results: Sequence[CollectorResult], now: datetime) -> BriefingDocument:
        items = self._normalize_items((item for result in results for item in result.items), request, now)
        coverage = self._coverage(results)
        warnings = self._warnings(results)
        stamp = rfc3339(now)
        patch_attempts = {
            result.source_id: stamp
            for result in results
            if result.coverage.status in {CoverageStatus.FAILED, CoverageStatus.PARTIAL}
        }
        document = BriefingDocument(
            local_date=request.local_date.isoformat(),
            timezone=request.timezone,
            items=items,
            coverage=coverage,
            warnings=warnings,
            text="",
            script="",
            fetched=True,
            rewritten=False,
            rewrite_status="not_requested",
            created_at=stamp,
            updated_at=stamp,
            patch_attempts=patch_attempts,
            cache_status=CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED,
        )
        document.text = self.prompt_builder.plain_text(document.local_date, items, coverage, warnings)
        return document

    def _patch_ready(self, document: BriefingDocument, source_ids: Sequence[str], now: datetime) -> list[str]:
        ready: list[str] = []
        for source_id in source_ids:
            coverage = document.coverage.get(source_id)
            if coverage is None or coverage.status not in {CoverageStatus.FAILED, CoverageStatus.PARTIAL}:
                continue
            retry_at = self._parse_timestamp(coverage.retry_after or "")
            attempted = self._parse_timestamp(document.patch_attempts.get(source_id, ""))
            local_retry = attempted + self.patch_cooldown if attempted else None
            next_retry = max((value for value in (retry_at, local_retry) if value is not None), default=None)
            if next_retry is None or now.astimezone(timezone.utc) >= next_retry:
                ready.append(source_id)
        return ready

    def _without_source(self, items: Iterable[IntelItem], source_id: str) -> list[IntelItem]:
        result = []
        for item in items:
            sources = self._paper_sources(item)
            if source_id not in sources:
                result.append(item)
                continue
            remaining = [value for value in sources if value != source_id]
            if not remaining:
                continue
            metadata = dict(item.metadata)
            metadata["discovery_sources"] = remaining
            result.append(IntelItem(
                stable_id=item.stable_id,
                source_id=sorted(remaining, key=self._source_priority)[0],
                category=item.category,
                title=item.title,
                summary=item.summary,
                url=item.url,
                author=item.author,
                published_at=item.published_at,
                fetched_at=item.fetched_at,
                metadata=metadata,
            ))
        return result

    def _merge_patch(
        self,
        document: BriefingDocument,
        request: CollectRequest,
        results: Sequence[CollectorResult],
        now: datetime,
    ) -> bool:
        before_digest = document_digest(document)
        items = list(document.items)
        changed = False
        warnings = list(document.warnings)
        for result in results:
            source_id = result.source_id
            document.patch_attempts[source_id] = rfc3339(now)
            warning_prefixes = {
                "bilibili": ("bilibili:", "bilibili "),
            }.get(source_id, (f"{source_id.casefold()}:",))
            warnings = [
                value
                for value in warnings
                if not value.casefold().startswith(warning_prefixes)
            ]
            warnings.extend(value for value in result.warnings if value not in warnings)
            failed = result.coverage.status is CoverageStatus.FAILED
            if failed:
                old_count = sum(source_id in self._paper_sources(item) for item in items)
                status = CoverageStatus.PARTIAL if old_count else CoverageStatus.FAILED
                document.coverage[source_id] = SourceCoverage(
                    status,
                    old_count,
                    result.coverage.detail or "patch failed; previous content retained",
                    result.retry_after or result.coverage.retry_after,
                )
                continue
            items = self._without_source(items, source_id)
            items.extend(result.items)
            document.coverage[source_id] = SourceCoverage(
                result.coverage.status,
                result.coverage.item_count,
                result.coverage.detail,
                result.retry_after or result.coverage.retry_after,
            )
            changed = True
        document.items = self._normalize_items(items, request, now)
        document.warnings = warnings
        document.updated_at = rfc3339(now)
        document.text = self.prompt_builder.plain_text(document.local_date, document.items, document.coverage, warnings)
        content_changed = document_digest(document) != before_digest
        if content_changed:
            document.script = ""
            document.rewritten = False
            document.rewrite_status = "not_requested"
        return content_changed

    async def _rewrite(self, document: BriefingDocument, *, refresh: bool = False) -> bool:
        if document.script and not refresh:
            return False
        fallback = self.prompt_builder.fallback_script(document)
        generated = False
        text = fallback
        if self.text_generator is not None:
            system, user = self.prompt_builder.rewrite_prompt(document, self.text_generator.system_prompt)
            try:
                result = await asyncio.wait_for(
                    self.text_generator.generate_text(
                        system,
                        user,
                        max_tokens=2200,
                        temperature=0.5,
                        fallback=fallback,
                    ),
                    timeout=self.rewrite_timeout,
                )
                candidate = sanitize_external_text(
                    getattr(result, "text", ""),
                    limit=200_000,
                    collapse_whitespace=False,
                )
                generated = bool(getattr(result, "generated", False) and candidate)
                text = candidate if generated else fallback
            except (asyncio.TimeoutError, Exception):
                generated = False
                text = fallback
        document.script = text
        document.rewritten = generated
        document.rewrite_status = "generated" if generated else "fallback"
        document.updated_at = rfc3339(self._now())
        return True

    @staticmethod
    def _unacceptable_refresh(results: Sequence[CollectorResult]) -> bool:
        def usable(result: CollectorResult) -> bool:
            if result.coverage.status is CoverageStatus.EMPTY:
                return True
            if result.coverage.status in {CoverageStatus.COMPLETE, CoverageStatus.PARTIAL}:
                return bool(result.items)
            return False

        return not results or not any(usable(result) for result in results)

    async def generate(
        self,
        *,
        local_date: Optional[date] = None,
        source_ids: Optional[Iterable[object]] = None,
        refresh: bool = False,
        rewrite: bool = True,
        rewrite_refresh: bool = False,
        patch_missing: bool = True,
        lookback: int = 24,
    ) -> BriefingDocument:
        async with self._mutation_guard():
            selected = normalize_source_ids(source_ids)
            token = self._generation.start(selected, self._now())
            try:
                document = await self._generate_locked(
                    run_token=token,
                    local_date=local_date,
                    selected=selected,
                    refresh=refresh,
                    rewrite=rewrite,
                    rewrite_refresh=rewrite_refresh,
                    patch_missing=patch_missing,
                    lookback=lookback,
                )
            except asyncio.CancelledError:
                self._generation.fail(token, self._now(), "cancelled")
                raise
            except BriefingCachePersistenceError:
                self._generation.fail(token, self._now(), "cache_save_failed")
                raise
            except Exception:
                self._generation.fail(token, self._now(), "generation_failed")
                raise
            self._generation.succeed(token, self._now())
            return document

    async def _generate_locked(
        self,
        *,
        run_token: int,
        local_date: Optional[date],
        selected: tuple[str, ...],
        refresh: bool,
        rewrite: bool,
        rewrite_refresh: bool,
        patch_missing: bool,
        lookback: int,
    ) -> BriefingDocument:
        now = self._now()
        target = local_date or now.astimezone(get_timezone(self.timezone_name)).date()
        self.repository.invalidate_stale_summary(self.today())
        previous = self.repository.load(target)
        cached = None if refresh else previous
        content_changed = False
        needs_commit = False

        if refresh and previous is not None:
            request = CollectRequest(
                local_date=target,
                timezone=self.timezone_name,
                source_ids=selected,
                refresh=True,
                lookback=lookback,
                source_config_snapshot=self.source_config_provider(),
            )
            results = await self._collect(request, now, run_token=run_token)
            if self._unacceptable_refresh(results):
                previous.cache_status = CacheStatus.HIT
                previous.refresh_status = "failed_using_cache"
                previous.refresh_message = "刷新失败，继续使用旧缓存。"
                return previous
            document = previous
            content_changed = self._merge_patch(document, request, results, now)
            document.cache_status = CacheStatus.REFRESHED
            document.refresh_status = "succeeded"
            document.refresh_message = ""
            needs_commit = True
        elif cached is None:
            request = CollectRequest(
                local_date=target,
                timezone=self.timezone_name,
                source_ids=selected,
                refresh=refresh,
                lookback=lookback,
                source_config_snapshot=self.source_config_provider(),
            )
            results = await self._collect(request, now, run_token=run_token)
            document = self._document_from_results(request, results, now)
            content_changed = True
            needs_commit = True
            if refresh:
                document.refresh_status = "succeeded"
        else:
            document = cached
            document.cache_status = CacheStatus.HIT
            patch_ids = self._patch_ready(document, selected, now) if patch_missing else []
            if patch_ids:
                request = CollectRequest(
                    local_date=target,
                    timezone=self.timezone_name,
                    source_ids=tuple(patch_ids),
                    refresh=False,
                    lookback=lookback,
                    source_config_snapshot=self.source_config_provider(),
                )
                results = await self._collect(request, now, run_token=run_token)
                content_changed = self._merge_patch(document, request, results, now)
                needs_commit = True
            else:
                self._generation.collection_not_needed(run_token)

        if rewrite:
            self._generation.phase(run_token, "rewriting")
            rewrite_changed = await self._rewrite(
                document,
                refresh=bool(rewrite_refresh or content_changed),
            )
            needs_commit = needs_commit or rewrite_changed
        elif not document.script:
            document.script = self.prompt_builder.fallback_script(document)
            document.rewritten = False
            document.rewrite_status = "fallback"
            document.updated_at = rfc3339(self._now())
            needs_commit = True
        if needs_commit:
            self._generation.phase(run_token, "saving")
            self.repository.save_transaction(
                document,
                include_summary=(
                    document.local_date == self.today().isoformat()
                    and bool(document.script.strip())
                ),
            )
        return document

    def generation_status(self) -> dict[str, object]:
        """Return a sanitized in-memory snapshot with no collection side effects."""
        return self._generation.snapshot(self._now())

    def public_result(self, document: BriefingDocument) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in document.items:
            counts[item.category] = counts.get(item.category, 0) + 1
        warnings = list(document.warnings)
        if document.refresh_message:
            warnings.append(document.refresh_message)
        return {
            "schema_version": document.schema_version,
            "collector_contract_version": "1.0",
            "date": document.local_date,
            "timezone": document.timezone,
            "fetched": document.fetched,
            "rewritten": document.rewritten,
            "rewrite_status": document.rewrite_status,
            "generated": document.rewritten,
            "fallback": document.rewrite_status == "fallback",
            "cached": document.cache_status is CacheStatus.HIT,
            "cache_status": document.cache_status.value,
            "counts": counts,
            "items": [item.to_dict() for item in document.items],
            "coverage": {key: value.to_dict() for key, value in document.coverage.items()},
            "warnings": warnings,
            "text": document.text,
            "script": document.script,
            "updated_at": document.updated_at,
            "refresh_status": document.refresh_status,
            "refresh_message": document.refresh_message,
        }

    def summary_result(self, document: Optional[BriefingDocument]) -> dict[str, Any]:
        if document is None or not document.script.strip():
            return {
                "ready": False,
                "date": self.today().isoformat(),
                "text": "",
                "generated": False,
                "fallback": False,
                "updated_at": None,
            }
        return {
            "ready": True,
            "date": document.local_date,
            "text": document.script,
            "generated": document.rewritten,
            "fallback": document.rewrite_status in {"fallback", "not_requested"},
            "updated_at": document.updated_at,
        }


__all__ = ["BriefingService"]
