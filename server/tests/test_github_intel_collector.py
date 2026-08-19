"""Isolated PK-132 GitHub Collector checks using only MockTransport."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone

import _path_setup  # noqa: F401
import httpx

from core.intel_contracts import CacheStatus, CollectRequest, CoverageStatus
from features.github_intel import GitHubCollector, GitHubCollectorSettings
from intel.collectors.github import GitHubCollector as LegacyModuleGitHubCollector


NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


def _settings(**overrides) -> GitHubCollectorSettings:
    values = {
        "per_page": 2,
        "max_pages": 3,
        "timeout_seconds": 2.0,
        "trust_env": False,
        "use_environment_auth": False,
    }
    values.update(overrides)
    return GitHubCollectorSettings(**values)


def _request(*, users=(), repos=(), refresh=False) -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=("github",),
        refresh=refresh,
        lookback=24,
        source_config_snapshot={
            "github_users": list(users),
            "github_repos": list(repos),
        },
    )


def _event(event_id: str, published: str, *, event_type: str = "WatchEvent") -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "actor": {"login": "sample-user"},
        "repo": {"name": "sample-org/sample-repo"},
        "created_at": published,
        "payload": {"commits": [{"message": "bounded public summary"}]},
    }


def _release(release_id: int, published: str) -> dict:
    return {
        "id": release_id,
        "name": "v1.2.3",
        "tag_name": "v1.2.3",
        "body": "Public release notes",
        "html_url": "https://github.com/sample-org/sample-repo/releases/tag/v1.2.3",
        "published_at": published,
        "draft": False,
        "prerelease": False,
    }


async def check_events_releases_pagination_and_window() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "api.github.com"
        assert "authorization" not in request.headers
        page = int(request.url.params["page"])
        if request.url.path == "/users/sample-user/events/public" and page == 1:
            return httpx.Response(
                200,
                json=[_event("event-1", "2026-07-22T07:30:00Z")],
                headers={"Link": '<https://untrusted.invalid/next>; rel="next"'},
            )
        if request.url.path == "/users/sample-user/events/public" and page == 2:
            return httpx.Response(
                200,
                json=[_event("old-event", "2026-07-20T00:00:00Z")],
                headers={"Link": '<https://untrusted.invalid/more>; rel="next"'},
            )
        if request.url.path == "/repos/sample-org/sample-repo/releases" and page == 1:
            return httpx.Response(200, json=[_release(42, "2026-07-22T06:00:00Z")])
        raise AssertionError(f"unexpected request: {request.url}")

    collector = GitHubCollector(
        settings=_settings(),
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    )
    result = await collector.collect(
        _request(users=("sample-user",), repos=("sample-org/sample-repo",), refresh=True)
    )

    assert result.coverage.status is CoverageStatus.COMPLETE
    assert result.cache_status is CacheStatus.REFRESHED
    assert len(result.items) == 2
    assert {item.metadata["record_type"] for item in result.items} == {"user_event", "release"}
    assert {item.stable_id for item in result.items} == {
        "github:0fe25ef0425a87abef887a38810d8062",
        "github:164f2ce289a6fadc847d13bfe120faf4",
    }
    assert all(item.source_id == "github" and item.category == "development" for item in result.items)
    assert [request.url.host for request in requests] == ["api.github.com"] * 3
    assert [int(request.url.params["page"]) for request in requests] == [1, 2, 1]
    serialized = json.dumps(result.to_dict(), ensure_ascii=False).casefold()
    assert "authorization" not in serialized
    assert "untrusted.invalid" not in serialized


async def check_http_failures_are_isolated_and_redacted() -> None:
    cases = (
        (401, "authentication was rejected"),
        (403, "request was rejected"),
        (404, "user target was not found"),
    )
    for status_code, expected in cases:
        def handler(_request: httpx.Request, code=status_code) -> httpx.Response:
            return httpx.Response(code, text="upstream diagnostic must remain private")

        result = await GitHubCollector(
            settings=_settings(),
            transport=httpx.MockTransport(handler),
            clock=lambda: NOW,
        ).collect(_request(users=("sample-user",)))
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        assert result.coverage.status is CoverageStatus.FAILED
        assert expected in payload
        assert "upstream diagnostic" not in payload

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private transport detail", request=request)

    timed_out = await GitHubCollector(
        settings=_settings(),
        transport=httpx.MockTransport(timeout_handler),
        clock=lambda: NOW,
    ).collect(_request(users=("sample-user",)))
    payload = json.dumps(timed_out.to_dict(), ensure_ascii=False)
    assert timed_out.coverage.status is CoverageStatus.FAILED
    assert timed_out.retry_after == "2026-07-22T08:30:00Z"
    assert "private transport detail" not in payload

    def isolated_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/users/"):
            return httpx.Response(404, text="private missing-target detail")
        return httpx.Response(200, json=[_release(43, "2026-07-22T06:30:00Z")])

    isolated = await GitHubCollector(
        settings=_settings(),
        transport=httpx.MockTransport(isolated_handler),
        clock=lambda: NOW,
    ).collect(_request(users=("sample-user",), repos=("sample-org/sample-repo",)))
    assert isolated.coverage.status is CoverageStatus.PARTIAL
    assert len(isolated.items) == 1
    assert isolated.items[0].metadata["record_type"] == "release"


async def check_rate_limit_stops_collection_and_sets_retry_after() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(
            429,
            text="rate-limit upstream body must remain private",
            headers={"Retry-After": "120", "X-RateLimit-Remaining": "0"},
        )

    result = await GitHubCollector(
        settings=_settings(),
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    ).collect(_request(users=("sample-user",), repos=("sample-org/sample-repo",)))
    payload = json.dumps(result.to_dict(), ensure_ascii=False)
    assert requested_paths == ["/users/sample-user/events/public"]
    assert result.coverage.status is CoverageStatus.FAILED
    assert result.retry_after == "2026-07-22T08:02:00Z"
    assert result.coverage.retry_after == result.retry_after
    assert "rate limit was reached" in payload
    assert "upstream body" not in payload


async def check_partial_result_and_pagination_cap() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=[_event(f"event-{calls}", f"2026-07-22T0{8 - calls}:00:00Z")],
            headers={"Link": '<https://api.github.com/ignored>; rel="next"'},
        )

    result = await GitHubCollector(
        settings=_settings(max_pages=2),
        transport=httpx.MockTransport(handler),
        clock=lambda: NOW,
    ).collect(_request(users=("sample-user",)))
    assert calls == 2
    assert result.coverage.status is CoverageStatus.PARTIAL
    assert len(result.items) == 2
    assert result.warnings == ("github: pagination limit was reached",)


async def check_missing_and_invalid_configuration() -> None:
    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("not-configured collection must not issue HTTP")

    collector = GitHubCollector(
        settings=_settings(),
        transport=httpx.MockTransport(unexpected),
        clock=lambda: NOW,
    )
    missing = await collector.collect(_request())
    assert missing.coverage.status is CoverageStatus.NOT_CONFIGURED
    assert missing.warnings == ()

    invalid = await collector.collect(_request(users=("not/a/user",), repos=("missing-slash",)))
    assert invalid.coverage.status is CoverageStatus.NOT_CONFIGURED
    assert invalid.warnings == ("github: invalid targets were ignored",)


async def main() -> int:
    assert LegacyModuleGitHubCollector is GitHubCollector
    await check_events_releases_pagination_and_window()
    await check_http_failures_are_isolated_and_redacted()
    await check_rate_limit_stops_collection_and_sets_retry_after()
    await check_partial_result_and_pagination_cap()
    await check_missing_and_invalid_configuration()
    print("github intelligence collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
