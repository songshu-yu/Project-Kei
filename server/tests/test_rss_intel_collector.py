"""PK-134 RSS/Atom checks; every HTTP exchange uses ``MockTransport``."""

from __future__ import annotations

import ast
import asyncio
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

os.environ["PROJECT_KEI_ENV_FILE"] = str(
    Path(tempfile.gettempdir()) / "project-kei-pk134-missing.env"
)

import _path_setup  # noqa: F401
import httpx

from core.intel_contracts import (
    CollectRequest,
    CoverageStatus,
    stable_item_id,
)
from features.rss_intel import RSSIntelCollector, normalize_feed_url, parse_feed
from intel.collectors.money_tips import fetch_money_tips


FIXED_TIME = datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc)
RSS_URL = "https://rss.example/main.xml"
ATOM_URL = "https://atom.example/feed.xml"

RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Builder RSS</title>
  <item><guid>rss-001</guid><title>Bootstrap income report</title>
    <link>https://articles.example/one?token=fake-secret&amp;ref=public</link>
    <description>&lt;b&gt;A practical bootstrap guide&lt;/b&gt;</description>
    <pubDate>Wed, 22 Jul 2026 05:00:00 GMT</pubDate></item>
  <item><guid>rss-001</guid><title>Bootstrap income report duplicate</title>
    <link>https://articles.example/one?token=another-secret&amp;ref=public</link>
    <description>duplicate</description>
    <pubDate>Wed, 22 Jul 2026 05:00:00 GMT</pubDate></item>
  <item><guid>rss-missing-time</guid><title>\xe7\x8b\xac\xe7\xab\x8b\xe5\xbc\x80\xe5\x8f\x91\xe5\xb7\xa5\xe5\x85\xb7</title>
    <link>https://articles.example/no-time</link><description>\xe5\xae\x9e\xe8\xb7\xb5</description></item>
  <item><guid>rss-old</guid><title>Old bootstrap item</title>
    <pubDate>Sat, 20 Jun 2026 05:00:00 GMT</pubDate></item>
  <item><guid>rss-future</guid><title>Future bootstrap item</title>
    <pubDate>Thu, 23 Jul 2026 05:00:00 GMT</pubDate></item>
  <item><guid>rss-unmatched</guid><title>Ordinary release</title>
    <description>No configured term here</description></item>
</channel></rss>"""

ATOM_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Builders</title>
  <entry><id>tag:atom.example,2026:42</id><title>Passive income notebook</title>
    <link rel="alternate" href="https://articles.example/atom" />
    <summary type="html">A &lt;strong&gt;passive income&lt;/strong&gt; field note</summary>
    <author><name>Ada</name></author><updated>2026-07-22T11:30:00+08:00</updated></entry>
</feed>"""

EMPTY_XML = b"<?xml version='1.0'?><rss version='2.0'><channel><title>Empty</title></channel></rss>"


def public_dns(_host: str):
    return ("93.184.216.34",)


def request(*, snapshot=None, refresh=False) -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 22),
        timezone="Asia/Shanghai",
        source_ids=("money",),
        refresh=refresh,
        lookback=48,
        source_config_snapshot=snapshot or {},
    )


