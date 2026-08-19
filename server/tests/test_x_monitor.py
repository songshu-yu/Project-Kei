"""Offline PK-120 checks for the single daily X content experience."""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from features.daily_briefing.models import CacheStatus, CollectRequest, CoverageStatus
from features.x_monitor.router import build_router
from features.x_monitor.service import (
    MAX_QUERY_DAYS,
    XMonitorService,
    build_x_post_query_window,
)
from intel.collectors.twitter import (
    NitterCollector,
    fetch_x_daily_posts,
    fetch_x_posts_window,
)
from services.x_daily_cache import XDailyCachePersistenceError, XDailyContentRepository
from services.x_daily_posts import prepare_x_daily_posts_cache


BEIJING = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 22, 9, 0, tzinfo=BEIJING)

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item>
    <title>plain post</title>
    <description><![CDATA[plain post]]></description>
    <link>https://nitter.test/Alice/status/101?token=drop</link>
    <guid>https://nitter.test/Alice/status/101</guid>
    <pubDate>Wed, 22 Jul 2026 00:15:00 GMT</pubDate>
  </item>
  <item>
    <title>R to @Bob: reply body</title>
    <description><![CDATA[
      <div class="tweet-reply-context">parent text must not surface</div>
      reply body
    ]]></description>
    <link>https://nitter.test/Alice/status/102</link>
    <guid>https://nitter.test/Alice/status/102</guid>
    <pubDate>Wed, 22 Jul 2026 00:20:00 GMT</pubDate>
  </item>
  <item>
    <title>RT by @Bob: repost body</title>
    <description><![CDATA[repost body]]></description>
    <link>https://nitter.test/Alice/status/103</link>
    <guid>https://nitter.test/Alice/status/103</guid>
    <pubDate>Wed, 22 Jul 2026 00:25:00 GMT</pubDate>
  </item>
  <item>
    <title>my quote comment</title>
    <description><![CDATA[
      my quote comment
      <blockquote>quoted text must not surface</blockquote>
    ]]></description>
    <link>https://nitter.test/Alice/status/104</link>
    <guid>https://nitter.test/Alice/status/104</guid>
    <pubDate>Wed, 22 Jul 2026 00:30:00 GMT</pubDate>
  </item>
</channel></rss>"""

WINDOW_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item><title>before</title><description>before</description><link>https://nitter.test/Alice/status/200</link><pubDate>Tue, 21 Jul 2026 15:59:00 GMT</pubDate></item>
  <item><title>midnight</title><description>midnight</description><link>https://nitter.test/Alice/status/201</link><pubDate>Tue, 21 Jul 2026 16:00:00 GMT</pubDate></item>
  <item><title>zero thirty</title><description>zero thirty</description><link>https://nitter.test/Alice/status/202</link><pubDate>Tue, 21 Jul 2026 16:30:00 GMT</pubDate></item>
  <item><title>seven fifty nine</title><description>seven fifty nine</description><link>https://nitter.test/Alice/status/203</link><pubDate>Tue, 21 Jul 2026 23:59:00 GMT</pubDate></item>
  <item><title>eight</title><description>eight</description><link>https://nitter.test/Alice/status/204</link><pubDate>Wed, 22 Jul 2026 00:00:00 GMT</pubDate></item>
  <item><title>twenty three fifty nine</title><description>twenty three fifty nine</description><link>https://nitter.test/Alice/status/205</link><pubDate>Wed, 22 Jul 2026 15:59:00 GMT</pubDate></item>
  <item><title>next midnight</title><description>next midnight</description><link>https://nitter.test/Alice/status/206</link><pubDate>Wed, 22 Jul 2026 16:00:00 GMT</pubDate></item>
  <item><title>naive time</title><description>naive time</description><link>https://nitter.test/Alice/status/207</link><pubDate>2026-07-22T09:00:00</pubDate></item>
</channel></rss>"""


def item(kind: str, status_id: str, *, content: str | None = None) -> dict[str, str]:
    payload = {
        "kind": kind,
        "content": content or f"{kind} {status_id}",
        "url": f"https://nitter.test/Alice/status/{status_id}?secret=drop",
        "published": "2026-07-22 08:15",
        "published_at": "2026-07-22T08:15:00+08:00",
        "upstream_id": status_id,
    }
    if kind == "reply":
        payload["reply_to_username"] = "Bob"
    return payload


