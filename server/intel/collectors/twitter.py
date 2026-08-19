"""X/Nitter RSS helpers and the PK-120 Collector 1.0 implementation."""
from __future__ import annotations

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable, Mapping, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from core.intel_contracts import (
    Collector,
    CacheStatus,
    CollectRequest,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    normalize_url,
    rfc3339,
    sanitize_external_text,
    stable_item_id,
)
from core.intel_contracts import get_timezone


SOURCE_ID = "twitter"
STANDARD_GROUP = "twitter_users"
INFORMATION_GAP_GROUP = "money_twitter_users"
_NITTER_FAILURE_CODES = frozenset({
    "access_denied",
    "http_error",
    "invalid_response",
    "network_error",
    "not_found",
    "parse_error",
    "rate_limited",
    "timeout",
    "upstream_unavailable",
})
_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,30}")
_STATUS_ID_RE = re.compile(r"/status(?:es)?/(\d+)", re.IGNORECASE)
_REPLY_TITLE_RE = re.compile(r"^R to @([A-Za-z0-9_]{1,30}):\s*", re.IGNORECASE)
_REPOST_TITLE_RE = re.compile(r"^RT by @([A-Za-z0-9_]{1,30}):\s*", re.IGNORECASE)
_MALFORMED_MARKER_RE = re.compile(r"^(?:R to|RT by)\b", re.IGNORECASE)
_PINNED_TITLE_RE = re.compile(r"^Pinned:\s*", re.IGNORECASE)
_QUOTE_MARKER_RE = re.compile(
    r"<(?:blockquote)\b|class\s*=\s*['\"][^'\"]*(?:quote|quoted-tweet)[^'\"]*['\"]",
    re.IGNORECASE,
)


class NitterFetchError(RuntimeError):
    """Finite, body-free failure raised after bounded Nitter retries."""

    def __init__(self, code: str) -> None:
        safe_code = code if code in _NITTER_FAILURE_CODES else "upstream_unavailable"
        super().__init__(safe_code)
        self.code = safe_code


def _nitter_failure_code(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return "rate_limited"
        if status in {401, 403}:
            return "access_denied"
        if status == 404:
            return "not_found"
        if 500 <= status <= 599:
            return "upstream_unavailable"
        return "http_error"
    if isinstance(exc, httpx.TransportError):
        return "network_error"
    if isinstance(exc, ET.ParseError):
        return "parse_error"
    if isinstance(exc, ValueError):
        return "invalid_response"
    return "upstream_unavailable"
_RELATION_BLOCK_RE = re.compile(
    r"<(?P<tag>[a-z0-9]+)\b[^>]*class\s*=\s*['\"][^'\"]*"
    r"(?:tweet-reply-context|replying-to|retweet-header)[^'\"]*['\"][^>]*>"
    r".*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_QUOTE_BLOCK_RE = re.compile(
    r"(?:<hr\b[^>]*>\s*)?<blockquote\b[^>]*>.*?</blockquote>",
    re.IGNORECASE | re.DOTALL,
)
_QUOTE_CLASS_BLOCK_RE = re.compile(
    r"(?:<hr\b[^>]*>\s*)?<(?P<tag>[a-z0-9]+)\b[^>]*"
    r"class\s*=\s*['\"][^'\"]*(?:quote|quoted-tweet)[^'\"]*['\"][^>]*>"
    r".*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class Tweet:
    username: str
    content: str
    url: str
    published: str
    upstream_id: str = ""
    kind: str = "post"
    reply_to_username: str = ""


@dataclass(frozen=True)
class ClassifiedTweet:
    username: str
    content: str
    url: str
    published: str
    upstream_id: str
    kind: str
    reply_to_username: str = ""


def _handle(value: object) -> str:
    result = str(value or "").strip().lstrip("@")
    if not _HANDLE_RE.fullmatch(result):
        raise ValueError("X username must contain only letters, numbers, or underscores")
    return result


def _instance_url(value: object) -> str:
    text = str(value or "").strip().rstrip("/")
    try:
        parsed = urlsplit(text)
    except ValueError as exc:
        raise ValueError("Nitter instance must be an absolute HTTP(S) URL") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Nitter instance must be an absolute HTTP(S) URL without credentials or query")
    host = parsed.hostname.lower()
    try:
        netloc = f"{host}:{parsed.port}" if parsed.port else host
    except ValueError as exc:
        raise ValueError("Nitter instance port is invalid") from exc
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path.rstrip("/"), "", ""))


