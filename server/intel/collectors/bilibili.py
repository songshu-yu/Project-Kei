"""PK-130 Bilibili profile compatibility helpers and Collector 1.0 adapter."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from features.bilibili.client import (
    BilibiliClientError,
    BilibiliPublicClient,
    normalize_uid,
)
from features.bilibili.credentials import load_active_bilibili_cookies
from core.intel_contracts import (
    Collector,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    normalize_url,
    rfc3339,
    stable_item_id,
)


SOURCE_ID = "bilibili"
DEFAULT_FAILURE_COOLDOWN = timedelta(hours=6)
_BILIBILI_FAILURE_CODES = frozenset({
    "anti_bot",
    "invalid_response",
    "not_found",
    "rate_limited",
    "timeout",
    "upstream_failed",
    "upstream_rejected",
    "upstream_unavailable",
})

NowProvider = Callable[[], datetime]


@dataclass
class BiliDynamic:
    """Legacy shape retained for ``intel.briefing`` during serial integration."""

    uid: int
    username: str
    content: str
    url: str
    dynamic_type: str
    published: str


class BiliResult(list):
    def __init__(self, items: Optional[Sequence[BiliDynamic]] = None, warnings: Optional[Sequence[str]] = None):
        super().__init__(items or [])
        self.warnings = list(warnings or [])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _configured_cookies() -> dict[str, str]:
    """Load only the active allowlisted values for an explicit operation."""
    return load_active_bilibili_cookies()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, limit: int = 4000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _absolute_bilibili_url(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        text = "https:" + text
    elif text.startswith("/"):
        text = "https://www.bilibili.com" + text
    return normalize_url(text)


def _dynamic_fields(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    modules = _mapping(payload.get("modules"))
    dynamic_module = _mapping(modules.get("module_dynamic"))
    description = _mapping(dynamic_module.get("desc"))
    description_text = _text(description.get("text"))
    major = _mapping(dynamic_module.get("major"))
    major_type = _text(major.get("type"), 80)

    title = summary = jump_url = ""
    for key in ("archive", "opus", "article", "common"):
        candidate = _mapping(major.get(key))
        if not candidate:
            continue
        title = _text(candidate.get("title") or candidate.get("name"), 1000)
        summary = _text(
            candidate.get("desc")
            or candidate.get("summary")
            or candidate.get("description"),
            4000,
        )
        jump_url = _absolute_bilibili_url(candidate.get("jump_url") or candidate.get("url"))
        if key == "archive" and not jump_url:
            bvid = _text(candidate.get("bvid"), 80)
            if bvid:
                jump_url = normalize_url(f"https://www.bilibili.com/video/{bvid}")
        break

    if not title and major_type == "MAJOR_TYPE_LIVE_RCMD":
        live_payload = _mapping(major.get("live_rcmd"))
        raw_content = live_payload.get("content")
        if isinstance(raw_content, str):
            try:
                raw_content = json.loads(raw_content)
            except (TypeError, ValueError):
                raw_content = {}
        live_content = _mapping(raw_content)
        live_info = _mapping(live_content.get("live_play_info"))
        title = _text(live_info.get("title"), 1000)
        jump_url = _absolute_bilibili_url(live_info.get("link"))

    if not title:
        title = description_text or "发布了新的 B 站动态"
    if not summary and description_text and description_text != title:
        summary = description_text
    return title, summary, jump_url


def _parse_dynamic(
    payload: Mapping[str, Any],
    *,
    uid: int,
    fetched_at: datetime,
) -> Optional[IntelItem]:
    dynamic_id = _text(payload.get("id_str") or payload.get("id"), 160)
    dynamic_type = _text(payload.get("type"), 80) or "DYNAMIC_TYPE_UNKNOWN"
    modules = _mapping(payload.get("modules"))
    author_module = _mapping(modules.get("module_author"))
    author = _text(author_module.get("name"), 300) or f"UID:{uid}"
    title, summary, jump_url = _dynamic_fields(payload)

    try:
        published_timestamp = int(author_module.get("pub_ts") or 0)
    except (TypeError, ValueError):
        published_timestamp = 0
    published_at = ""
    if published_timestamp > 0:
        try:
            published_at = rfc3339(datetime.fromtimestamp(published_timestamp, tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            published_at = ""

    url = jump_url
    if not url and dynamic_id:
        url = normalize_url(f"https://t.bilibili.com/{dynamic_id}")
    return IntelItem(
        stable_id=stable_item_id(
            SOURCE_ID,
            upstream_id=dynamic_id,
            url=url,
            title=title,
            author=author,
            published_at=published_at,
        ),
        source_id=SOURCE_ID,
        category="video",
        title=title,
        summary=summary,
        url=url,
        author=author,
        published_at=published_at,
        fetched_at=rfc3339(fetched_at),
        metadata={
            "uid": uid,
            "dynamic_id": dynamic_id,
            "dynamic_type": dynamic_type,
        },
    )


def _configured_uids(snapshot: Mapping[str, Any]) -> list[int]:
    values = snapshot.get("bilibili_uids", [])
    if not isinstance(values, (list, tuple)):
        return []
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            uid = normalize_uid(value)
        except ValueError:
            continue
        if uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result


class BilibiliCollector:
    """Collector 1.0 implementation for configured Bilibili space dynamics."""

    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        client: Optional[BilibiliPublicClient] = None,
        max_items_per_uid: int = 5,
        failure_cooldown: timedelta = DEFAULT_FAILURE_COOLDOWN,
        now: NowProvider = _utc_now,
    ) -> None:
        self._client = client or BilibiliPublicClient(cookies_provider=_configured_cookies)
        self._max_items_per_uid = max(1, min(30, int(max_items_per_uid)))
        self._failure_cooldown = max(timedelta(minutes=1), failure_cooldown)
        self._now = now
        self._cooldowns: dict[int, datetime] = {}
        self._cooldown_codes: dict[int, str] = {}
        # The installable entrypoint is synchronous; defer loop binding until
        # the first Collector call.
        self._collect_lock: Optional[asyncio.Lock] = None
        self._collect_loop: Optional[asyncio.AbstractEventLoop] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    def _lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._collect_lock is None or self._collect_loop is not loop:
            self._collect_lock = asyncio.Lock()
            self._collect_loop = loop
        return self._collect_lock

    def _failure_result(
        self,
        *,
        fetched_at: datetime,
        warnings: Sequence[str],
        retry_after: Optional[datetime] = None,
        cache_status: CacheStatus = CacheStatus.UNAVAILABLE,
    ) -> CollectorResult:
        retry_text = rfc3339(retry_after) if retry_after is not None else None
        safe_warnings = tuple(warnings) or ("Bilibili source unavailable",)
        return CollectorResult(
            source_id=SOURCE_ID,
            items=(),
            warnings=safe_warnings,
            coverage=SourceCoverage(
                CoverageStatus.FAILED,
                0,
                "Configured Bilibili targets could not be collected",
                retry_text,
            ),
            fetched_at=rfc3339(fetched_at),
            retry_after=retry_text,
            cache_status=cache_status,
        )

    async def collect(self, request: CollectRequest) -> CollectorResult:
        if not isinstance(request, CollectRequest):
            raise TypeError("request must be a CollectRequest")
        now = _aware_utc(self._now())
        if SOURCE_ID not in request.source_ids:
            return CollectorResult(
                source_id=SOURCE_ID,
                items=(),
                warnings=(),
                coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, 0, "source not requested"),
                fetched_at=rfc3339(now),
                cache_status=CacheStatus.UNAVAILABLE,
            )

        uids = _configured_uids(request.source_config_snapshot)
        if not uids:
            return CollectorResult(
                source_id=SOURCE_ID,
                items=(),
                warnings=(),
                coverage=SourceCoverage(CoverageStatus.NOT_CONFIGURED, 0, "no Bilibili UID configured"),
                fetched_at=rfc3339(now),
                cache_status=CacheStatus.UNAVAILABLE,
            )

        async with self._lock():
            now = _aware_utc(self._now())
            for uid, retry_at in list(self._cooldowns.items()):
                if retry_at <= now:
                    self._cooldowns.pop(uid, None)
                    self._cooldown_codes.pop(uid, None)

            items: list[IntelItem] = []
            failure_count = 0
            failure_codes: dict[str, int] = {}
            cooldown_count = 0
            succeeded_count = 0
            retry_values: list[datetime] = []
            cutoff = now - timedelta(hours=request.lookback)

            for uid in uids:
                active_retry = self._cooldowns.get(uid)
                if active_retry is not None and active_retry > now:
                    cooldown_count += 1
                    failure_count += 1
                    code = self._cooldown_codes.get(uid, "upstream_unavailable")
                    failure_codes[code] = failure_codes.get(code, 0) + 1
                    retry_values.append(active_retry)
                    continue
                try:
                    raw_items = await self._client.fetch_space_dynamics(uid)
                    succeeded_count += 1
                    kept = 0
                    for raw_item in raw_items:
                        item = _parse_dynamic(raw_item, uid=uid, fetched_at=now)
                        if item is None:
                            continue
                        if item.published_at:
                            published = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
                            if published < cutoff or published > now + timedelta(minutes=5):
                                continue
                        items.append(item)
                        kept += 1
                        if kept >= self._max_items_per_uid:
                            break
                except BilibiliClientError as exc:
                    failure_count += 1
                    code = (
                        exc.code
                        if exc.code in _BILIBILI_FAILURE_CODES
                        else "upstream_failed"
                    )
                    retry_at = now + self._failure_cooldown
                    self._cooldowns[uid] = retry_at
                    self._cooldown_codes[uid] = code
                    failure_codes[code] = failure_codes.get(code, 0) + 1
                    retry_values.append(retry_at)
                except ValueError:
                    failure_count += 1
                    code = "invalid_response"
                    retry_at = now + self._failure_cooldown
                    self._cooldowns[uid] = retry_at
                    self._cooldown_codes[uid] = code
                    failure_codes[code] = failure_codes.get(code, 0) + 1
                    retry_values.append(retry_at)

            retry_after = min(retry_values) if retry_values else None
            retry_text = rfc3339(retry_after) if retry_after is not None else None
            warnings: list[str] = []
            if failure_count:
                warnings.append(f"Bilibili temporarily unavailable for {failure_count} target(s)")
            if cooldown_count:
                warnings.append(f"Bilibili failure cooldown active for {cooldown_count} target(s)")
            warnings.extend(
                f"Bilibili: {count} target(s) failed ({code})"
                for code, count in sorted(failure_codes.items())
            )

            if items and failure_count:
                status = CoverageStatus.PARTIAL
            elif items:
                status = CoverageStatus.COMPLETE
            elif failure_count and succeeded_count:
                status = CoverageStatus.FAILED
            elif succeeded_count:
                status = CoverageStatus.EMPTY
            else:
                failure_warnings = warnings
                if cooldown_count and cooldown_count == failure_count:
                    cooldown_warning = (
                        f"Bilibili failure cooldown active for {cooldown_count} target(s)"
                    )
                    failure_warnings = [
                        cooldown_warning,
                        *(value for value in warnings if value != cooldown_warning),
                    ]
                return self._failure_result(
                    fetched_at=now,
                    warnings=failure_warnings,
                    retry_after=retry_after,
                    cache_status=CacheStatus.UNAVAILABLE,
                )

            detail = ""
            if status == CoverageStatus.PARTIAL:
                detail = "some configured Bilibili targets were unavailable"
            elif status == CoverageStatus.FAILED:
                detail = "configured Bilibili targets were not fully available"
            return CollectorResult(
                source_id=SOURCE_ID,
                items=tuple(items),
                warnings=tuple(warnings),
                coverage=SourceCoverage(status, len(items), detail, retry_text),
                fetched_at=rfc3339(now),
                retry_after=retry_text,
                cache_status=CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED,
            )


def collector_interface(value: BilibiliCollector) -> Collector:
    """Typing-only helper documenting conformance to the frozen protocol."""
    return value


async def fetch_bilibili_profile(
    uid: object,
    *,
    client: Optional[BilibiliPublicClient] = None,
) -> dict[str, Any]:
    """Legacy profile helper; it performs exactly one profile operation."""
    if client is not None:
        return await client.fetch_profile(uid)
    async with BilibiliPublicClient(cookies_provider=_configured_cookies) as public_client:
        return await public_client.fetch_profile(uid)


async def fetch_bilibili(
    uids: Sequence[object],
    max_per_user: int = 5,
    since_hours: Optional[int] = None,
    *,
    client: Optional[BilibiliPublicClient] = None,
    now: Optional[datetime] = None,
) -> BiliResult:
    """Legacy list adapter backed by the new dynamic Collector, not video APIs."""
    normalized_uids = [normalize_uid(uid) for uid in uids]
    collector = BilibiliCollector(
        client=client,
        max_items_per_uid=max_per_user,
        now=(lambda: now) if now is not None else _utc_now,
    )
    request = CollectRequest(
        local_date=_aware_utc(now or _utc_now()).date(),
        timezone="Asia/Shanghai",
        source_ids=(SOURCE_ID,),
        refresh=False,
        lookback=max(1, min(720, int(since_hours or 24))),
        source_config_snapshot={"bilibili_uids": normalized_uids},
    )
    try:
        result = await collector.collect(request)
    finally:
        if client is None:
            await collector.aclose()
    legacy_items = []
    for item in result.items:
        summary = f" - {item.summary}" if item.summary else ""
        legacy_items.append(BiliDynamic(
            uid=int(item.metadata.get("uid") or 0),
            username=item.author,
            content=f"{item.title}{summary}",
            url=item.url,
            dynamic_type=str(item.metadata.get("dynamic_type") or ""),
            published=item.published_at,
        ))
    return BiliResult(legacy_items, result.warnings)


__all__ = [
    "BiliDynamic",
    "BiliResult",
    "BilibiliCollector",
    "collector_interface",
    "fetch_bilibili",
    "fetch_bilibili_profile",
]
