"""Public PK-120 use cases over the isolated profile and daily-content caches."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Sequence

from services.x_daily_posts import (
    DEFAULT_PATH as DEFAULT_POSTS_PATH,
    PostsFetcher,
    get_x_daily_posts_cache,
)
from services.x_daily_cache import (
    BUSINESS_TIMEZONE,
    XDailyContentRepository,
    business_local_now,
)
from services.x_profile_cache import (
    DEFAULT_PATH as DEFAULT_PROFILES_PATH,
    ProfileFetcher,
    get_x_profiles,
    resolve_x_profiles,
)
from core.intel_contracts import localize, sanitize_external_text
from intel.collectors.twitter import fetch_x_posts_window
from .fxembed import FxEmbedFetchError
from intel.intel_config import NITTER_INSTANCES

from .models import XPostQueryMode, XTarget, classify_x_targets, normalize_handle


Clock = Callable[[], datetime]
PostsQueryFetcher = Callable[[str, datetime, datetime], Awaitable[object]]
FxEmbedQueryFetcher = Callable[[str, datetime, datetime, bool], Awaitable[object]]
MAX_QUERY_DAYS = 30


@dataclass(frozen=True)
class XPostQueryWindow:
    mode: XPostQueryMode
    query_date: date
    timezone: str
    start_at: datetime
    end_at: datetime


def build_x_post_query_window(
    query_date: date,
    mode: XPostQueryMode,
    *,
    now: datetime,
) -> XPostQueryWindow:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("X post query clock must return an aware datetime")
    if mode not in {"day", "since"}:
        raise ValueError("X post query mode must be day or since")
    local_now = business_local_now(now)
    if query_date > local_now.date():
        raise ValueError("X post query date cannot be in the future")
    earliest = local_now.date() - timedelta(days=MAX_QUERY_DAYS - 1)
    if query_date < earliest:
        raise ValueError(
            f"X post query date exceeds the {MAX_QUERY_DAYS}-calendar-day limit"
        )
    start_at = localize(datetime.combine(query_date, time.min), BUSINESS_TIMEZONE)
    if mode == "day":
        end_at = localize(
            datetime.combine(query_date + timedelta(days=1), time.min),
            BUSINESS_TIMEZONE,
        )
    else:
        end_at = local_now
    return XPostQueryWindow(
        mode=mode,
        query_date=query_date,
        timezone=BUSINESS_TIMEZONE,
        start_at=start_at,
        end_at=end_at,
    )


def _aware_item_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


class XMonitorService:
    """Operate only on caller-supplied, non-secret source configuration snapshots."""

    def __init__(
        self,
        *,
        profile_path: str | Path = DEFAULT_PROFILES_PATH,
        posts_path: str | Path = DEFAULT_POSTS_PATH,
        profile_fetcher: ProfileFetcher | None = None,
        posts_fetcher: PostsFetcher | None = None,
        posts_query_fetcher: PostsQueryFetcher | None = None,
        fxembed_query_fetcher: FxEmbedQueryFetcher | None = None,
        nitter_instances: Sequence[object] = NITTER_INSTANCES,
        clock: Clock | None = None,
    ) -> None:
        self._profile_path = Path(profile_path)
        self._posts_path = Path(posts_path)
        self._profile_fetcher = profile_fetcher
        self._posts_fetcher = posts_fetcher
        self._posts_query_fetcher = posts_query_fetcher
        self._fxembed_query_fetcher = fxembed_query_fetcher
        self._nitter_instances = tuple(nitter_instances)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._fxembed_cooldown_until: datetime | None = None

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("XMonitorService clock must return an aware datetime")
        return value

    @staticmethod
    def _targets(snapshot: Mapping[str, object], username: object | None = None) -> tuple[XTarget, ...]:
        targets = classify_x_targets(snapshot)
        if username is None:
            return targets
        selected_key = normalize_handle(username).casefold()
        selected = tuple(target for target in targets if target.key == selected_key)
        if not selected:
            raise ValueError("X username is not in the current source list")
        return selected

    @staticmethod
    def _groups(targets: tuple[XTarget, ...]) -> dict[str, tuple[str, ...]]:
        return {target.key: target.config_groups for target in targets}

    async def resolve_profiles(
        self,
        source_config_snapshot: Mapping[str, object],
        *,
        username: object | None = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        targets = self._targets(source_config_snapshot, username)
        return await resolve_x_profiles(
            [target.username for target in targets],
            refresh=refresh,
            path=self._profile_path,
            fetcher=self._profile_fetcher,
            nitter_instances=self._nitter_instances,
            now=self._now().astimezone(timezone.utc),
            groups_by_username=self._groups(targets),
        )

    def read_profiles(
        self,
        source_config_snapshot: Mapping[str, object],
        *,
        username: object | None = None,
    ) -> dict[str, object]:
        targets = self._targets(source_config_snapshot, username)
        return get_x_profiles(
            [target.username for target in targets],
            path=self._profile_path,
            groups_by_username=self._groups(targets),
        )

    def get_daily_posts(
        self,
        source_config_snapshot: Mapping[str, object],
    ) -> dict[str, object]:
        targets = self._targets(source_config_snapshot)
        return get_x_daily_posts_cache(
            [target.username for target in targets],
            self._posts_path,
            now=self._now(),
            groups_by_username=self._groups(targets),
        )

    async def fetch_daily_posts(
        self,
        source_config_snapshot: Mapping[str, object],
        *,
        username: object,
    ) -> dict[str, object]:
        target = self._targets(source_config_snapshot, username)[0]
        now = self._now()
        local_now = business_local_now(now)
        window = build_x_post_query_window(
            local_now.date(),
            "since",
            now=now,
        )
        result = await self._fetch_window(target.username, window)
        return XDailyContentRepository(
            self._posts_path,
            channel="posts",
        ).replace_user(
            target.username,
            result["items"],
            now=local_now,
            x_config_groups=target.config_groups,
        )

    async def query_posts(
        self,
        source_config_snapshot: Mapping[str, object],
        *,
        username: object,
        mode: XPostQueryMode,
        query_date: date,
    ) -> dict[str, object]:
        target = self._targets(source_config_snapshot, username)[0]
        now = self._now()
        window = build_x_post_query_window(query_date, mode, now=now)
        result = await self._fetch_window(target.username, window)
        return {
            "username": target.username,
            "mode": window.mode,
            "timezone": window.timezone,
            "start_at": window.start_at.isoformat(timespec="seconds"),
            "end_at": window.end_at.isoformat(timespec="seconds"),
            "count": len(result["items"]),
            "items": result["items"],
            "fetched_at": business_local_now(now).isoformat(timespec="seconds"),
            "coverage": result["coverage"],
            "warnings": result["warnings"],
        }

    async def _fetch_window(
        self,
        username: str,
        window: XPostQueryWindow,
    ) -> dict[str, object]:
        try:
            if self._posts_query_fetcher is not None:
                raw_result = await self._posts_query_fetcher(
                    username,
                    window.start_at,
                    window.end_at,
                )
            elif self._posts_fetcher is not None:
                raw_result = await self._posts_fetcher(username)
            else:
                raw_result = await fetch_x_posts_window(
                    username,
                    self._nitter_instances,
                    start_at=window.start_at,
                    end_at=window.end_at,
                    end_inclusive=window.mode == "since",
                )
        except (RuntimeError, ValueError):
            if self._fxembed_query_fetcher is None:
                raise
            fallback_now = self._now().astimezone(timezone.utc)
            if (
                self._fxembed_cooldown_until is not None
                and fallback_now < self._fxembed_cooldown_until
            ):
                raise RuntimeError("configured X sources are unavailable")
            try:
                raw_result = await self._fxembed_query_fetcher(
                    username,
                    window.start_at,
                    window.end_at,
                    window.mode == "since",
                )
            except FxEmbedFetchError as fx_error:
                if (
                    fx_error.code == "rate_limited"
                    and fx_error.retry_after_seconds is not None
                ):
                    self._fxembed_cooldown_until = fallback_now + timedelta(
                        seconds=fx_error.retry_after_seconds
                    )
                raise RuntimeError("configured X sources are unavailable") from fx_error
            except (RuntimeError, ValueError) as fx_error:
                raise RuntimeError("configured X sources are unavailable") from fx_error
        if isinstance(raw_result, Mapping):
            raw_items = raw_result.get("items", [])
            raw_warnings = raw_result.get("warnings", [])
            raw_coverage = raw_result.get("coverage", {})
        else:
            raw_items = raw_result
            raw_warnings = []
            raw_coverage = {}
        repository = XDailyContentRepository(self._posts_path, channel="posts")
        normalized = repository.normalize_items(
            username,
            raw_items,
            day=window.query_date.isoformat(),
        )
        items: list[dict[str, object]] = []
        skipped_time = 0
        for item in normalized:
            published_at = _aware_item_time(item.get("published_at"))
            if published_at is None:
                skipped_time += 1
                continue
            in_window = (
                window.start_at <= published_at <= window.end_at
                if window.mode == "since"
                else window.start_at <= published_at < window.end_at
            )
            if in_window:
                items.append(item)
        warnings = [
            sanitize_external_text(value, limit=300)
            for value in raw_warnings
            if str(value).strip()
        ][:10] if isinstance(raw_warnings, Sequence) and not isinstance(raw_warnings, (str, bytes)) else []
        raw_detail = (
            raw_coverage.get("detail")
            if isinstance(raw_coverage, Mapping)
            else ""
        )
        default_warning = (
            "FxEmbed exposes one bounded timeline page; window coverage is not guaranteed."
            if raw_detail == "fxembed_api_v2_fallback"
            else "Nitter/RSS only exposes a limited upstream snapshot; window coverage is not guaranteed."
        )
        if default_warning not in warnings:
            warnings.insert(0, default_warning)
        if skipped_time:
            warnings.append(
                f"Skipped {skipped_time} item(s) without a valid timezone-aware publication time."
            )
        coverage = {
            "status": "partial",
            "detail": sanitize_external_text(
                raw_detail or "nitter_rss_best_effort",
                limit=160,
            ),
        }
        return {
            "items": items,
            "coverage": coverage,
            "warnings": warnings[:10],
        }


__all__ = [
    "BUSINESS_TIMEZONE",
    "MAX_QUERY_DAYS",
    "FxEmbedQueryFetcher",
    "PostsQueryFetcher",
    "XMonitorService",
    "XPostQueryWindow",
    "build_x_post_query_window",
]
