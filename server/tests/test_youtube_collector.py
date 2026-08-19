"""PK-131 YouTube Collector checks using fake Atom feeds and MockTransport."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from typing import Iterable, Mapping
from urllib.parse import parse_qs

import _path_setup  # noqa: F401
import httpx

from core.intel_contracts import CacheStatus, CollectRequest, CoverageStatus
from features.youtube import (
    FEED_URL,
    YouTubeCollector,
    YouTubeVideo,
    fetch_youtube,
    is_channel_id,
    parse_youtube_timestamp,
    validate_channel_id,
    youtube_video_stable_id,
)


CHANNEL_A = "UCaaaaaaaaaaaaaaaaaaaaaa"
CHANNEL_B = "UCbbbbbbbbbbbbbbbbbbbbbb"
VIDEO_A = "abc123DEF45"
VIDEO_B = "xyz987UVW65"
NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


def atom_feed(channel_id: str, entries: Iterable[Mapping[str, str]] = ()) -> str:
    rendered_entries = []
    for entry in entries:
        rendered_entries.append(
            f"""
  <entry>
    <yt:videoId>{entry.get('video_id', VIDEO_A)}</yt:videoId>
    <yt:channelId>{entry.get('channel_id', channel_id)}</yt:channelId>
    <title>{entry.get('title', 'Fake video')}</title>
    <link rel="alternate" href="{entry.get('url', 'https://www.youtube.com/watch?v=' + VIDEO_A)}" />
    <author><name>{entry.get('author', 'Fake channel title')}</name></author>
    <published>{entry.get('published', '2026-07-22T15:30:00+08:00')}</published>
    <updated>{entry.get('updated', '2026-07-22T07:45:00Z')}</updated>
    <media:group>
      <media:description>{entry.get('summary', 'Fake description')}</media:description>
      <media:thumbnail url="{entry.get('thumbnail', 'https://i.ytimg.com/vi/' + VIDEO_A + '/hqdefault.jpg')}" />
    </media:group>
  </entry>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <yt:channelId>{channel_id}</yt:channelId>
  <title>Fake channel title</title>
  {''.join(rendered_entries)}
