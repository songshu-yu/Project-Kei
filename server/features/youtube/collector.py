"""Public YouTube Atom feed Collector for PK-131.

Only canonical YouTube Channel IDs are accepted.  Channel names, handles and
channel URLs are display/discovery values and are never interpolated into an
HTTP request by this module.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Iterable, List, Optional, Sequence, Tuple

import httpx

from core.intel_contracts import (
    Collector,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    aware_timestamp,
    normalize_url,
    rfc3339,
    stable_item_id,
)


SOURCE_ID = "youtube"
FEED_URL = "https://www.youtube.com/feeds/videos.xml"
CHANNEL_ID_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")
VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
MAX_FEED_BYTES = 2 * 1024 * 1024
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


@dataclass(frozen=True)
class YouTubeVideo:
    """Legacy display value retained for ``intel.briefing`` compatibility."""

    channel: str
    title: str
    url: str
    published: str
    thumbnail: str = ""


class YouTubeResult(list):
    """Legacy list result with bounded source warnings."""

    def __init__(self, items: Optional[Iterable[YouTubeVideo]] = None, warnings: Optional[Iterable[str]] = None):
        super().__init__(items or [])
        self.warnings = list(warnings or [])


class _FeedFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def validate_channel_id(value: object) -> str:
    """Return a canonical Channel ID or reject names, handles and URLs."""
    channel_id = str(value or "").strip()
    if not CHANNEL_ID_RE.fullmatch(channel_id):
        raise ValueError("YouTube Channel ID must be UC followed by 22 URL-safe characters")
    return channel_id


def is_channel_id(value: object) -> bool:
    try:
        validate_channel_id(value)
    except ValueError:
        return False
    return True


def parse_youtube_timestamp(value: object) -> str:
    """Normalize an Atom timestamp to timezone-aware UTC RFC 3339."""
    return aware_timestamp(value, required=True)


def youtube_video_stable_id(video_id: object) -> str:
    """Build a stable Collector ID from YouTube's immutable video ID."""
    normalized = str(video_id or "").strip()
    if not VIDEO_ID_RE.fullmatch(normalized):
        raise ValueError("invalid YouTube video ID")
    return stable_item_id(SOURCE_ID, upstream_id=normalized)


def _entry_link(entry: ET.Element, video_id: str) -> str:
    for link in entry.findall("atom:link", NS):
        href = str(link.get("href") or "").strip()
        if href and str(link.get("rel") or "alternate") == "alternate":
            return normalize_url(href)
    return normalize_url(f"https://www.youtube.com/watch?v={video_id}")