def _rss_profile_name(title: object, username: object) -> str:
    handle = _handle(username)
    name = sanitize_external_text(title, limit=160)
    escaped = re.escape(handle)
    name = re.sub(rf"\s*\(@?{escaped}\)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(rf"\s*/\s*@?{escaped}\s*$", "", name, flags=re.IGNORECASE)
    return name.strip() or f"@{handle}"


def _description_text(value: object) -> str:
    without_markup = re.sub(r"<[^>]+>", " ", unescape(str(value or "")))
    return sanitize_external_text(without_markup, limit=1_000)


def _own_description_text(value: object, *, strip_quote: bool = False) -> str:
    """Return only the followed user's text, never relation or quoted blocks."""
    markup = unescape(str(value or ""))
    markup = _RELATION_BLOCK_RE.sub(" ", markup)
    if strip_quote:
        markup = _QUOTE_CLASS_BLOCK_RE.sub(" ", markup)
        markup = _QUOTE_BLOCK_RE.sub(" ", markup)
    return _description_text(markup)


def _published_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _status_id(url: object, guid: object = "") -> str:
    for value in (url, guid):
        match = _STATUS_ID_RE.search(str(value or ""))
        if match:
            return match.group(1)
    return ""


def _public_status_url(value: object) -> str:
    """Keep only the public status location, never upstream query material."""
    url = normalize_url(value)
    if not url:
        return ""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _rss_classified_items(xml_text: object, username: object) -> list[ClassifiedTweet]:
    """Classify Nitter RSS entries without following status or thread links."""
    handle = _handle(username)
    root = ET.fromstring(str(xml_text).lstrip())
    tweets: list[ClassifiedTweet] = []
    for item in root.findall(".//item"):
        title = sanitize_external_text(unescape(item.findtext("title", "")), limit=1_000)
        title_without_pinned = _PINNED_TITLE_RE.sub("", title, count=1)
        raw_description = str(item.findtext("description", "") or "")
        reply_match = _REPLY_TITLE_RE.match(title_without_pinned)
        repost_match = _REPOST_TITLE_RE.match(title_without_pinned)
        has_quote = bool(_QUOTE_MARKER_RE.search(raw_description))
        malformed_marker = bool(_MALFORMED_MARKER_RE.match(title_without_pinned)) and not (
            reply_match or repost_match
        )

        if malformed_marker or (has_quote and (reply_match or repost_match)):
            kind = "unknown"
            relation_prefix = ""
            reply_to_username = ""
        elif reply_match:
            kind = "reply"
            relation_prefix = reply_match.group(0)
            reply_to_username = reply_match.group(1)
        elif repost_match:
            kind = "repost"
            relation_prefix = repost_match.group(0)
            reply_to_username = ""
        elif has_quote:
            kind = "quote"
            relation_prefix = ""
            reply_to_username = ""
        else:
            kind = "post"
            relation_prefix = ""
            reply_to_username = ""

        content = _own_description_text(raw_description, strip_quote=has_quote)
        if not content:
            content = sanitize_external_text(
                title_without_pinned[len(relation_prefix):],
                limit=1_000,
            )
        if not content:
            kind = "unknown"
        url = _public_status_url(item.findtext("link", ""))
        published = str(item.findtext("pubDate", "") or "").strip()
        tweets.append(
            ClassifiedTweet(
                username=handle,
                content=content,
                url=url,
                published=published,
                upstream_id=_status_id(url, item.findtext("guid", "")),
                kind=kind,
                reply_to_username=reply_to_username,
            )
        )
    return tweets


def _rss_tweets(xml_text: object, username: object) -> list[Tweet]:
    """Return only user-authored content eligible for Collector 1.0."""
    return [
        Tweet(
            username=item.username,
            content=item.content,
            url=item.url,
            published=item.published,
            upstream_id=item.upstream_id,
            kind=item.kind,
            reply_to_username=item.reply_to_username,
        )
        for item in _rss_classified_items(xml_text, username)
        if item.kind in {"post", "quote", "reply"}
    ]


def _rss_daily_content(
    xml_text: object,
    username: object,
    target_date: date,
    local_tz,
    *,
    kinds: set[str],
) -> list[dict[str, str]]:
    """Parse one mutually exclusive content channel for a local calendar day."""
    posts: list[dict[str, str]] = []
    seen: set[str] = set()
    for tweet in _rss_classified_items(xml_text, username):
        if tweet.kind not in kinds:
            continue
        published_at = _published_datetime(tweet.published)
        if published_at is None:
            continue
        local_published = published_at.astimezone(local_tz)
        if local_published.date() != target_date:
            continue
        stable_key = tweet.upstream_id or "\x1f".join(
            (tweet.kind, tweet.url, tweet.content, local_published.isoformat())
        )
        if stable_key in seen:
            continue
        seen.add(stable_key)
        post = {
            "username": tweet.username,
            "kind": tweet.kind,
            "content": tweet.content,
            "url": tweet.url,
            "published": local_published.strftime("%Y-%m-%d %H:%M"),
            "published_at": local_published.isoformat(timespec="seconds"),
            "upstream_id": tweet.upstream_id,
        }
        if tweet.kind == "reply":
            post["reply_to_username"] = tweet.reply_to_username
        posts.append(post)
    return posts[:30]


def _rss_daily_posts(
    xml_text: object,
    username: object,
    target_date: date,
    local_tz,
) -> list[dict[str, str]]:
    return _rss_daily_content(
        xml_text,
        username,
        target_date,
        local_tz,
        kinds={"post", "quote", "reply"},
    )


def _strict_published_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _rss_window_content(
    xml_text: object,
    username: object,
    start_at: datetime,
    end_at: datetime,
    *,
    end_inclusive: bool = False,
) -> dict[str, object]:
    """Parse one bounded half-open window without following status links."""
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        raise ValueError("start_at must be timezone-aware")
    if end_at.tzinfo is None or end_at.utcoffset() is None:
        raise ValueError("end_at must be timezone-aware")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    skipped_without_time = 0
    for tweet in _rss_classified_items(xml_text, username):
        if tweet.kind not in {"post", "quote", "reply"}:
            continue
        published_at = _strict_published_datetime(tweet.published)
        if published_at is None:
            skipped_without_time += 1
            continue
        in_window = (
            start_at <= published_at <= end_at
            if end_inclusive
            else start_at <= published_at < end_at
        )
        if not in_window:
            continue
        local_published = published_at.astimezone(start_at.tzinfo)
        stable_key = tweet.upstream_id or "\x1f".join(
            (tweet.kind, tweet.url, tweet.content, local_published.isoformat())
        )
        if stable_key in seen:
            continue
        seen.add(stable_key)
        item = {
            "username": tweet.username,
            "kind": tweet.kind,
            "content": tweet.content,
            "url": tweet.url,
            "published": local_published.strftime("%Y-%m-%d %H:%M"),
            "published_at": local_published.isoformat(timespec="seconds"),
            "upstream_id": tweet.upstream_id,
        }
        if tweet.kind == "reply":
            item["reply_to_username"] = tweet.reply_to_username
        items.append(item)
        if len(items) >= 30:
            break
    warnings = [
        "Nitter/RSS only exposes a limited upstream snapshot; window coverage is not guaranteed."
    ]
    if skipped_without_time:
        warnings.append(
            f"Skipped {skipped_without_time} item(s) without a valid timezone-aware publication time."
        )
    return {
        "items": items,
        "coverage": {
            "status": "partial",
            "detail": "nitter_rss_best_effort",
        },
        "warnings": warnings,
    }


def _default_retries() -> int:
    try:
        return min(3, max(0, int(os.getenv("NITTER_RETRIES", "2"))))
    except ValueError:
        return 2


def _trust_env() -> bool:
    return os.getenv("NITTER_TRUST_ENV", "true").strip().lower() in {"1", "true", "yes", "on"}


async def _fetch_rss(
    username: object,
    nitter_instances: Sequence[object],
    *,
    client: httpx.AsyncClient,
    retries: int,
) -> tuple[str, str]:
    handle = _handle(username)
    instances = tuple(_instance_url(value) for value in nitter_instances)
    if not instances:
        raise RuntimeError("No Nitter instance is configured")
    last_error_code = "upstream_unavailable"
    for instance in instances:
        rss_url = f"{instance}/{handle}/rss"
        for attempt in range(retries + 1):
            try:
                response = await client.get(rss_url)
                response.raise_for_status()
                root = ET.fromstring(response.text.lstrip())
                if root.find("./channel") is None:
                    raise ValueError("Nitter RSS channel is missing")
            except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
                last_error_code = _nitter_failure_code(exc)
                if attempt < retries:
                    await asyncio.sleep(min(2.0 * (attempt + 1), 6.0))
                continue
            return response.text, instance
    raise NitterFetchError(last_error_code)


def _client_headers(purpose: str) -> dict[str, str]:
    return {
        "User-Agent": f"ProjectKei/1.0 Nitter RSS {purpose}",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }


async def fetch_x_profile(
    username: object,
    nitter_instances: Sequence[object],
    *,
    client: httpx.AsyncClient | None = None,
    retries: int | None = None,
) -> dict[str, str]:
    """Resolve public display metadata from a Nitter RSS channel."""
    handle = _handle(username)
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=30.0,
        headers=_client_headers("profile resolver"),
        follow_redirects=True,
        trust_env=_trust_env(),
    )
    try:
        xml_text, instance = await _fetch_rss(
            handle,
            nitter_instances,
            client=client,
            retries=_default_retries() if retries is None else max(0, int(retries)),
        )
        root = ET.fromstring(xml_text.lstrip())
        channel = root.find("./channel")
        if channel is None:
            raise ValueError("Nitter RSS channel is missing")
        avatar_url = str(channel.findtext("image/url", "") or "").strip()
        if avatar_url:
            avatar_url = normalize_url(urljoin(instance.rstrip("/") + "/", avatar_url))
        return {
            "username": handle,
            "name": _rss_profile_name(channel.findtext("title", ""), handle),
            "avatar_url": avatar_url,
        }
    finally:
        if owns_client:
            await client.aclose()