</feed>"""


def request_for(channel_ids, *, refresh: bool = False, lookback: int = 24) -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=("youtube",),
        refresh=refresh,
        lookback=lookback,
        source_config_snapshot={"youtube_channel_ids": channel_ids},
    )


async def check_channel_id_guard() -> None:
    assert validate_channel_id(CHANNEL_A) == CHANNEL_A
    assert is_channel_id(CHANNEL_A)
    invalid_values = (
        "Fake channel title",
        "@fake_handle",
        "https://www.youtube.com/@fake_handle",
        "youtube.com/channel/" + CHANNEL_A,
        "UC_too_short",
        "uc" + "a" * 22,
    )
    for value in invalid_values:
        assert not is_channel_id(value)
        try:
            validate_channel_id(value)
            raise AssertionError(f"invalid Channel ID was accepted: {value}")
        except ValueError:
            pass

    calls = []

    def forbidden_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("invalid Channel IDs must not cause HTTP requests")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden_handler)) as client:
        collector = YouTubeCollector(client=client, clock=lambda: NOW, request_interval_seconds=0)
        invalid = await collector.collect(request_for(list(invalid_values)))
        missing = await collector.collect(request_for([]))
        scalar = await collector.collect(request_for(CHANNEL_A))
    assert not calls
    assert invalid.coverage.status is CoverageStatus.FAILED
    assert invalid.coverage.item_count == 0 and invalid.warnings
    assert missing.coverage.status is CoverageStatus.NOT_CONFIGURED
    assert scalar.coverage.status is CoverageStatus.FAILED


async def check_atom_parse_time_stable_id_and_dedupe() -> None:
    requested_urls = []
    feed = atom_feed(CHANNEL_A, (
        {
            "video_id": VIDEO_A,
            "title": "  Fresh   fake video  ",
            "published": "2026-07-22T15:30:00+08:00",
            "summary": "Fake summary",
        },
        {
            "video_id": VIDEO_A,
            "title": "Duplicate title must not create another item",
            "published": "2026-07-22T07:31:00Z",
        },
        {
            "video_id": VIDEO_B,
            "title": "Outside lookback",
            "published": "2026-07-20T00:00:00Z",
        },
    ))

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(request.url)
        assert request.url.scheme == "https"
        assert request.url.host == "www.youtube.com"
        assert request.url.path == "/feeds/videos.xml"
        assert parse_qs(request.url.query.decode())["channel_id"] == [CHANNEL_A]
        return httpx.Response(200, text=feed, headers={"content-type": "application/atom+xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await YouTubeCollector(
            client=client,
            clock=lambda: NOW,
            request_interval_seconds=0,
        ).collect(request_for([CHANNEL_A], refresh=True))

    assert len(requested_urls) == 1
    assert result.coverage.status is CoverageStatus.COMPLETE
    assert result.cache_status is CacheStatus.REFRESHED
    assert len(result.items) == 1
    item = result.items[0]
    assert item.title == "Fresh fake video"
    assert item.summary == "Fake summary"
    assert item.author == "Fake channel title"
    assert item.published_at == "2026-07-22T07:30:00Z"
    assert item.fetched_at == "2026-07-22T08:00:00Z"
    assert item.metadata["video_id"] == VIDEO_A
    assert item.metadata["channel_id"] == CHANNEL_A
    assert item.stable_id == youtube_video_stable_id(VIDEO_A)
    assert item.stable_id == youtube_video_stable_id(VIDEO_A), "title changes must not affect stable ID"
    assert parse_youtube_timestamp("2026-07-22T15:30:00+08:00") == "2026-07-22T07:30:00Z"
    json.dumps(result.to_dict(), ensure_ascii=False)


async def check_empty_partial_failed_and_throttle() -> None:
    sleeps = []
    seen_channel_ids = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def mixed_handler(request: httpx.Request) -> httpx.Response:
        channel_id = parse_qs(request.url.query.decode())["channel_id"][0]
        seen_channel_ids.append(channel_id)
        assert str(request.url).startswith(FEED_URL + "?")
        if channel_id == CHANNEL_B:
            raise httpx.ReadTimeout("fake body must not escape", request=request)
        return httpx.Response(200, text=atom_feed(CHANNEL_A, ({"video_id": VIDEO_A},)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(mixed_handler)) as client:
        partial = await YouTubeCollector(
            client=client,
            clock=lambda: NOW,
            request_interval_seconds=1.5,
            sleep=fake_sleep,
        ).collect(request_for([CHANNEL_A, "@not-a-channel-id", CHANNEL_B]))
    assert seen_channel_ids == [CHANNEL_A, CHANNEL_B]
    assert sleeps == [1.5]
    assert partial.coverage.status is CoverageStatus.PARTIAL
    assert len(partial.items) == 1
    assert all("fake body must not escape" not in warning for warning in partial.warnings)
    assert all(CHANNEL_A not in warning and CHANNEL_B not in warning for warning in partial.warnings)

    def empty_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=atom_feed(CHANNEL_A))

    async with httpx.AsyncClient(transport=httpx.MockTransport(empty_handler)) as client:
        empty = await YouTubeCollector(client=client, clock=lambda: NOW, request_interval_seconds=0).collect(
            request_for([CHANNEL_A])
        )
    assert empty.coverage.status is CoverageStatus.EMPTY
    assert empty.coverage.item_count == 0 and not empty.warnings

    secret_body = "token=fake-upstream-secret"

    def failed_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=secret_body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failed_handler)) as client:
        failed = await YouTubeCollector(client=client, clock=lambda: NOW, request_interval_seconds=0).collect(
            request_for([CHANNEL_A])
        )
    assert failed.coverage.status is CoverageStatus.FAILED
    assert secret_body not in "\n".join(failed.warnings)
    assert CHANNEL_A not in "\n".join(failed.warnings)
    assert any("http_503" in warning for warning in failed.warnings)


async def check_feed_identity_and_legacy_facade() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=atom_feed(CHANNEL_A, ({"video_id": VIDEO_A},)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        legacy = await fetch_youtube(
            [CHANNEL_A],
            client=client,
            clock=lambda: NOW,
            request_interval_seconds=0,
        )
    assert len(calls) == 1 and len(legacy) == 1
    assert isinstance(legacy[0], YouTubeVideo)
    assert legacy[0].published == "2026-07-22T07:30:00Z"
    assert legacy[0].thumbnail.startswith("https://i.ytimg.com/")
    assert not legacy.warnings

    def mismatch_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=atom_feed(CHANNEL_B, ({"video_id": VIDEO_B},)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(mismatch_handler)) as client:
        mismatch = await YouTubeCollector(client=client, clock=lambda: NOW, request_interval_seconds=0).collect(
            request_for([CHANNEL_A])
        )
    assert mismatch.coverage.status is CoverageStatus.FAILED
    assert any("feed_channel_id_mismatch" in warning for warning in mismatch.warnings)


async def main() -> int:
    await check_channel_id_guard()
    await check_atom_parse_time_stable_id_and_dedupe()
    await check_empty_partial_failed_and_throttle()
    await check_feed_identity_and_legacy_facade()
    print("youtube collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