def _timestamp_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class YouTubeCollector:
    """Collector 1.0 implementation backed only by public YouTube Atom feeds."""

    source_id = SOURCE_ID

    def __init__(
        self,
        *,
        client: Optional[httpx.AsyncClient] = None,
        max_per_channel: int = 5,
        request_interval_seconds: float = 0.25,
        timeout_seconds: float = 15.0,
        trust_env: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if isinstance(max_per_channel, bool) or int(max_per_channel) < 1:
            raise ValueError("max_per_channel must be positive")
        self._client = client
        self._max_per_channel = int(max_per_channel)
        self._request_interval_seconds = max(0.0, float(request_interval_seconds))
        self._timeout_seconds = max(0.1, float(timeout_seconds))
        self._trust_env = bool(trust_env)
        self._clock = clock
        self._sleep = sleep

    async def collect(self, request: CollectRequest) -> CollectorResult:
        fetched_dt = self._clock()
        if fetched_dt.tzinfo is None or fetched_dt.utcoffset() is None:
            raise ValueError("YouTube Collector clock must return an aware datetime")
        fetched_dt = fetched_dt.astimezone(timezone.utc)
        fetched_at = rfc3339(fetched_dt)
        channel_ids, warnings, configured_count = self._configured_channel_ids(request)

        if configured_count == 0:
            return self._result(
                fetched_at,
                (),
                (),
                CoverageStatus.NOT_CONFIGURED,
                "no YouTube Channel IDs configured",
                request.refresh,
            )
        if not channel_ids:
            return self._result(
                fetched_at,
                (),
                warnings,
                CoverageStatus.FAILED,
                "configured YouTube Channel IDs are invalid",
                request.refresh,
            )

        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers={
                    "User-Agent": "ProjectKei/1.0 YouTube Atom collector",
                    "Accept": "application/atom+xml, application/xml, text/xml",
                },
                follow_redirects=True,
                trust_env=self._trust_env,
            )

        items: List[IntelItem] = []
        successful_channels = 0
        requested_channels = 0
        try:
            for channel_id in channel_ids:
                if requested_channels and self._request_interval_seconds:
                    await self._sleep(self._request_interval_seconds)
                requested_channels += 1
                channel_label = f"configured channel {requested_channels}"
                try:
                    response = await client.get(FEED_URL, params={"channel_id": channel_id})
                    if response.status_code != 200:
                        raise _FeedFailure(f"http_{response.status_code}")
                    if len(response.content) > MAX_FEED_BYTES:
                        raise _FeedFailure("feed_too_large")
                    parsed_items, entry_warnings = self._parse_feed(
                        response.content,
                        channel_id=channel_id,
                        channel_label=channel_label,
                        fetched_at=fetched_at,
                        fetched_dt=fetched_dt,
                        lookback=request.lookback,
                    )
                    items.extend(parsed_items)
                    warnings.extend(entry_warnings)
                    successful_channels += 1
                except httpx.TimeoutException:
                    warnings.append(f"youtube {channel_label}: request_timeout")
                except httpx.RequestError as exc:
                    warnings.append(f"youtube {channel_label}: request_{type(exc).__name__}")
                except _FeedFailure as exc:
                    warnings.append(f"youtube {channel_label}: {exc.code}")
        finally:
            if owns_client:
                await client.aclose()

        items = self._dedupe(items)
        if warnings:
            status = CoverageStatus.PARTIAL if items else CoverageStatus.FAILED
        else:
            status = CoverageStatus.COMPLETE if items else CoverageStatus.EMPTY
        if status is CoverageStatus.PARTIAL:
            detail = f"{successful_channels}/{configured_count} channel feeds produced usable items"
        elif status is CoverageStatus.FAILED:
            detail = "YouTube feed collection failed"
        else:
            detail = f"{successful_channels} channel feeds fetched"
        return self._result(fetched_at, items, warnings, status, detail, request.refresh)

    def _configured_channel_ids(self, request: CollectRequest) -> Tuple[List[str], List[str], int]:
        raw_values = request.source_config_snapshot.get("youtube_channel_ids")
        if raw_values is None or raw_values == [] or raw_values == ():
            return [], [], 0
        if isinstance(raw_values, (str, bytes)) or not isinstance(raw_values, Sequence):
            return [], ["youtube configuration: channel IDs must be a list"], 1

        result: List[str] = []
        warnings: List[str] = []
        seen = set()
        for index, raw_value in enumerate(raw_values):
            try:
                channel_id = validate_channel_id(raw_value)
            except ValueError:
                warnings.append(f"youtube configuration: invalid Channel ID at index {index}")
                continue
            if channel_id not in seen:
                seen.add(channel_id)
                result.append(channel_id)
        return result, warnings, len(raw_values)

    def _parse_feed(
        self,
        payload: bytes,
        *,
        channel_id: str,
        channel_label: str,
        fetched_at: str,
        fetched_dt: datetime,
        lookback: int,
    ) -> Tuple[List[IntelItem], List[str]]:
        try:
            root = ET.fromstring(payload.lstrip())
        except ET.ParseError as exc:
            raise _FeedFailure("invalid_atom_xml") from exc
        if root.tag != f"{{{NS['atom']}}}feed":
            raise _FeedFailure("not_atom_feed")
        if str(root.findtext("yt:channelId", "", NS) or "").strip() != channel_id:
            raise _FeedFailure("feed_channel_id_mismatch")

        channel_title = str(root.findtext("atom:title", channel_id, NS) or channel_id).strip()
        cutoff = fetched_dt - timedelta(hours=lookback)
        latest_allowed = fetched_dt + timedelta(minutes=5)
        items: List[IntelItem] = []
        warnings: List[str] = []
        for entry_index, entry in enumerate(root.findall("atom:entry", NS)):
            video_id = str(entry.findtext("yt:videoId", "", NS) or "").strip()
            if not VIDEO_ID_RE.fullmatch(video_id):
                warnings.append(f"youtube {channel_label}: invalid video ID at entry {entry_index}")
                continue
            entry_channel_id = str(entry.findtext("yt:channelId", channel_id, NS) or channel_id).strip()
            if entry_channel_id != channel_id:
                warnings.append(f"youtube {channel_label}: entry channel ID mismatch")
                continue
            title = str(entry.findtext("atom:title", "", NS) or "").strip()
            if not title:
                warnings.append(f"youtube {channel_label}: entry {entry_index} has no title")
                continue

            published_raw = str(entry.findtext("atom:published", "", NS) or "").strip()
            published_at = ""
            if published_raw:
                try:
                    published_at = parse_youtube_timestamp(published_raw)
                except ValueError:
                    warnings.append(f"youtube {channel_label}: entry {entry_index} has invalid published time")
            published_dt = _timestamp_datetime(published_at)
            if published_dt is not None and (published_dt < cutoff or published_dt > latest_allowed):
                continue

            author = str(entry.findtext("atom:author/atom:name", channel_title, NS) or channel_title).strip()
            summary = str(entry.findtext("media:group/media:description", "", NS) or "").strip()
            thumbnail_element = entry.find("media:group/media:thumbnail", NS)
            thumbnail = normalize_url(thumbnail_element.get("url", "") if thumbnail_element is not None else "")
            updated_raw = str(entry.findtext("atom:updated", "", NS) or "").strip()
            updated_at = ""
            if updated_raw:
                try:
                    updated_at = parse_youtube_timestamp(updated_raw)
                except ValueError:
                    pass
            metadata = {
                "video_id": video_id,
                "channel_id": channel_id,
                "thumbnail": thumbnail,
            }
            if updated_at:
                metadata["updated_at"] = updated_at
            items.append(IntelItem(
                stable_id=youtube_video_stable_id(video_id),
                source_id=SOURCE_ID,
                category="video",
                title=title,
                summary=summary,
                url=_entry_link(entry, video_id),
                author=author,
                published_at=published_at,
                fetched_at=fetched_at,
                metadata=metadata,
            ))
            if len(items) >= self._max_per_channel:
                break
        return items, warnings

    @staticmethod
    def _dedupe(items: Iterable[IntelItem]) -> List[IntelItem]:
        result: List[IntelItem] = []
        seen = set()
        for item in items:
            if item.stable_id in seen:
                continue
            seen.add(item.stable_id)
            result.append(item)
        return result

    @staticmethod
    def _result(
        fetched_at: str,
        items: Iterable[IntelItem],
        warnings: Iterable[str],
        status: CoverageStatus,
        detail: str,
        refresh: bool,
    ) -> CollectorResult:
        normalized_items = tuple(items)
        return CollectorResult(
            source_id=SOURCE_ID,
            items=normalized_items,
            warnings=tuple(warnings),
            coverage=SourceCoverage(status, len(normalized_items), detail),
            fetched_at=fetched_at,
            cache_status=CacheStatus.REFRESHED if refresh else CacheStatus.FETCHED,
        )