async def check_rss_atom_filter_time_dedupe_and_stable_id() -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        payload = RSS_XML if http_request.url.host == "rss.example" else ATOM_XML
        return httpx.Response(200, content=payload, headers={"content-type": "application/xml"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        collector = RSSIntelCollector(
            [RSS_URL, ATOM_URL],
            ["bootstrap", "passive income", "独立开发"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        )
        result = await collector.collect(request())

    assert result.source_id == "money"
    assert result.coverage.status is CoverageStatus.COMPLETE
    assert result.coverage.item_count == 3
    assert len(result.items) == 3
    assert all(item.source_id == "money" and item.category == "money" for item in result.items)
    by_title = {item.title: item for item in result.items}
    rss_item = by_title["Bootstrap income report"]
    assert rss_item.stable_id == stable_item_id(
        "money", upstream_id="rss.example:rss-001"
    )
    assert rss_item.published_at == "2026-07-22T05:00:00Z"
    assert rss_item.summary == "A practical bootstrap guide"
    assert rss_item.url == "https://articles.example/one?ref=public"
    assert rss_item.metadata["matched_keywords"] == ["bootstrap"]
    assert by_title["Passive income notebook"].published_at == "2026-07-22T03:30:00Z"
    assert by_title["Passive income notebook"].author == "Ada"
    assert by_title["独立开发工具"].published_at == ""
    assert not any("Old" in item.title or "Future" in item.title for item in result.items)

    parsed = parse_feed(ATOM_XML, ATOM_URL)
    assert parsed[0].upstream_id == "tag:atom.example,2026:42"
    assert parsed[0].url == "https://articles.example/atom"


async def check_empty_partial_broken_and_timeout() -> None:
    def empty_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=EMPTY_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(empty_handler)) as client:
        empty = await RSSIntelCollector(
            [RSS_URL],
            ["bootstrap"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert empty.coverage.status is CoverageStatus.EMPTY
    assert empty.retry_after is None

    def partial_handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.host == "broken.example":
            return httpx.Response(200, content=b"<rss><broken>")
        return httpx.Response(200, content=ATOM_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(partial_handler)) as client:
        partial = await RSSIntelCollector(
            ["https://broken.example/feed", ATOM_URL],
            ["passive income"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert partial.coverage.status is CoverageStatus.PARTIAL
    assert len(partial.items) == 1
    assert partial.retry_after == "2026-07-22T06:30:00Z"
    assert partial.warnings == (
        "money: 1 configured feed(s) unavailable",
        "money: 1 configured feed(s) failed (parse_error)",
    )

    seen = []

    def timeout_handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(str(http_request.url))
        raise httpx.ReadTimeout("fake secret response body", request=http_request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as client:
        failed = await RSSIntelCollector(
            [RSS_URL],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert seen == [RSS_URL]
    assert failed.coverage.status is CoverageStatus.FAILED
    assert failed.retry_after == "2026-07-22T06:30:00Z"
    assert any("(timeout)" in warning for warning in failed.warnings)
    assert "secret" not in " ".join(failed.warnings).casefold()
    assert RSS_URL not in " ".join(failed.warnings)


async def check_redirect_and_retry_after_policy() -> None:
    seen = []

    def redirect_handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(str(http_request.url))
        if http_request.url.host == "redirect.example":
            return httpx.Response(302, headers={"location": "https://feeds.example/final.xml"})
        return httpx.Response(200, content=ATOM_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)) as client:
        redirected = await RSSIntelCollector(
            ["https://redirect.example/start.xml"],
            ["passive income"],
            allowed_redirect_hosts=["feeds.example"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert redirected.coverage.status is CoverageStatus.COMPLETE
    assert seen == [
        "https://redirect.example/start.xml",
        "https://feeds.example/final.xml",
    ]

    rejected_seen = []

    def rejected_handler(http_request: httpx.Request) -> httpx.Response:
        rejected_seen.append(str(http_request.url))
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(rejected_handler)) as client:
        rejected = await RSSIntelCollector(
            ["https://redirect.example/start.xml"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert rejected.coverage.status is CoverageStatus.FAILED
    assert rejected_seen == ["https://redirect.example/start.xml"]
    assert any("(redirect_rejected)" in warning for warning in rejected.warnings)

    def limited_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "120"}, content=b"private body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(limited_handler)) as client:
        limited = await RSSIntelCollector(
            [RSS_URL],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert limited.coverage.status is CoverageStatus.FAILED
    assert limited.retry_after == "2026-07-22T06:02:00Z"
    assert any("(rate_limited)" in warning for warning in limited.warnings)


async def check_private_dns_and_redirect_resolution_are_rejected() -> None:
    direct_seen = []

    def direct_handler(http_request: httpx.Request) -> httpx.Response:
        direct_seen.append(str(http_request.url))
        return httpx.Response(200, content=RSS_XML)

    def private_dns(_host: str):
        return ("127.0.0.1",)

    async with httpx.AsyncClient(transport=httpx.MockTransport(direct_handler)) as client:
        direct = await RSSIntelCollector(
            [RSS_URL],
            client=client,
            resolver=private_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert direct.coverage.status is CoverageStatus.FAILED
    assert direct_seen == []
    assert any("(dns_rejected)" in warning for warning in direct.warnings)

    redirect_seen = []

    def redirect_handler(http_request: httpx.Request) -> httpx.Response:
        redirect_seen.append(str(http_request.url))
        return httpx.Response(
            302,
            headers={"location": "https://redirect-private.example/final.xml"},
        )

    def rebinding_dns(host: str):
        if host == "redirect-private.example":
            return ("169.254.169.254",)
        return public_dns(host)

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)) as client:
        redirected = await RSSIntelCollector(
            [RSS_URL],
            allowed_redirect_hosts=["redirect-private.example"],
            client=client,
            resolver=rebinding_dns,
            clock=lambda: FIXED_TIME,
        ).collect(request())
    assert redirected.coverage.status is CoverageStatus.FAILED
    assert redirect_seen == [RSS_URL]
    assert any("(dns_rejected)" in warning for warning in redirected.warnings)


async def check_snapshot_cannot_add_urls_and_legacy_wrapper() -> None:
    seen = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        seen.append(str(http_request.url))
        return httpx.Response(200, content=RSS_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = RSSIntelCollector(
            [RSS_URL],
            ["bootstrap"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        )
        result = await collector.collect(
            request(snapshot={"rss_feeds": ["https://127.0.0.1/private"]})
        )
        legacy = await fetch_money_tips(
            [RSS_URL],
            ["bootstrap"],
            client=client,
            resolver=public_dns,
            clock=lambda: FIXED_TIME,
        )
    assert seen == [RSS_URL, RSS_URL]
    assert result.coverage.status is CoverageStatus.COMPLETE
    assert len(legacy) == 1
    assert legacy[0].score == 1
    assert legacy[0].published == "2026-07-22T05:00:00Z"


def check_url_policy_and_xml_safety() -> None:
    for value in (
        "http://feeds.example/feed.xml",
        "https://localhost/feed.xml",
        "https://127.0.0.1/feed.xml",
        "https://user:password@feeds.example/feed.xml",
        "https://feeds.example:8443/feed.xml",
    ):
        try:
            normalize_feed_url(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe feed URL was accepted: {value}")

    try:
        parse_feed(b"<!DOCTYPE rss [<!ENTITY x 'fake'>]><rss/>", RSS_URL)
    except ValueError as exc:
        assert "unsafe XML" in str(exc)
    else:
        raise AssertionError("unsafe XML declaration was accepted")


def check_forbidden_dependency_edges() -> None:
    server_root = Path(__file__).resolve().parents[1]
    paths = [
        *sorted((server_root / "features" / "rss_intel").glob("*.py")),
        server_root / "intel" / "collectors" / "money_tips.py",
    ]
    forbidden = {
        "features.daily_briefing.collector_gateway",
        "features.daily_briefing.service",
        "features.daily_briefing.repository",
        "features.daily_briefing.router",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not (forbidden & imported), (path.name, forbidden & imported)
        assert "intel.intel_config" not in imported, path.name
        assert not any(name.startswith("features.x_monitor") for name in imported), path.name


async def main() -> int:
    await check_rss_atom_filter_time_dedupe_and_stable_id()
    await check_empty_partial_broken_and_timeout()
    await check_redirect_and_retry_after_policy()
    await check_private_dns_and_redirect_resolution_are_rejected()
    await check_snapshot_cannot_add_urls_and_legacy_wrapper()
    check_url_policy_and_xml_safety()
    check_forbidden_dependency_edges()
    print("PK-134 RSS intel collector tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