async def fetch_x_daily_posts(
    username: object,
    nitter_instances: Sequence[object],
    target_date: date | str | None = None,
    local_tz=None,
    *,
    client: httpx.AsyncClient | None = None,
    retries: int | None = None,
) -> list[dict[str, str]]:
    """Fetch one X user's posts published on a single local calendar day."""
    handle = _handle(username)
    local_tz = local_tz or datetime.now().astimezone().tzinfo
    target_date = target_date or datetime.now(local_tz).date()
    if isinstance(target_date, str):
        target_date = date.fromisoformat(target_date)
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=30.0,
        headers=_client_headers("daily-post resolver"),
        follow_redirects=True,
        trust_env=_trust_env(),
    )
    try:
        xml_text, _ = await _fetch_rss(
            handle,
            nitter_instances,
            client=client,
            retries=_default_retries() if retries is None else max(0, int(retries)),
        )
        return _rss_daily_posts(xml_text, handle, target_date, local_tz)
    finally:
        if owns_client:
            await client.aclose()


async def fetch_x_posts_window(
    username: object,
    nitter_instances: Sequence[object],
    *,
    start_at: datetime,
    end_at: datetime,
    end_inclusive: bool = False,
    client: httpx.AsyncClient | None = None,
    retries: int | None = None,
) -> dict[str, object]:
    """Fetch one explicit bounded window from the user's public RSS feed."""
    handle = _handle(username)
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=30.0,
        headers=_client_headers("bounded-post resolver"),
        follow_redirects=True,
        trust_env=_trust_env(),
    )
    try:
        xml_text, _ = await _fetch_rss(
            handle,
            nitter_instances,
            client=client,
            retries=_default_retries() if retries is None else max(0, int(retries)),
        )
        return _rss_window_content(
            xml_text,
            handle,
            start_at,
            end_at,
            end_inclusive=end_inclusive,
        )
    finally:
        if owns_client:
            await client.aclose()