def create_collector(**kwargs) -> Collector:
    """Build the source adapter through the frozen Collector interface."""
    return YouTubeCollector(**kwargs)


async def fetch_youtube(
    channel_ids: Sequence[object],
    max_per_channel: int = 5,
    *,
    client: Optional[httpx.AsyncClient] = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    request_interval_seconds: float = 0.25,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> YouTubeResult:
    """Legacy facade implemented by the Collector 1.0 source adapter."""
    request = CollectRequest(
        local_date=clock().date(),
        timezone="Asia/Shanghai",
        source_ids=(SOURCE_ID,),
        lookback=720,
        source_config_snapshot={"youtube_channel_ids": list(channel_ids or [])},
    )
    result = await YouTubeCollector(
        client=client,
        max_per_channel=max_per_channel,
        request_interval_seconds=request_interval_seconds,
        clock=clock,
        sleep=sleep,
    ).collect(request)
    videos = [
        YouTubeVideo(
            channel=item.author,
            title=item.title,
            url=item.url,
            published=item.published_at,
            thumbnail=str(item.metadata.get("thumbnail") or ""),
        )
        for item in result.items
    ]
    return YouTubeResult(videos, result.warnings)


__all__ = [
    "CHANNEL_ID_RE",
    "FEED_URL",
    "NS",
    "SOURCE_ID",
    "YouTubeCollector",
    "YouTubeResult",
    "YouTubeVideo",
    "create_collector",
    "fetch_youtube",
    "is_channel_id",
    "parse_youtube_timestamp",
    "validate_channel_id",
    "youtube_video_stable_id",
]
