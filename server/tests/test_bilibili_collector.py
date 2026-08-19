"""PK-130 isolated tests: every upstream request uses httpx.MockTransport."""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx

import _path_setup  # noqa: F401

from features.bilibili.client import (
    DYNAMIC_PATH,
    NAV_PATH,
    PROFILE_PATH,
    BilibiliClientError,
    BilibiliPublicClient,
)
from features.daily_briefing.models import CollectRequest, CoverageStatus
from intel.collectors.bilibili import BilibiliCollector, fetch_bilibili
from services.bilibili_profile_cache import resolve_bilibili_profiles


FIXED_NOW = datetime(2026, 7, 22, 4, 0, tzinfo=timezone.utc)
PUBLISHED_TS = int(datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc).timestamp())
WBI_IMG_KEY = "a" * 32
WBI_SUB_KEY = "b" * 32


def _query(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.url.query.decode("ascii"))


def _dynamic_payload(uid: int) -> dict:
    return {
        "code": 0,
        "data": {
            "items": [
                {
                    "id_str": f"dynamic-{uid}",
                    "type": "DYNAMIC_TYPE_AV",
                    "modules": {
                        "module_author": {
                            "mid": uid,
                            "name": f"UP-{uid}",
                            "pub_ts": PUBLISHED_TS,
                        },
                        "module_dynamic": {
                            "desc": {"text": "补充说明"},
                            "major": {
                                "type": "MAJOR_TYPE_ARCHIVE",
                                "archive": {
                                    "bvid": "BV1TESTONLY",
                                    "title": "新动态标题",
                                    "desc": "动态摘要",
                                },
                            },
                        },
                    },
                }
            ]
        },
    }


def _nav_payload() -> dict:
    return {
        "code": -101,
        "data": {
            "wbi_img": {
                "img_url": f"https://i.example.test/{WBI_IMG_KEY}.png",
                "sub_url": f"https://i.example.test/{WBI_SUB_KEY}.png",
            }
        },
    }


async def check_profile_and_dynamic_paths_are_independent() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert "cookie" not in request.headers
        if request.url.path == NAV_PATH:
            return httpx.Response(200, json=_nav_payload())
        if request.url.path == PROFILE_PATH:
            query = _query(request)
            uid = int(query["mid"][0])
            assert query["wts"] == [str(int(FIXED_NOW.timestamp()))]
            assert len(query["w_rid"][0]) == 32
            return httpx.Response(200, json={
                "code": 0,
                "data": {"mid": uid, "name": f"UP-{uid}", "face": "//i.example.test/avatar.jpg"},
            })
        if request.url.path == DYNAMIC_PATH:
            uid = int(_query(request)["host_mid"][0])
            return httpx.Response(200, json=_dynamic_payload(uid))
        raise AssertionError(f"unexpected path: {request.url.path}")

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(handler),
        request_delay=0,
        retry_delay=0,
        wall_clock=lambda: FIXED_NOW.timestamp(),
    ) as client:
        profile = await client.fetch_profile(100)
        assert profile == {
            "uid": 100,
            "name": "UP-100",
            "avatar_url": "https://i.example.test/avatar.jpg",
        }
        assert paths == [NAV_PATH, PROFILE_PATH]

        dynamics = await client.fetch_space_dynamics(100)
        assert len(dynamics) == 1
        assert paths == [NAV_PATH, PROFILE_PATH, DYNAMIC_PATH]
        assert not any("video" in path or "arc/search" in path for path in paths)


async def check_retry_is_bounded_and_requests_are_throttled() -> None:
    attempts = 0

    def blocked_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"code": -352, "message": "fictional secret body"})

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(blocked_handler),
        request_delay=0,
        retry_delay=0,
        max_attempts=99,
    ) as client:
        try:
            await client.fetch_space_dynamics(101)
        except BilibiliClientError as exc:
            assert exc.code == "anti_bot"
            assert "fictional" not in str(exc)
        else:
            raise AssertionError("anti-bot response should fail")
    assert attempts == 2

    fake_time = [10.0]
    slept: list[float] = []

    def monotonic() -> float:
        return fake_time[0]

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)
        fake_time[0] += delay

    def profile_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == NAV_PATH:
            return httpx.Response(200, json=_nav_payload())
        uid = int(_query(request)["mid"][0])
        return httpx.Response(200, json={
            "code": 0,
            "data": {"name": f"UP-{uid}", "face": ""},
        })

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(profile_handler),
        request_delay=2.5,
        retry_delay=0,
        max_attempts=1,
        sleep=fake_sleep,
        monotonic=monotonic,
    ) as client:
        await client.fetch_profile(1)
        await client.fetch_profile(2)
    assert slept == [2.5, 2.5]


