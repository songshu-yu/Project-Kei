"""Single per-user, per-day X content cache for the local dashboard."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Sequence

from services.x_daily_cache import (
    SCHEMA_VERSION,
    XDailyContentRepository,
    business_local_now,
    normalize_x_handle,
)
from intel.collectors.twitter import fetch_x_daily_posts
from intel.intel_config import NITTER_INSTANCES


SERVER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = SERVER_ROOT / "data" / "x_daily_posts.json"
PostsFetcher = Callable[[str], Awaitable[list]]


def prepare_x_daily_posts_cache(
    path: str | Path = DEFAULT_PATH,
    *,
    now: datetime | None = None,
) -> dict:
    """Read today's posts cache without creating or cleaning files."""
    return XDailyContentRepository(path, channel="posts").read_today(now=now)


def get_x_daily_posts_cache(
    usernames: list[object],
    path: str | Path = DEFAULT_PATH,
    *,
    now: datetime | None = None,
    groups_by_username: Mapping[str, Sequence[str]] | None = None,
) -> dict:
    return XDailyContentRepository(path, channel="posts").read_selected(
        usernames,
        now=now,
        groups_by_username=groups_by_username,
    )


async def fetch_and_cache_x_daily_posts(
    username: object,
    path: str | Path = DEFAULT_PATH,
    *,
    fetcher: PostsFetcher | None = None,
    now: datetime | None = None,
    x_config_groups: Sequence[str] = (),
) -> dict:
    local_now = business_local_now(now)

    async def default_fetcher(handle: str) -> list:
        return await fetch_x_daily_posts(
            handle,
            NITTER_INSTANCES,
            target_date=local_now.date(),
            local_tz=local_now.tzinfo,
        )

    handle = normalize_x_handle(username)
    items = await (fetcher or default_fetcher)(handle)
    return XDailyContentRepository(path, channel="posts").replace_user(
        handle,
        items,
        now=local_now,
        x_config_groups=x_config_groups,
    )


__all__ = [
    "DEFAULT_PATH",
    "PostsFetcher",
    "SCHEMA_VERSION",
    "fetch_and_cache_x_daily_posts",
    "get_x_daily_posts_cache",
    "prepare_x_daily_posts_cache",
]