async def fetch_twitter(
    users: Iterable[object],
    nitter_instances: Sequence[object],
    hours: int = 24,
    *,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    retries: int | None = None,
) -> list[Tweet]:
    """Legacy-compatible multi-user helper with bounded, sanitized failures."""
    handles: list[str] = []
    seen: set[str] = set()
    for value in users:
        handle = _handle(value)
        if handle.casefold() not in seen:
            seen.add(handle.casefold())
            handles.append(handle)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    cutoff = current_time - timedelta(hours=max(1, min(720, int(hours))))
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=30.0,
        headers=_client_headers("collector"),
        follow_redirects=True,
        trust_env=_trust_env(),
    )
    results: list[Tweet] = []
    failures = 0
    try:
        for handle in handles:
            try:
                xml_text, _ = await _fetch_rss(
                    handle,
                    nitter_instances,
                    client=client,
                    retries=_default_retries() if retries is None else max(0, int(retries)),
                )
                for tweet in _rss_tweets(xml_text, handle):
                    published_at = _published_datetime(tweet.published)
                    if published_at is None or published_at >= cutoff:
                        results.append(tweet)
            except (RuntimeError, ValueError, ET.ParseError):
                failures += 1
        if failures:
            print(f"[Twitter] {failures} configured target(s) unavailable")
        return results
    finally:
        if owns_client:
            await client.aclose()