async def check_active_cookie_provider_hot_switches_without_restart() -> None:
    current = {"SESSDATA": "fictional-first-session"}
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie", ""))
        if request.url.path == NAV_PATH:
            return httpx.Response(200, json=_nav_payload())
        uid = int(_query(request)["mid"][0])
        return httpx.Response(200, json={
            "code": 0,
            "data": {"name": f"UP-{uid}", "face": ""},
        })

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(handler),
        cookies_provider=lambda: dict(current),
        request_delay=0,
        retry_delay=0,
    ) as client:
        await client.fetch_profile(1)
        current["SESSDATA"] = "fictional-second-session"
        await client.fetch_profile(2)
    assert "fictional-first-session" in seen[0]
    assert "fictional-first-session" in seen[1]
    assert "fictional-second-session" in seen[2]
    assert "fictional-first-session" not in seen[2]


def _request(uids: list[int], *, refresh: bool = False) -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=("bilibili",),
        refresh=refresh,
        lookback=24,
        source_config_snapshot={"bilibili_uids": uids},
    )


async def check_collector_contract_and_legacy_adapter() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.url.path == DYNAMIC_PATH
        uid = int(_query(request)["host_mid"][0])
        return httpx.Response(200, json=_dynamic_payload(uid))

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(handler), request_delay=0, retry_delay=0
    ) as client:
        collector = BilibiliCollector(client=client, now=lambda: FIXED_NOW)
        result = await collector.collect(_request([100]))
        assert result.source_id == "bilibili"
        assert result.coverage.status == CoverageStatus.COMPLETE
        assert result.coverage.item_count == 1
        assert result.retry_after is None
        item = result.items[0]
        assert item.stable_id.startswith("bilibili:")
        assert item.title == "新动态标题"
        assert item.summary == "动态摘要"
        assert item.author == "UP-100"
        assert item.url == "https://www.bilibili.com/video/BV1TESTONLY"
        assert item.published_at == "2026-07-22T03:00:00Z"
        assert item.metadata == {
            "uid": 100,
            "dynamic_id": "dynamic-100",
            "dynamic_type": "DYNAMIC_TYPE_AV",
        }
        assert paths == [DYNAMIC_PATH]

        legacy = await fetch_bilibili(
            [100], max_per_user=3, since_hours=24, client=client, now=FIXED_NOW
        )
        assert len(legacy) == 1
        assert legacy[0].username == "UP-100"
        assert legacy[0].dynamic_type == "DYNAMIC_TYPE_AV"
        assert paths == [DYNAMIC_PATH, DYNAMIC_PATH]


async def check_not_configured_and_failure_cooldown() -> None:
    requests = 0

    def should_not_run(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(500)

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(should_not_run), request_delay=0, retry_delay=0
    ) as client:
        collector = BilibiliCollector(client=client, now=lambda: FIXED_NOW)
        result = await collector.collect(_request([]))
        assert result.coverage.status == CoverageStatus.NOT_CONFIGURED
        assert requests == 0

    blocked_requests = 0

    def blocked(_request: httpx.Request) -> httpx.Response:
        nonlocal blocked_requests
        blocked_requests += 1
        return httpx.Response(200, json={
            "code": -352,
            "message": "Authorization=fictional-credential",
        })

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(blocked), request_delay=0, retry_delay=0
    ) as client:
        collector = BilibiliCollector(client=client, now=lambda: FIXED_NOW)
        first = await collector.collect(_request([200], refresh=True))
        assert first.coverage.status == CoverageStatus.FAILED
        assert first.retry_after == "2026-07-22T10:00:00Z"
        assert blocked_requests == 2
        assert any("(anti_bot)" in warning for warning in first.warnings)
        assert "fictional-credential" not in str(first.to_dict())

        second = await collector.collect(_request([200], refresh=True))
        assert second.coverage.status == CoverageStatus.FAILED
        assert second.retry_after == first.retry_after
        assert "cooldown active" in second.warnings[0]
        assert any("(anti_bot)" in warning for warning in second.warnings)
        assert blocked_requests == 2


