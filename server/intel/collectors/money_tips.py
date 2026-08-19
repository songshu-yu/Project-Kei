"""Legacy money-tip compatibility wrapper over the PK-134 RSS Collector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

import httpx

from core.intel_contracts import CollectRequest, get_timezone
from features.rss_intel import RSSIntelCollector
from features.rss_intel.http_client import Resolver

@dataclass
class MoneyTip:
    source: str
    title: str
    url: str
    summary: str
    score: int = 0
    published: str = ""


async def fetch_money_tips(
    rss_feeds: Iterable[object],
    keywords: Iterable[object],
    max_per_feed: int = 30,
    max_results: int = 15,
    *,
    client: Optional[httpx.AsyncClient] = None,
    resolver: Optional[Resolver] = None,
    clock=None,
    timezone_name: str = "Asia/Shanghai",
):
    """Preserve the legacy return type while using the frozen Collector models."""
    now_provider = clock or (lambda: datetime.now(timezone.utc))
    now = now_provider()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("money tip clock must return an aware datetime")
    collector = RSSIntelCollector(
        rss_feeds,
        keywords,
        client=client,
        resolver=resolver,
        clock=lambda: now,
        max_entries_per_feed=max_per_feed,
        max_results=max_results,
    )
    request = CollectRequest(
        local_date=now.astimezone(get_timezone(timezone_name)).date(),
        timezone=timezone_name,
        source_ids=("money",),
        lookback=720,
        source_config_snapshot={},
    )
    result = await collector.collect(request)
    return [
        MoneyTip(
            source=(
                str(item.metadata.get("feed_title", ""))
                .replace(" RSS", "")
                .replace(" Feed", "")[:30]
            ),
            title=item.title,
            url=item.url,
            summary=item.summary[:150],
            score=int(item.metadata.get("keyword_score", 0)),
            published=item.published_at,
        )
        for item in result.items
    ]


__all__ = ["MoneyTip", "RSSIntelCollector", "fetch_money_tips"]