def mock_client() -> tuple[httpx.AsyncClient, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/Alice/rss":
            return httpx.Response(200, text=RSS)
        if request.url.path == "/down/rss":
            return httpx.Response(503, text="private upstream detail")
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


async def check_single_rss_content() -> None:
    client, calls = mock_client()
    try:
        content = await fetch_x_daily_posts(
            "Alice",
            ["https://nitter.test"],
            target_date=date(2026, 7, 22),
            local_tz=BEIJING,
            client=client,
            retries=0,
        )
    finally:
        await client.aclose()

    assert calls == ["/Alice/rss"]
    assert [entry["kind"] for entry in content] == ["post", "reply", "quote"]
    assert content[0]["url"] == "https://nitter.test/Alice/status/101"
    assert content[1]["reply_to_username"] == "Bob"
    serialized = json.dumps(content, ensure_ascii=False)
    assert "parent text" not in serialized
    assert "quoted text" not in serialized
    assert "repost body" not in serialized
    assert "secret" not in serialized and "token" not in serialized


async def check_shanghai_window_boundaries() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.path == "/Alice/rss"
        return httpx.Response(200, text=WINDOW_RSS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    day_window = build_x_post_query_window(
        date(2026, 7, 22),
        "day",
        now=datetime(2026, 7, 22, 23, 59, tzinfo=BEIJING),
    )
    since_window = build_x_post_query_window(
        date(2026, 7, 22),
        "since",
        now=datetime(2026, 7, 22, 8, 0, tzinfo=BEIJING),
    )
    try:
        day_result = await fetch_x_posts_window(
            "Alice",
            ["https://nitter.test"],
            start_at=day_window.start_at,
            end_at=day_window.end_at,
            client=client,
            retries=0,
        )
        since_result = await fetch_x_posts_window(
            "Alice",
            ["https://nitter.test"],
            start_at=since_window.start_at,
            end_at=since_window.end_at,
            end_inclusive=True,
            client=client,
            retries=0,
        )
    finally:
        await client.aclose()

    assert calls == ["/Alice/rss", "/Alice/rss"]
    assert [entry["upstream_id"] for entry in day_result["items"]] == [
        "201",
        "202",
        "203",
        "204",
        "205",
    ]
    assert [entry["upstream_id"] for entry in since_result["items"]] == [
        "201",
        "202",
        "203",
        "204",
    ]
    assert day_result["coverage"]["status"] == "partial"
    assert any("timezone-aware" in warning for warning in day_result["warnings"])
    assert day_window.start_at.isoformat() == "2026-07-22T00:00:00+08:00"
    assert day_window.end_at.isoformat() == "2026-07-23T00:00:00+08:00"
    assert since_window.end_at.isoformat() == "2026-07-22T08:00:00+08:00"

    assert build_x_post_query_window(
        date(2026, 2, 28),
        "day",
        now=datetime(2026, 3, 1, 9, 0, tzinfo=BEIJING),
    ).end_at.date() == date(2026, 3, 1)
    leap = build_x_post_query_window(
        date(2024, 2, 29),
        "day",
        now=datetime(2024, 3, 1, 9, 0, tzinfo=BEIJING),
    )
    assert leap.end_at.date() == date(2024, 3, 1)
    cross_year = build_x_post_query_window(
        date(2025, 12, 31),
        "day",
        now=datetime(2026, 1, 1, 9, 0, tzinfo=BEIJING),
    )
    assert cross_year.end_at.date() == date(2026, 1, 1)

    for invalid in (date(2026, 7, 23), date(2026, 7, 22) - timedelta(days=MAX_QUERY_DAYS)):
        try:
            build_x_post_query_window(
                invalid,
                "day",
                now=datetime(2026, 7, 22, 9, 0, tzinfo=BEIJING),
            )
        except ValueError:
            pass
        else:
            raise AssertionError("invalid query date was not rejected")


async def check_collector_contract() -> None:
    client, calls = mock_client()
    try:
        collector = NitterCollector(
            ["https://nitter.test"],
            client=client,
            clock=lambda: NOW.astimezone(timezone.utc),
            retries=0,
        )
        result = await collector.collect(
            CollectRequest(
                local_date=date(2026, 7, 22),
                timezone="Asia/Shanghai",
                source_ids=("twitter",),
                refresh=True,
                lookback=24,
                source_config_snapshot={
                    "twitter_users": ["Alice"],
                    "money_twitter_users": ["alice", "down"],
                },
            )
        )
    finally:
        await client.aclose()

    assert calls == ["/Alice/rss", "/down/rss"]
    assert result.source_id == "twitter"
    assert result.coverage.status is CoverageStatus.PARTIAL
    assert result.cache_status is CacheStatus.REFRESHED
    assert any("(upstream_unavailable)" in warning for warning in result.warnings)
    assert {entry.metadata["x_content_kind"] for entry in result.items} == {
        "post",
        "quote",
        "reply",
    }
    assert result.to_dict()["contract_version"] == "1.0"
    assert "private upstream detail" not in str(result.to_dict())


async def check_collector_diagnostic_code_mapping() -> None:
    cases = (
        (
            "timeout",
            lambda request: (_ for _ in ()).throw(
                httpx.ReadTimeout("fictional secret body", request=request)
            ),
        ),
        (
            "rate_limited",
            lambda _request: httpx.Response(429, text="fictional secret body"),
        ),
        (
            "parse_error",
            lambda _request: httpx.Response(200, text="<rss><broken>"),
        ),
    )
    for expected_code, handler in cases:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await NitterCollector(
                ["https://nitter.test"],
                client=client,
                clock=lambda: NOW.astimezone(timezone.utc),
                retries=0,
            ).collect(
                CollectRequest(
                    local_date=date(2026, 7, 22),
                    timezone="Asia/Shanghai",
                    source_ids=("twitter",),
                    source_config_snapshot={"twitter_users": ["Alice"]},
                )
            )
        assert result.coverage.status is CoverageStatus.FAILED
        assert any(
            f"({expected_code})" in warning
            for warning in result.warnings
        )
        assert "fictional" not in str(result.to_dict()).casefold()


async def check_single_cache() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "x-content.json"
        repository = XDailyContentRepository(path, channel="posts")
        entry = repository.replace_user(
            "Alice",
            [
                item("post", "101"),
                item("reply", "102"),
                item("quote", "104"),
                item("repost", "105"),
            ],
            now=NOW,
            x_config_groups=("twitter_users", "money_twitter_users"),
        )
        assert entry["count"] == 3
        assert [value["kind"] for value in entry["posts"]] == [
            "post",
            "reply",
            "quote",
        ]
        assert entry["posts"][1]["reply_to_username"] == "Bob"
        assert entry["posts"][0]["url"] == "https://nitter.test/Alice/status/101"

        before = path.read_bytes()
        stale = prepare_x_daily_posts_cache(path, now=NOW + timedelta(days=1))
        assert stale["users"] == {}
        assert path.read_bytes() == before

        def fail_replace(source, destination):
            raise OSError("private absolute path")

        failing = XDailyContentRepository(path, channel="posts", replace=fail_replace)
        try:
            failing.replace_user("Alice", [item("post", "999")], now=NOW)
        except XDailyCachePersistenceError as exc:
            assert "private absolute path" not in str(exc)
        else:
            raise AssertionError("atomic replacement failure was not raised")
        assert path.read_bytes() == before

        try:
            XDailyContentRepository(path, channel="replies")
        except ValueError:
            pass
        else:
            raise AssertionError("the removed replies cache channel must stay unavailable")


async def check_service_and_router() -> None:
    post_calls: list[str] = []

    async def content(username: str) -> list[dict[str, str]]:
        post_calls.append(username)
        return [
            item("post", "301", content=f"post by {username}"),
            item("reply", "302", content=f"reply by {username}"),
        ]

    snapshot = {
        "twitter_users": ["Alice"],
        "money_twitter_users": ["alice", "Gap"],
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        service = XMonitorService(
            profile_path=Path(temp_dir) / "profiles.json",
            posts_path=Path(temp_dir) / "content.json",
            posts_fetcher=content,
            clock=lambda: NOW,
        )
        assert service.get_daily_posts(snapshot)["users"] == {}
        assert post_calls == []

        entry = await service.fetch_daily_posts(snapshot, username="@ALICE")
        assert post_calls == ["Alice"]
        assert [value["kind"] for value in entry["posts"]] == ["post", "reply"]
        assert entry["x_config_groups"] == [
            "twitter_users",
            "money_twitter_users",
        ]

        api = FastAPI()
        api.include_router(build_router(service, lambda: snapshot))
        transport = httpx.ASGITransport(app=api, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = list(post_calls)
            response = await client.get("/api/v1/x/posts")
            assert response.status_code == 200
            assert post_calls == before
            assert (await client.get("/api/v1/x/replies")).status_code == 404
            assert (
                await client.post("/api/v1/x/replies/fetch?username=Alice")
            ).status_code == 404
            assert (
                await client.post("/api/v1/x/posts/fetch?username=Gap")
            ).status_code == 200
            assert post_calls[-1] == "Gap"
            blocked = await client.post(
                "/api/v1/x/posts/fetch?username=Alice",
                headers={"origin": "https://evil.example"},
            )
            assert blocked.status_code == 403


async def check_query_service_and_router() -> None:
    calls: list[tuple[str, str, str]] = []
    release = asyncio.Event()

    async def query_content(
        username: str,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[str, object]:
        calls.append((username, start_at.isoformat(), end_at.isoformat()))
        if username == "Gap":
            raise RuntimeError("private upstream detail")
        if username == "Concurrent":
            await release.wait()
        return {
            "items": [
                {
                    **item("post", "401", content=f"midnight by {username}"),
                    "published": "2026-07-22 00:00",
                    "published_at": "2026-07-22T00:00:00+08:00",
                },
                {
                    **item("reply", "402", content=f"reply by {username}"),
                    "published": "2026-07-22 08:00",
                    "published_at": "2026-07-22T08:00:00+08:00",
                },
                {
                    **item("quote", "403", content=f"upper by {username}"),
                    "published": "2026-07-23 00:00",
                    "published_at": "2026-07-23T00:00:00+08:00",
                },
                {
                    **item("post", "404", content="naive"),
                    "published_at": "2026-07-22T09:00:00",
                },
            ],
            "coverage": {"status": "partial", "detail": "fixture_partial"},
            "warnings": ["fixture returned only part of the window"],
        }

    snapshot = {
        "twitter_users": ["Alice", "Gap", "Concurrent"],
        "money_twitter_users": [],
    }
    utc_half_past_midnight = datetime(2026, 7, 21, 16, 30, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as temp_dir:
        posts_path = Path(temp_dir) / "content.json"
        service = XMonitorService(
            profile_path=Path(temp_dir) / "profiles.json",
            posts_path=posts_path,
            posts_query_fetcher=query_content,
            clock=lambda: utc_half_past_midnight,
        )
        entry = await service.fetch_daily_posts(snapshot, username="Alice")
        assert entry["date"] == "2026-07-22"
        assert entry["count"] == 1
        assert calls[-1][1:] == (
            "2026-07-22T00:00:00+08:00",
            "2026-07-22T00:30:00+08:00",
        )
        cache_before = posts_path.read_bytes()

        service._clock = lambda: datetime(2026, 7, 22, 8, 0, tzinfo=BEIJING)
        day = await service.query_posts(
            snapshot,
            username="Alice",
            mode="day",
            query_date=date(2026, 7, 22),
        )
        since = await service.query_posts(
            snapshot,
            username="Alice",
            mode="since",
            query_date=date(2026, 7, 22),
        )
        assert [value["id"] for value in day["items"]] == ["401", "402"]
        assert [value["id"] for value in since["items"]] == ["401", "402"]
        assert day["end_at"] == "2026-07-23T00:00:00+08:00"
        assert since["end_at"] == "2026-07-22T08:00:00+08:00"
        assert day["timezone"] == "Asia/Shanghai"
        assert day["coverage"]["status"] == "partial"
        assert any("timezone-aware" in warning for warning in day["warnings"])
        assert posts_path.read_bytes() == cache_before

        before_invalid = len(calls)
        for invalid_date in (date(2026, 7, 23), date(2026, 6, 22)):
            try:
                await service.query_posts(
                    snapshot,
                    username="Alice",
                    mode="day",
                    query_date=invalid_date,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("invalid service query was not rejected")
        assert len(calls) == before_invalid

        concurrent_task = asyncio.create_task(
            service.query_posts(
                snapshot,
                username="Concurrent",
                mode="day",
                query_date=date(2026, 7, 22),
            )
        )
        await asyncio.sleep(0)
        alice_result = await service.query_posts(
            snapshot,
            username="Alice",
            mode="day",
            query_date=date(2026, 7, 22),
        )
        release.set()
        concurrent_result = await concurrent_task
        assert alice_result["username"] == "Alice"
        assert concurrent_result["username"] == "Concurrent"

        try:
            await service.query_posts(
                snapshot,
                username="Gap",
                mode="day",
                query_date=date(2026, 7, 22),
            )
        except RuntimeError as exc:
            assert "private upstream detail" in str(exc)
        else:
            raise AssertionError("single-user fake failure was not isolated")
        assert posts_path.read_bytes() == cache_before

        api = FastAPI()
        api.include_router(build_router(service, lambda: snapshot))
        transport = httpx.ASGITransport(app=api, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            call_count = len(calls)
            assert (await client.get("/api/v1/x/posts")).status_code == 200
            assert len(calls) == call_count
            response = await client.post(
                "/api/v1/x/posts/query",
                json={"username": "Alice", "mode": "day", "date": "2026-07-22"},
            )
            assert response.status_code == 200
            assert len(calls) == call_count + 1
            invalid = await client.post(
                "/api/v1/x/posts/query",
                json={"username": "Alice", "mode": "day", "date": "not-a-date"},
            )
            future = await client.post(
                "/api/v1/x/posts/query",
                json={"username": "Alice", "mode": "since", "date": "2026-07-23"},
            )
            assert invalid.status_code == future.status_code == 422
            assert len(calls) == call_count + 1


async def main() -> None:
    assert not (
        Path(__file__).resolve().parents[1] / "services" / "x_daily_replies.py"
    ).exists()
    await check_single_rss_content()
    await check_shanghai_window_boundaries()
    await check_collector_contract()
    await check_collector_diagnostic_code_mapping()
    await check_single_cache()
    await check_service_and_router()
    await check_query_service_and_router()
    print("test_x_monitor: all checks passed")


if __name__ == "__main__":
    asyncio.run(main())
