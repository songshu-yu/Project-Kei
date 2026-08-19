"""Bounded FxTwitter API v2 fallback for explicit PK-120 post queries."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping, Sequence

import httpx

from core.intel_contracts import sanitize_external_text


FXTWITTER_API_BASE = "https://api.fxtwitter.com"
FXTWITTER_COUNT = 30
FXTWITTER_TIMEOUT_SECONDS = 10.0
FXTWITTER_MAX_RESPONSE_BYTES = 1024 * 1024
FXTWITTER_MAX_PARENT_FETCHES = 8
FXTWITTER_PARENT_CONCURRENCY = 3
_HANDLE_RE = re.compile(r"[A-Za-z0-9_]{1,30}")
_SNOWFLAKE_RE = re.compile(r"\d{2,20}")
_ALLOWED_PATH_RE = re.compile(
    r"/2/(?:profile/[A-Za-z0-9_]{1,30}/statuses|status/\d{2,20})"
)
_ERROR_CODES = frozenset({
    "access_denied",
    "http_error",
    "invalid_json",
    "invalid_request",
    "invalid_response",
    "network_error",
    "not_found",
    "oversize_response",
    "rate_limited",
    "timeout",
    "upstream_unavailable",
})


class FxEmbedFetchError(RuntimeError):
    """Finite, body-free FxEmbed error safe for internal control flow."""

    def __init__(self, code: str, *, retry_after_seconds: int | None = None) -> None:
        safe_code = code if code in _ERROR_CODES else "upstream_unavailable"
        super().__init__(safe_code)
        self.code = safe_code
        self.retry_after_seconds = retry_after_seconds


def _handle(value: object) -> str:
    result = str(value or "").strip().lstrip("@")
    if not _HANDLE_RE.fullmatch(result):
        raise ValueError("X username must contain only letters, numbers, or underscores")
    return result


def _snowflake(value: object) -> str:
    result = str(value or "").strip()
    if not _SNOWFLAKE_RE.fullmatch(result):
        raise ValueError("X status ID must be a valid snowflake")
    return result


def _retry_after_seconds(value: object) -> int | None:
    text = str(value or "").strip()
    if not text.isascii() or not text.isdecimal():
        return None
    seconds = int(text)
    return seconds if 0 <= seconds <= 3600 else None


def _failure_for_status(status: int) -> str:
    if status == 429:
        return "rate_limited"
    if status in {401, 403}:
        return "access_denied"
    if status == 404:
        return "not_found"
    if 500 <= status <= 599:
        return "upstream_unavailable"
    if 400 <= status <= 499:
        return "invalid_request"
    return "http_error"


async def _request_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: Mapping[str, object] | None = None,
) -> Mapping[str, Any] | None:
    if not _ALLOWED_PATH_RE.fullmatch(path):
        raise ValueError("FxEmbed request path is not allowed")
    try:
        async with client.stream(
            "GET",
            f"{FXTWITTER_API_BASE}{path}",
            params=params,
            timeout=FXTWITTER_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code == 204:
                return None
            if response.status_code != 200:
                raise FxEmbedFetchError(
                    _failure_for_status(response.status_code),
                    retry_after_seconds=(
                        _retry_after_seconds(response.headers.get("retry-after"))
                        if response.status_code == 429
                        else None
                    ),
                )
            content_length = response.headers.get("content-length", "").strip()
            if content_length.isdecimal() and int(content_length) > FXTWITTER_MAX_RESPONSE_BYTES:
                raise FxEmbedFetchError("oversize_response")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > FXTWITTER_MAX_RESPONSE_BYTES:
                    raise FxEmbedFetchError("oversize_response")
                chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise FxEmbedFetchError("timeout") from exc
    except httpx.TransportError as exc:
        raise FxEmbedFetchError("network_error") from exc
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FxEmbedFetchError("invalid_json") from exc
    if not isinstance(payload, Mapping):
        raise FxEmbedFetchError("invalid_response")
    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        raise FxEmbedFetchError("invalid_response")
    if code != 200:
        raise FxEmbedFetchError(_failure_for_status(int(code)))
    return payload


def _aware_time(status: Mapping[str, Any]) -> datetime | None:
    value = str(status.get("created_at") or "").strip()
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                parsed = None
        if parsed is not None and parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed
    timestamp = status.get("created_timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _profile_handle(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    candidate = str(value.get("screen_name") or "").strip().lstrip("@")
    return candidate if _HANDLE_RE.fullmatch(candidate) else ""


def _has_marker(value: object) -> bool:
    return isinstance(value, Mapping) and any(
        value.get(field) not in (None, "", False, [], {})
        for field in ("id", "screen_name", "status", "type", "url")
    )


def _status_kind(status: Mapping[str, Any], expected_handle: str) -> tuple[str, str, str]:
    if status.get("type") != "status":
        return "unknown", "", ""
    author_handle = _profile_handle(status.get("author"))
    if not author_handle or author_handle.casefold() != expected_handle.casefold():
        return "unknown", "", ""
    is_repost = _has_marker(status.get("reposted_by"))
    is_reply = _has_marker(status.get("replying_to"))
    is_quote = _has_marker(status.get("quote"))
    if sum((is_repost, is_reply, is_quote)) > 1:
        return "unknown", "", ""
    if is_repost:
        return "repost", "", ""
    if is_reply:
        relation = status.get("replying_to")
        assert isinstance(relation, Mapping)
        return (
            "reply",
            _profile_handle({"screen_name": relation.get("screen_name")}),
            str(relation.get("status") or "").strip(),
        )
    if is_quote:
        return "quote", "", ""
    return "post", "", ""


def _canonical_status_url(username: str, status_id: str) -> str:
    return f"https://x.com/{username}/status/{status_id}"


def _normalized_status(
    status: object,
    expected_handle: str,
    *,
    start_at: datetime,
    end_at: datetime,
    end_inclusive: bool,
) -> tuple[dict[str, Any] | None, str, str]:
    if not isinstance(status, Mapping):
        return None, "", ""
    kind, reply_to, parent_id = _status_kind(status, expected_handle)
    if kind not in {"post", "quote", "reply"}:
        return None, "", ""
    try:
        status_id = _snowflake(status.get("id"))
    except ValueError:
        return None, "", ""
    content = sanitize_external_text(status.get("text"), limit=1_000)
    published_at = _aware_time(status)
    if not content or published_at is None:
        return None, "", ""
    in_window = (
        start_at <= published_at <= end_at
        if end_inclusive
        else start_at <= published_at < end_at
    )
    if not in_window:
        return None, "", ""
    local_published = published_at.astimezone(start_at.tzinfo)
    item: dict[str, Any] = {
        "upstream_id": status_id,
        "kind": kind,
        "content": content,
        "url": _canonical_status_url(expected_handle, status_id),
        "published": local_published.strftime("%Y-%m-%d %H:%M"),
        "published_at": local_published.isoformat(timespec="seconds"),
    }
    if kind == "reply":
        item["reply_to_username"] = reply_to
    return item, reply_to, parent_id


def _parent_context(
    payload: Mapping[str, Any] | None,
    *,
    parent_id: str,
    expected_author: str,
) -> dict[str, str] | None:
    if payload is None:
        return None
    status = payload.get("status")
    if not isinstance(status, Mapping) or status.get("type") != "status":
        return None
    author = _profile_handle(status.get("author"))
    if not author or author.casefold() != expected_author.casefold():
        return None
    try:
        returned_id = _snowflake(status.get("id"))
    except ValueError:
        return None
    if returned_id != parent_id:
        return None
    content = sanitize_external_text(status.get("text"), limit=1_000)
    published_at = _aware_time(status)
    if not content or published_at is None:
        return None
    return {
        "username": f"@{author}",
        "content": content,
        "published_at": published_at.isoformat(timespec="seconds"),
        "url": _canonical_status_url(author, parent_id),
    }


async def _fetch_parent_contexts(
    client: httpx.AsyncClient,
    candidates: Sequence[tuple[int, str, str]],
) -> tuple[dict[int, dict[str, str]], list[str]]:
    semaphore = asyncio.Semaphore(FXTWITTER_PARENT_CONCURRENCY)
    selected: list[tuple[str, str, list[int]]] = []
    by_id: dict[str, tuple[str, list[int]]] = {}
    for index, expected_author, raw_parent_id in candidates:
        try:
            parent_id = _snowflake(raw_parent_id)
            author = _handle(expected_author)
        except ValueError:
            continue
        existing = by_id.get(parent_id)
        if existing is not None:
            if existing[0].casefold() == author.casefold():
                existing[1].append(index)
            continue
        if len(selected) >= FXTWITTER_MAX_PARENT_FETCHES:
            continue
        indexes = [index]
        by_id[parent_id] = (author, indexes)
        selected.append((parent_id, author, indexes))

    async def fetch_one(parent_id: str, author: str, indexes: list[int]):
        async with semaphore:
            try:
                payload = await _request_json(client, f"/2/status/{parent_id}")
                return indexes, _parent_context(
                    payload,
                    parent_id=parent_id,
                    expected_author=author,
                ), ""
            except FxEmbedFetchError as exc:
                detail = exc.code
                if exc.code == "rate_limited" and exc.retry_after_seconds is not None:
                    detail = f"rate_limited:{exc.retry_after_seconds}s"
                return indexes, None, detail

    fetched = await asyncio.gather(
        *(fetch_one(parent_id, author, indexes) for parent_id, author, indexes in selected)
    )
    contexts: dict[int, dict[str, str]] = {}
    warning_codes: set[str] = set()
    for indexes, context, warning in fetched:
        if context is not None:
            for index in indexes:
                contexts[index] = context
        if warning:
            warning_codes.add(warning)
    warnings = [
        f"FxEmbed direct parent context unavailable ({code})."
        for code in sorted(warning_codes)
    ]
    return contexts, warnings


async def fetch_fxembed_posts_window(
    username: object,
    *,
    start_at: datetime,
    end_at: datetime,
    end_inclusive: bool = False,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Fetch one flat timeline page and, for replies, at most one direct parent."""
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        raise ValueError("start_at must be timezone-aware")
    if end_at.tzinfo is None or end_at.utcoffset() is None:
        raise ValueError("end_at must be timezone-aware")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")
    handle = _handle(username)
    owns_client = client is None
    client = client or httpx.AsyncClient(
        headers={
            "Accept": "application/json",
            "User-Agent": "ProjectKei/1.0 FxTwitter explicit fallback",
        },
        follow_redirects=False,
        trust_env=False,
    )
    try:
        payload = await _request_json(
            client,
            f"/2/profile/{handle}/statuses",
            params={
                "count": FXTWITTER_COUNT,
                "since": int(start_at.timestamp()) - 1,
                "with_replies": "1",
            },
        )
        if payload is None:
            results: object = []
        else:
            results = payload.get("results")
            if not isinstance(results, list):
                raise FxEmbedFetchError("invalid_response")
        items: list[dict[str, Any]] = []
        candidates: list[tuple[int, str, str]] = []
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        for raw_status in results:
            item, reply_to, parent_id = _normalized_status(
                raw_status,
                handle,
                start_at=start_at,
                end_at=end_at,
                end_inclusive=end_inclusive,
            )
            if item is None:
                continue
            item_id = str(item["upstream_id"])
            item_url = str(item["url"])
            if item_id in seen_ids or item_url in seen_urls:
                continue
            seen_ids.add(item_id)
            seen_urls.add(item_url)
            index = len(items)
            items.append(item)
            if item["kind"] == "reply" and reply_to and parent_id:
                candidates.append((index, reply_to, parent_id))
            if len(items) >= FXTWITTER_COUNT:
                break
        contexts, parent_warnings = await _fetch_parent_contexts(client, candidates)
        for index, context in contexts.items():
            items[index]["parent_context"] = context
        return {
            "items": items,
            "coverage": {
                "status": "partial",
                "detail": "fxembed_api_v2_fallback",
            },
            "warnings": [
                "FxEmbed exposes one bounded timeline page; window coverage is not guaranteed.",
                *parent_warnings,
            ][:10],
        }
    finally:
        if owns_client:
            await client.aclose()


__all__ = [
    "FXTWITTER_API_BASE",
    "FXTWITTER_COUNT",
    "FXTWITTER_MAX_PARENT_FETCHES",
    "FXTWITTER_PARENT_CONCURRENCY",
    "FxEmbedFetchError",
    "fetch_fxembed_posts_window",
]