def _classified_targets(snapshot: Mapping[str, object]) -> list[tuple[str, tuple[str, ...]]]:
    targets: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for group in (STANDARD_GROUP, INFORMATION_GAP_GROUP):
        values = snapshot.get(group, [])
        if not isinstance(values, (list, tuple)):
            continue
        for value in values:
            try:
                handle = _handle(value)
            except ValueError:
                continue
            key = handle.casefold()
            if key not in targets:
                targets[key] = {"username": handle, "groups": []}
                order.append(key)
            groups = targets[key]["groups"]
            if isinstance(groups, list) and group not in groups:
                groups.append(group)
    return [
        (str(targets[key]["username"]), tuple(targets[key]["groups"]))
        for key in order
    ]


class NitterCollector(Collector):
    """Collect configured X accounts directly into the frozen Collector 1.0 models."""

    source_id = SOURCE_ID

    def __init__(
        self,
        nitter_instances: Sequence[object],
        *,
        client: httpx.AsyncClient | None = None,
        clock=None,
        retries: int | None = None,
    ) -> None:
        self._instances = tuple(_instance_url(value) for value in nitter_instances)
        self._client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._retries = _default_retries() if retries is None else max(0, min(3, int(retries)))

    async def collect(self, request: CollectRequest) -> CollectorResult:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("NitterCollector clock must return an aware datetime")
        fetched_at = rfc3339(now)
        targets = _classified_targets(request.source_config_snapshot)
        if SOURCE_ID not in request.source_ids or not targets:
            coverage = SourceCoverage(CoverageStatus.NOT_CONFIGURED, detail="No X target is configured")
            return CollectorResult(
                source_id=SOURCE_ID,
                items=(),
                warnings=(),
                coverage=coverage,
                fetched_at=fetched_at,
                cache_status=CacheStatus.UNAVAILABLE,
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=30.0,
            headers=_client_headers("Collector 1.0"),
            follow_redirects=True,
            trust_env=_trust_env(),
        )
        items: list[IntelItem] = []
        failures = 0
        failure_codes: dict[str, int] = {}
        local_tz = get_timezone(request.timezone)
        lookback_cutoff = now - timedelta(hours=request.lookback)
        try:
            for username, groups in targets:
                try:
                    xml_text, _ = await _fetch_rss(
                        username,
                        self._instances,
                        client=client,
                        retries=self._retries,
                    )
                    for tweet in _rss_tweets(xml_text, username):
                        published = _published_datetime(tweet.published)
                        if published is not None:
                            if published < lookback_cutoff or published > now + timedelta(minutes=5):
                                continue
                            published_at = rfc3339(published)
                        else:
                            published_at = ""
                        item_url = normalize_url(tweet.url)
                        items.append(
                            IntelItem(
                                stable_id=stable_item_id(
                                    SOURCE_ID,
                                    upstream_id=tweet.upstream_id,
                                    url=item_url,
                                    title=tweet.content,
                                    author=username,
                                    published_at=published_at,
                                ),
                                source_id=SOURCE_ID,
                                category="social",
                                title=tweet.content,
                                url=item_url,
                                author=username,
                                published_at=published_at,
                                fetched_at=fetched_at,
                                metadata={
                                    "username": username,
                                    "x_content_kind": tweet.kind,
                                    "reply_to_username": tweet.reply_to_username,
                                    "x_config_groups": list(groups),
                                    "local_date": request.local_date.isoformat(),
                                    "timezone": request.timezone,
                                    "published_local_date": (
                                        published.astimezone(local_tz).date().isoformat()
                                        if published is not None
                                        else ""
                                    ),
                                },
                            )
                        )
                except (RuntimeError, ValueError, ET.ParseError, httpx.HTTPError) as exc:
                    failures += 1
                    code = (
                        exc.code
                        if isinstance(exc, NitterFetchError)
                        else _nitter_failure_code(exc)
                    )
                    failure_codes[code] = failure_codes.get(code, 0) + 1
        finally:
            if owns_client:
                await client.aclose()

        retry_after = rfc3339(now + timedelta(hours=6)) if failures else None
        warnings = []
        if failures:
            warnings.append(f"twitter: {failures} configured target(s) unavailable")
            warnings.extend(
                f"twitter: {count} target(s) failed ({code})"
                for code, count in sorted(failure_codes.items())
            )
        if items and failures:
            status = CoverageStatus.PARTIAL
            detail = "Some configured X targets were unavailable"
        elif items:
            status = CoverageStatus.COMPLETE
            detail = ""
        elif failures:
            status = CoverageStatus.FAILED
            detail = "Configured X targets could not be collected"
        else:
            status = CoverageStatus.EMPTY
            detail = "Configured X targets had no posts in the requested window"
        coverage = SourceCoverage(status, len(items), detail, retry_after)
        return CollectorResult(
            source_id=SOURCE_ID,
            items=tuple(items),
            warnings=tuple(warnings),
            coverage=coverage,
            fetched_at=fetched_at,
            retry_after=retry_after,
            cache_status=CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED,
        )


__all__ = [
    "INFORMATION_GAP_GROUP",
    "NitterCollector",
    "SOURCE_ID",
    "STANDARD_GROUP",
    "Tweet",
    "fetch_twitter",
    "fetch_x_daily_posts",
    "fetch_x_posts_window",
    "fetch_x_profile",
]
