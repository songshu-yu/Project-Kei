"""Offline FxEmbed fallback and one-level parent-context regressions for PK-120."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

import _path_setup  # noqa: F401

from features.x_monitor.fxembed import (
    FXTWITTER_MAX_PARENT_FETCHES,
    FXTWITTER_PARENT_CONCURRENCY,
    FxEmbedFetchError,
    fetch_fxembed_posts_window,
)
from features.x_monitor.service import XMonitorService
from services.x_daily_cache import XDailyCachePersistenceError, XDailyContentRepository
from test_x_monitor_module import protected_path_tripwire


LOCAL_TZ = timezone(timedelta(hours=8))
START = datetime(2026, 7, 22, 0, 0, tzinfo=LOCAL_TZ)
END = datetime(2026, 7, 23, 0, 0, tzinfo=LOCAL_TZ)
NOW = datetime(2026, 7, 22, 12, 0, tzinfo=LOCAL_TZ)
SNAPSHOT = {"twitter_users": ["Alice"], "money_twitter_users": []}


def status(
    status_id: int,
    *,
    author: str = "Alice",
    text: str | None = None,
    created_at: str = "2026-07-22T08:00:00+08:00",
    quote: object = None,
    replying_to: object = None,
    reposted_by: object = None,
) -> dict:
    return {
        "type": "status",
        "id": str(status_id),
        "url": f"https://x.com/{author}/status/{status_id}?secret=drop",
        "text": text or f"item {status_id}",
        "created_at": created_at,
        "created_timestamp": 1784678400,
        "author": {"type": "profile", "screen_name": author},
        "quote": quote,
        "replying_to": replying_to,
        "reposted_by": reposted_by,
    }


async def fetch_with(handler, **kwargs):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await fetch_fxembed_posts_window(
            "Alice",
            start_at=START,
            end_at=END,
            client=client,
            **kwargs,
        )


def check_classification_parent_and_dedup() -> None:
    requests: list[httpx.Request] = []
    parent_id = "200000000000000001"
    timeline = [
        status(100000000000000001, text="post"),
        status(100000000000000002, text="quote", quote={"type": "tombstone"}),
        status(
            100000000000000003,
            text="Alice reply only",
            replying_to={"screen_name": "Bob", "status": parent_id},
        ),
        status(
            100000000000000004,
            reposted_by={"screen_name": "Alice", "id": "9"},
        ),
        status(
            100000000000000005,
            replying_to={"screen_name": "Bob", "status": parent_id},
            quote={"type": "status", "id": "8"},
        ),
        {"type": "thread", "id": "100000000000000006"},
        status(100000000000000001, text="duplicate must lose"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "api.fxtwitter.com"
        if request.url.path == "/2/profile/Alice/statuses":
            assert request.url.params["count"] == "30"
            assert request.url.params["with_replies"] == "1"
            assert "cursor" not in request.url.params
            assert "groupthreads" not in request.url.params
            return httpx.Response(200, json={"code": 200, "results": timeline})
        assert request.url.path == f"/2/status/{parent_id}"
        return httpx.Response(
            200,
            json={
                "code": 200,
                "status": status(
                    int(parent_id),
                    author="Bob",
                    text="direct parent only",
                ),
            },
        )

    result = asyncio.run(fetch_with(handler))
    assert [item["kind"] for item in result["items"]] == ["post", "quote", "reply"]
    assert result["items"][2]["content"] == "Alice reply only"
    assert result["items"][2]["parent_context"] == {
        "username": "@Bob",
        "content": "direct parent only",
        "published_at": "2026-07-22T08:00:00+08:00",
        "url": f"https://x.com/Bob/status/{parent_id}",
    }
    assert len(requests) == 2
    assert all("conversation" not in request.url.path for request in requests)


def check_parent_absent_mismatch_and_limits() -> None:
    parent_requests: list[str] = []

    def mismatch_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/statuses"):
            return httpx.Response(200, json={
                "code": 200,
                "results": [
                    status(
                        100000000000000010,
                        replying_to={"screen_name": "Bob", "status": "bad"},
                    ),
                    status(
                        100000000000000011,
                        replying_to={
                            "screen_name": "Bob",
                            "status": "200000000000000011",
                        },
                    ),
                    status(
                        100000000000000012,
                        replying_to={
                            "screen_name": "Bob",
                            "status": "200000000000000012",
                        },
                    ),
                ],
            })
        parent_requests.append(request.url.path)
        if request.url.path.endswith("12"):
            return httpx.Response(503, text="SECRET parent failure")
        return httpx.Response(200, json={
            "code": 200,
            "status": status(
                200000000000000011,
                author="Mallory",
                text="must not attach",
            ),
        })

    result = asyncio.run(fetch_with(mismatch_handler))
    assert len(result["items"]) == 3
    assert all("parent_context" not in item for item in result["items"])
    assert parent_requests == [
        "/2/status/200000000000000011",
        "/2/status/200000000000000012",
    ]

    active = 0
    maximum_active = 0
    total_parent_requests = 0

    async def limited_handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active, total_parent_requests
        if request.url.path.endswith("/statuses"):
            replies = [
                status(
                    110000000000000000 + index,
                    replying_to={
                        "screen_name": f"User{index}",
                        "status": str(210000000000000000 + index),
                    },
                )
                for index in range(FXTWITTER_MAX_PARENT_FETCHES + 3)
            ]
            return httpx.Response(200, json={"code": 200, "results": replies})
        total_parent_requests += 1
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        parent_id = request.url.path.rsplit("/", 1)[-1]
        index = int(parent_id) - 210000000000000000
        return httpx.Response(200, json={
            "code": 200,
            "status": status(int(parent_id), author=f"User{index}"),
        })

    limited = asyncio.run(fetch_with(limited_handler))
    assert len(limited["items"]) == FXTWITTER_MAX_PARENT_FETCHES + 3
    assert total_parent_requests == FXTWITTER_MAX_PARENT_FETCHES
    assert 1 < maximum_active <= FXTWITTER_PARENT_CONCURRENCY
    assert sum("parent_context" in item for item in limited["items"]) == FXTWITTER_MAX_PARENT_FETCHES


def check_protocol_failures_and_sanitization() -> None:
    async def expect_error(handler, code: str, *, retry_after: int | None = None):
        try:
            await fetch_with(handler)
        except FxEmbedFetchError as exc:
            assert exc.code == code
            assert exc.retry_after_seconds == retry_after
            assert "SECRET" not in str(exc)
        else:
            raise AssertionError(f"expected FxEmbedFetchError({code})")

    empty = asyncio.run(fetch_with(lambda request: httpx.Response(204)))
    assert empty["items"] == []

    asyncio.run(expect_error(
        lambda request: httpx.Response(
            429,
            headers={"Retry-After": "60", "X-Secret": "SECRET"},
            text="SECRET upstream body",
        ),
        "rate_limited",
        retry_after=60,
    ))
    asyncio.run(expect_error(
        lambda request: httpx.Response(200, json={"code": 429, "message": "SECRET"}),
        "rate_limited",
    ))
    asyncio.run(expect_error(
        lambda request: httpx.Response(403, text="SECRET access body"),
        "access_denied",
    ))
    asyncio.run(expect_error(
        lambda request: httpx.Response(503, text="SECRET upstream body"),
        "upstream_unavailable",
    ))
    asyncio.run(expect_error(
        lambda request: httpx.Response(200, content=b"not-json SECRET"),
        "invalid_json",
    ))
    asyncio.run(expect_error(
        lambda request: httpx.Response(200, json={"code": 200, "results": {}}),
        "invalid_response",
    ))
    asyncio.run(expect_error(
        lambda request: httpx.Response(200, content=b"x" * (1024 * 1024 + 1)),
        "oversize_response",
    ))

    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("SECRET timeout", request=request)

    asyncio.run(expect_error(timeout_handler, "timeout"))


def check_nitter_fallback_cache_and_tripwire() -> None:
    async def nitter_success(*args, **kwargs):
        return {
            "items": [status_item("300000000000000001", "nitter")],
            "coverage": {"status": "partial", "detail": "nitter_rss_best_effort"},
            "warnings": [],
        }

    async def nitter_failure(*args, **kwargs):
        raise RuntimeError("nitter fixture failure")

    fx_calls = 0

    async def fx_success(username, start_at, end_at, end_inclusive):
        nonlocal fx_calls
        fx_calls += 1
        return {
            "items": [status_item("300000000000000002", "fx")],
            "coverage": {"status": "partial", "detail": "fxembed_api_v2_fallback"},
            "warnings": [],
        }

    async def fx_failure(username, start_at, end_at, end_inclusive):
        nonlocal fx_calls
        fx_calls += 1
        raise FxEmbedFetchError("upstream_unavailable")

    rate_calls = 0

    async def fx_rate_limited(username, start_at, end_at, end_inclusive):
        nonlocal rate_calls
        rate_calls += 1
        raise FxEmbedFetchError("rate_limited", retry_after_seconds=60)

    with tempfile.TemporaryDirectory(prefix="kei-x-fxembed-") as temp_dir:
        root = Path(temp_dir).absolute()
        posts_path = root / "x_daily_posts.json"
        repository = XDailyContentRepository(posts_path, channel="posts")
        repository.replace_user(
            "Alice",
            [status_item("300000000000000000", "old")],
            now=NOW,
        )
        with protected_path_tripwire(root) as (hits, outside_writes):
            service = XMonitorService(
                profile_path=root / "x_profiles.json",
                posts_path=posts_path,
                fxembed_query_fetcher=fx_success,
                clock=lambda: NOW,
            )
            with patch("features.x_monitor.service.fetch_x_posts_window", nitter_success):
                result = asyncio.run(service.fetch_daily_posts(SNAPSHOT, username="Alice"))
            assert result["posts"][0]["content"] == "nitter"
            assert fx_calls == 0

            with patch("features.x_monitor.service.fetch_x_posts_window", nitter_failure):
                result = asyncio.run(service.fetch_daily_posts(SNAPSHOT, username="Alice"))
            assert result["posts"][0]["content"] == "fx"
            assert fx_calls == 1

            preserved = posts_path.read_bytes()
            failing_service = XMonitorService(
                profile_path=root / "x_profiles.json",
                posts_path=posts_path,
                fxembed_query_fetcher=fx_failure,
                clock=lambda: NOW,
            )
            with patch("features.x_monitor.service.fetch_x_posts_window", nitter_failure):
                try:
                    asyncio.run(failing_service.fetch_daily_posts(SNAPSHOT, username="Alice"))
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("double source failure did not fail")
            assert posts_path.read_bytes() == preserved

            rate_service = XMonitorService(
                profile_path=root / "x_profiles.json",
                posts_path=posts_path,
                fxembed_query_fetcher=fx_rate_limited,
                clock=lambda: NOW,
            )
            with patch("features.x_monitor.service.fetch_x_posts_window", nitter_failure):
                for _ in range(2):
                    try:
                        asyncio.run(rate_service.fetch_daily_posts(SNAPSHOT, username="Alice"))
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("rate-limited fallback did not fail closed")
            assert rate_calls == 1
            assert posts_path.read_bytes() == preserved

            service = XMonitorService(
                profile_path=root / "x_profiles.json",
                posts_path=posts_path,
                fxembed_query_fetcher=fx_success,
                clock=lambda: NOW,
            )
            with patch("features.x_monitor.service.fetch_x_posts_window", nitter_failure), patch.object(
                XDailyContentRepository,
                "_write_atomic",
                side_effect=XDailyCachePersistenceError("fixture save failure"),
            ):
                try:
                    asyncio.run(service.fetch_daily_posts(SNAPSHOT, username="Alice"))
                except XDailyCachePersistenceError:
                    pass
                else:
                    raise AssertionError("save failure did not propagate")
            assert posts_path.read_bytes() == preserved
            assert hits == []
            assert outside_writes == []


def status_item(status_id: str, content: str) -> dict:
    return {
        "upstream_id": status_id,
        "kind": "post",
        "content": content,
        "url": f"https://x.com/Alice/status/{status_id}",
        "published_at": "2026-07-22T08:00:00+08:00",
    }


def check_repository_parent_and_url_dedup() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-x-fxembed-repository-") as temp_dir:
        repository = XDailyContentRepository(
            Path(temp_dir) / "posts.json",
            channel="posts",
        )
        normalized = repository.normalize_items(
            "Alice",
            [
                {
                    "upstream_id": "400000000000000001",
                    "kind": "reply",
                    "content": "reply body",
                    "url": "https://x.com/Alice/status/400000000000000001?token=SECRET",
                    "published_at": "2026-07-22T08:00:00+08:00",
                    "reply_to_username": "Bob",
                    "parent_context": {
                        "username": "@Bob",
                        "content": "parent body",
                        "published_at": "2026-07-22T07:00:00+08:00",
                        "url": "https://x.com/Bob/status/500000000000000001?token=SECRET",
                        "thread": {"must": "drop"},
                    },
                },
                {
                    "upstream_id": "400000000000000002",
                    "kind": "post",
                    "content": "same URL must lose",
                    "url": "https://x.com/Alice/status/400000000000000001#fragment",
                    "published_at": "2026-07-22T09:00:00+08:00",
                },
            ],
            day="2026-07-22",
        )
        assert len(normalized) == 1
        assert normalized[0]["content"] == "reply body"
        assert normalized[0]["parent_context"] == {
            "username": "@Bob",
            "content": "parent body",
            "published_at": "2026-07-22T07:00:00+08:00",
            "url": "https://x.com/Bob/status/500000000000000001",
        }
        assert "SECRET" not in str(normalized)
        assert "thread" not in str(normalized)


def main() -> int:
    check_classification_parent_and_dedup()
    check_parent_absent_mismatch_and_limits()
    check_protocol_failures_and_sanitization()
    check_nitter_fallback_cache_and_tripwire()
    check_repository_parent_and_url_dedup()
    print("x_monitor FxEmbed fallback tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