async def check_single_target_failure_isolated_as_partial() -> None:
    requests: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        uid = int(_query(request)["host_mid"][0])
        requests.append(uid)
        if uid == 401:
            return httpx.Response(200, json=_dynamic_payload(uid))
        return httpx.Response(503, text="Authorization=fictional-response")

    async with BilibiliPublicClient(
        transport=httpx.MockTransport(handler), request_delay=0, retry_delay=0
    ) as client:
        collector = BilibiliCollector(client=client, now=lambda: FIXED_NOW)
        result = await collector.collect(_request([401, 402]))
        assert result.coverage.status == CoverageStatus.PARTIAL
        assert result.coverage.item_count == 1
        assert len(result.items) == 1
        assert result.items[0].metadata["uid"] == 401
        assert result.retry_after == "2026-07-22T10:00:00Z"
        assert requests == [401, 402, 402]
        assert any("(upstream_unavailable)" in warning for warning in result.warnings)
        assert "401" not in str(result.warnings)
        assert "402" not in str(result.warnings)
        assert "fictional-response" not in str(result.to_dict())


async def check_profile_cache_uses_mock_http_and_honors_failure_cooldown() -> None:
    profile_calls: dict[int, int] = {}
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == NAV_PATH:
            return httpx.Response(200, json=_nav_payload())
        assert request.url.path == PROFILE_PATH
        uid = int(_query(request)["mid"][0])
        profile_calls[uid] = profile_calls.get(uid, 0) + 1
        if uid == 300:
            return httpx.Response(200, json={
                "code": 0,
                "data": {"name": "缓存用户", "face": "//i.example.test/300.jpg"},
            })
        return httpx.Response(200, json={"code": -352, "message": "Cookie=fake-value"})

    with tempfile.TemporaryDirectory(prefix="kei-pk130-") as temp_dir:
        cache_path = Path(temp_dir) / "bilibili_profiles.json"
        async with BilibiliPublicClient(
            transport=httpx.MockTransport(handler), request_delay=0, retry_delay=0
        ) as client:
            first = await resolve_bilibili_profiles(
                [300], path=cache_path, fetcher=client.fetch_profile, now=FIXED_NOW
            )
            assert first["profiles"]["300"]["name"] == "缓存用户"
            assert profile_calls[300] == 1

            await resolve_bilibili_profiles(
                [300], path=cache_path, fetcher=client.fetch_profile, now=FIXED_NOW
            )
            assert profile_calls[300] == 1

            await resolve_bilibili_profiles(
                [300], refresh=True, path=cache_path, fetcher=client.fetch_profile, now=FIXED_NOW
            )
            assert profile_calls[300] == 2

            failed = await resolve_bilibili_profiles(
                [301], path=cache_path, fetcher=client.fetch_profile, now=FIXED_NOW
            )
            assert failed["profiles"]["301"]["status"] == "error"
            assert profile_calls[301] == 2

            await resolve_bilibili_profiles(
                [301], refresh=True, path=cache_path, fetcher=client.fetch_profile, now=FIXED_NOW
            )
            assert profile_calls[301] == 2

        assert paths and set(paths) == {NAV_PATH, PROFILE_PATH}
        assert not list(cache_path.parent.glob("*.tmp"))
        assert "fake-value" not in cache_path.read_text(encoding="utf-8")

        secret_cache_path = Path(temp_dir) / "secret_profiles.json"

        async def secret_profile(uid: int) -> dict:
            return {
                "uid": uid,
                "name": "Authorization=Bearer fictional-profile-secret Public Name",
                "avatar_url": "https://i.example.test/avatar.jpg?token=fictional-query-secret&view=public",
            }

        sanitized = await resolve_bilibili_profiles(
            [302], path=secret_cache_path, fetcher=secret_profile, now=FIXED_NOW
        )
        combined = json.dumps(sanitized, ensure_ascii=False) + secret_cache_path.read_text(encoding="utf-8")
        assert "fictional-profile-secret" not in combined
        assert "fictional-query-secret" not in combined
        assert "view=public" in combined


async def main() -> None:
    await check_profile_and_dynamic_paths_are_independent()
    await check_retry_is_bounded_and_requests_are_throttled()
    await check_active_cookie_provider_hot_switches_without_restart()
    await check_collector_contract_and_legacy_adapter()
    await check_not_configured_and_failure_cooldown()
    await check_single_target_failure_isolated_as_partial()
    await check_profile_cache_uses_mock_http_and_honors_failure_cooldown()
    print("bilibili collector tests passed")


if __name__ == "__main__":
    asyncio.run(main())
