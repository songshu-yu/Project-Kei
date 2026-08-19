"""GitHub public-events and releases Collector 1.0 implementation."""
from __future__ import annotations

import email.utils
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Mapping, Sequence
from urllib.parse import quote, urlsplit

import httpx

from core.intel_contracts import (
    CacheStatus,
    CollectRequest,
    Collector,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    localize,
    rfc3339,
    stable_item_id,
)


Clock = Callable[[], datetime]
_GITHUB_USER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_GITHUB_REPO_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}"
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


@dataclass(frozen=True)
class GitHubCollectorSettings:
    """Non-secret runtime controls for GitHub API collection."""

    api_base: str = "https://api.github.com"
    per_page: int = 100
    max_pages: int = 3
    timeout_seconds: float = 20.0
    transient_retry_seconds: int = 30 * 60
    trust_env: bool = True
    use_environment_auth: bool = True

    def __post_init__(self) -> None:
        parsed = urlsplit(self.api_base)
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("GitHub API base has an invalid port") from exc
        if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("GitHub API base must be an HTTPS origin")
        if parsed.query or parsed.fragment:
            raise ValueError("GitHub API base cannot contain query or fragment")
        if not 1 <= int(self.per_page) <= 100:
            raise ValueError("GitHub per_page must be between 1 and 100")
        if not 1 <= int(self.max_pages) <= 20:
            raise ValueError("GitHub max_pages must be between 1 and 20")
        if float(self.timeout_seconds) <= 0:
            raise ValueError("GitHub timeout must be positive")
        if int(self.transient_retry_seconds) < 60:
            raise ValueError("GitHub transient retry delay must be at least 60 seconds")

    @classmethod
    def from_environment(cls) -> "GitHubCollectorSettings":
        return cls(
            per_page=_env_int("GITHUB_PER_PAGE", 100, minimum=1, maximum=100),
            max_pages=_env_int("GITHUB_MAX_PAGES", 3, minimum=1, maximum=20),
            timeout_seconds=float(
                _env_int("GITHUB_TIMEOUT_SECONDS", 20, minimum=1, maximum=120)
            ),
            transient_retry_seconds=_env_int(
                "GITHUB_TRANSIENT_RETRY_SECONDS",
                30 * 60,
                minimum=60,
                maximum=24 * 60 * 60,
            ),
            trust_env=_env_bool("GITHUB_TRUST_ENV", True),
        )


@dataclass(frozen=True)
class _PageOutcome:
    values: tuple[Mapping[str, object], ...]
    successful_request: bool
    complete: bool
    error_code: str = ""
    retry_after: str | None = None
    rate_limit_exhausted: bool = False


def _aware_now(clock: Clock) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("GitHub collector clock must return an aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return ""
    return rfc3339(parsed)


def _timestamp_value(value: object) -> datetime | None:
    normalized = _timestamp(value)
    if not normalized:
        return None
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _has_next_link(value: str) -> bool:
    return any('rel="next"' in part.casefold() or "rel=next" in part.casefold() for part in value.split(","))


def _retry_after(response: httpx.Response, now: datetime, fallback_seconds: int) -> str:
    header = response.headers.get("Retry-After", "").strip()
    candidate: datetime | None = None
    if header.isdigit():
        candidate = now + timedelta(seconds=max(1, int(header)))
    elif header:
        try:
            candidate = email.utils.parsedate_to_datetime(header)
        except (TypeError, ValueError, OverflowError):
            candidate = None
    if candidate is None:
        reset = response.headers.get("X-RateLimit-Reset", "").strip()
        try:
            candidate = datetime.fromtimestamp(int(reset), tz=timezone.utc) if reset else None
        except (ValueError, OverflowError, OSError):
            candidate = None
    if candidate is None or candidate <= now:
        candidate = now + timedelta(seconds=fallback_seconds)
    if candidate.tzinfo is None or candidate.utcoffset() is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return rfc3339(candidate)


def _runtime_headers(*, use_environment_auth: bool, api_base: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ProjectKei/1.0 GitHub collector",
    }
    # Authentication is deliberately read only at request time. It is never
    # accepted from the Collector snapshot or retained in a result object.
    parsed_base = urlsplit(api_base)
    official_api = (
        parsed_base.scheme.casefold() == "https"
        and parsed_base.hostname == "api.github.com"
        and parsed_base.port in {None, 443}
    )
    token = os.getenv("GITHUB_TOKEN", "").strip() if use_environment_auth and official_api else ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class _GitHubAPIClient:
    """Small API client with bounded, same-endpoint pagination."""

    def __init__(
        self,
        *,
        settings: GitHubCollectorSettings,
        transport: httpx.AsyncBaseTransport | None,
        clock: Clock,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._clock = clock

    async def fetch_paginated(
        self,
        path: str,
        *,
        stop_after_page: Callable[[Sequence[Mapping[str, object]]], bool],
    ) -> _PageOutcome:
        values: list[Mapping[str, object]] = []
        successful_request = False
        async with httpx.AsyncClient(
            base_url=self._settings.api_base,
            headers=_runtime_headers(
                use_environment_auth=self._settings.use_environment_auth,
                api_base=self._settings.api_base,
            ),
            timeout=self._settings.timeout_seconds,
            follow_redirects=False,
            trust_env=self._settings.trust_env,
            transport=self._transport,
        ) as client:
            for page in range(1, self._settings.max_pages + 1):
                now = _aware_now(self._clock)
                try:
                    response = await client.get(
                        path,
                        params={"per_page": self._settings.per_page, "page": page},
                    )
                except (httpx.TimeoutException, httpx.RequestError):
                    return _PageOutcome(
                        tuple(values),
                        successful_request,
                        False,
                        "request_failed",
                        rfc3339(now + timedelta(seconds=self._settings.transient_retry_seconds)),
                    )

                remaining = response.headers.get("X-RateLimit-Remaining", "").strip()
                if response.status_code == 401:
                    return _PageOutcome(tuple(values), successful_request, False, "authentication_failed")
                if response.status_code in {403, 429} and (
                    response.status_code == 429
                    or remaining == "0"
                    or bool(response.headers.get("Retry-After"))
                ):
                    return _PageOutcome(
                        tuple(values),
                        successful_request,
                        False,
                        "rate_limited",
                        _retry_after(response, now, 60),
                        True,
                    )
                if response.status_code == 404:
                    return _PageOutcome(tuple(values), successful_request, False, "not_found")
                if response.status_code in {408, 500, 502, 503, 504}:
                    return _PageOutcome(
                        tuple(values),
                        successful_request,
                        False,
                        "upstream_unavailable",
                        rfc3339(now + timedelta(seconds=self._settings.transient_retry_seconds)),
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    return _PageOutcome(tuple(values), successful_request, False, "request_rejected")
                try:
                    payload = response.json()
                except ValueError:
                    return _PageOutcome(tuple(values), successful_request, False, "invalid_response")
                if not isinstance(payload, list) or any(not isinstance(item, Mapping) for item in payload):
                    return _PageOutcome(tuple(values), successful_request, False, "invalid_response")

                page_values = tuple(payload)
                values.extend(page_values)
                successful_request = True
                has_next = _has_next_link(response.headers.get("Link", ""))
                if stop_after_page(page_values) or not has_next:
                    return _PageOutcome(
                        tuple(values),
                        True,
                        True,
                        retry_after=_retry_after(response, now, 60) if remaining == "0" else None,
                        rate_limit_exhausted=remaining == "0",
                    )
                if remaining == "0":
                    return _PageOutcome(
                        tuple(values),
                        True,
                        False,
                        "rate_limited",
                        _retry_after(response, now, 60),
                        True,
                    )

        return _PageOutcome(tuple(values), True, False, "pagination_limit")


def _normalized_values(snapshot: Mapping[str, object], key: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    raw_values = snapshot.get(key, ())
    if not isinstance(raw_values, (list, tuple)):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        identity = value.casefold()
        if pattern.fullmatch(value) and identity not in seen:
            seen.add(identity)
            result.append(value)
    return tuple(result)


def _configured_value_count(snapshot: Mapping[str, object], key: str) -> int:
    value = snapshot.get(key, ())
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0 if value in (None, "") else 1


def _request_window(request: CollectRequest, now: datetime) -> tuple[datetime, datetime]:
    day_start = localize(datetime.combine(request.local_date, time.min), request.timezone)
    day_end = localize(
        datetime.combine(request.local_date + timedelta(days=1), time.min),
        request.timezone,
    )
    if now < day_start.astimezone(timezone.utc):
        return day_start.astimezone(timezone.utc), now
    upper = min(now, day_end.astimezone(timezone.utc))
    return upper - timedelta(hours=request.lookback), upper


def _page_is_before(
    values: Sequence[Mapping[str, object]],
    *,
    timestamp_key: str,
    lower: datetime,
) -> bool:
    if not values:
        return True
    timestamps = [_timestamp_value(item.get(timestamp_key)) for item in values]
    return all(value is not None and value < lower for value in timestamps)


def _repo_url(repo_name: str) -> str:
    return f"https://github.com/{repo_name}" if _GITHUB_REPO_RE.fullmatch(repo_name) else ""


def _event_item(
    event: Mapping[str, object],
    *,
    configured_user: str,
    fetched_at: str,
    lower: datetime,
    upper: datetime,
) -> IntelItem | None:
    published = _timestamp(event.get("created_at"))
    published_value = _timestamp_value(published)
    if published_value is None or published_value < lower or published_value > upper + timedelta(minutes=5):
        return None
    event_type = str(event.get("type") or "").strip()
    repo_value = event.get("repo")
    repo_name = str(repo_value.get("name") or "").strip() if isinstance(repo_value, Mapping) else ""
    actor_value = event.get("actor")
    actor = str(actor_value.get("login") or "").strip() if isinstance(actor_value, Mapping) else ""
    actor = actor or configured_user
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    action = str(payload.get("action") or "").strip()
    title = f"{actor} published {event_type or 'an event'}"
    summary = ""
    url = _repo_url(repo_name)

    if event_type == "WatchEvent":
        title = f"{actor} starred {repo_name}"
    elif event_type == "PushEvent":
        title = f"{actor} pushed to {repo_name}"
        commits = payload.get("commits") if isinstance(payload.get("commits"), list) else []
        messages = [
            str(item.get("message") or "").strip()
            for item in commits[:3]
            if isinstance(item, Mapping) and str(item.get("message") or "").strip()
        ]
        summary = " | ".join(messages)
    elif event_type == "CreateEvent":
        ref_type = str(payload.get("ref_type") or "item").strip()
        ref = str(payload.get("ref") or "").strip()
        title = f"{actor} created {ref_type} in {repo_name}"
        if url and ref:
            url = f"{url}/tree/{quote(ref, safe='')}"
    elif event_type == "ForkEvent":
        title = f"{actor} forked {repo_name}"
        forkee = payload.get("forkee")
        if isinstance(forkee, Mapping):
            url = str(forkee.get("html_url") or url)
    elif event_type == "PullRequestEvent":
        pull_request = payload.get("pull_request")
        if isinstance(pull_request, Mapping):
            title = f"{actor} {action or 'updated'} a pull request in {repo_name}"
            summary = str(pull_request.get("title") or "")
            url = str(pull_request.get("html_url") or url)
    elif event_type in {"IssuesEvent", "IssueCommentEvent"}:
        issue = payload.get("issue")
        if isinstance(issue, Mapping):
            title = f"{actor} {action or 'updated'} an issue in {repo_name}"
            summary = str(issue.get("title") or "")
            url = str(issue.get("html_url") or url)
    elif event_type == "ReleaseEvent":
        release = payload.get("release")
        if isinstance(release, Mapping):
            title = f"{repo_name} released {release.get('name') or release.get('tag_name') or ''}"
            summary = str(release.get("body") or "")
            url = str(release.get("html_url") or url)
    elif repo_name:
        title = f"{actor} {action or 'updated'} {repo_name} ({event_type or 'event'})"

    upstream_id = event.get("id") or ""
    return IntelItem(
        stable_id=stable_item_id(
            "github",
            upstream_id=f"event:{upstream_id}" if upstream_id else "",
            url=url,
            title=title,
            author=actor,
            published_at=published,
        ),
        source_id="github",
        category="development",
        title=title,
        summary=summary,
        url=url,
        author=actor,
        published_at=published,
        fetched_at=fetched_at,
        metadata={
            "record_type": "user_event",
            "event_type": event_type,
            "repository": repo_name,
        },
    )


def _release_item(
    release: Mapping[str, object],
    *,
    repository: str,
    fetched_at: str,
    lower: datetime,
    upper: datetime,
) -> IntelItem | None:
    if release.get("draft") is True:
        return None
    published = _timestamp(release.get("published_at"))
    published_value = _timestamp_value(published)
    if published_value is None or published_value < lower or published_value > upper + timedelta(minutes=5):
        return None
    name = str(release.get("name") or release.get("tag_name") or "").strip()
    if not name:
        return None
    title = f"{repository} released {name}"
    url = str(release.get("html_url") or "")
    upstream_id = release.get("id") or release.get("node_id") or ""
    return IntelItem(
        stable_id=stable_item_id(
            "github",
            upstream_id=f"release:{upstream_id}" if upstream_id else "",
            url=url,
            title=title,
            author=repository,
            published_at=published,
        ),
        source_id="github",
        category="development",
        title=title,
        summary=str(release.get("body") or ""),
        url=url,
        author=repository,
        published_at=published,
        fetched_at=fetched_at,
        metadata={
            "record_type": "release",
            "repository": repository,
            "tag_name": str(release.get("tag_name") or ""),
            "prerelease": bool(release.get("prerelease", False)),
        },
    )


_WARNING_TEXT = {
    "authentication_failed": "github: authentication was rejected",
    "rate_limited": "github: API rate limit was reached",
    "not_found_user": "github: one user target was not found",
    "not_found_repo": "github: one repository target was not found",
    "request_failed": "github: an API request failed",
    "upstream_unavailable": "github: API is temporarily unavailable",
    "request_rejected": "github: an API request was rejected",
    "invalid_response": "github: API returned an invalid response",
    "pagination_limit": "github: pagination limit was reached",
    "invalid_configuration": "github: invalid targets were ignored",
}


class GitHubCollector(Collector):
    """Collect configured public GitHub activity into Collector 1.0 models."""

    source_id = "github"

    def __init__(
        self,
        *,
        settings: GitHubCollectorSettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._settings = settings or GitHubCollectorSettings.from_environment()
        self._transport = transport
        self._clock = clock

    async def collect(self, request: CollectRequest) -> CollectorResult:
        now = _aware_now(self._clock)
        fetched_at = rfc3339(now)
        users = _normalized_values(request.source_config_snapshot, "github_users", _GITHUB_USER_RE)
        repositories = _normalized_values(request.source_config_snapshot, "github_repos", _GITHUB_REPO_RE)
        raw_user_count = _configured_value_count(request.source_config_snapshot, "github_users")
        raw_repo_count = _configured_value_count(request.source_config_snapshot, "github_repos")
        invalid_count = max(0, raw_user_count - len(users)) + max(0, raw_repo_count - len(repositories))
        if not users and not repositories:
            warnings = (_WARNING_TEXT["invalid_configuration"],) if invalid_count else ()
            return CollectorResult(
                source_id=self.source_id,
                items=(),
                warnings=warnings,
                coverage=SourceCoverage(
                    CoverageStatus.NOT_CONFIGURED,
                    detail="source has no active configuration",
                ),
                fetched_at=fetched_at,
                cache_status=CacheStatus.UNAVAILABLE,
            )

        lower, upper = _request_window(request, now)
        client = _GitHubAPIClient(settings=self._settings, transport=self._transport, clock=self._clock)
        targets = [
            ("user", user, f"/users/{quote(user, safe='')}/events/public", "created_at")
            for user in users
        ] + [
            ("repo", repository, f"/repos/{repository}/releases", "published_at")
            for repository in repositories
        ]
        items: list[IntelItem] = []
        seen_ids: set[str] = set()
        errors: Counter[str] = Counter()
        successful_targets = 0
        retry_values: list[str] = []
        if invalid_count:
            errors["invalid_configuration"] += invalid_count

        for index, (kind, target, path, timestamp_key) in enumerate(targets):
            outcome = await client.fetch_paginated(
                path,
                stop_after_page=lambda page, key=timestamp_key: _page_is_before(
                    page,
                    timestamp_key=key,
                    lower=lower,
                ),
            )
            if outcome.successful_request:
                successful_targets += 1
            if not outcome.complete:
                code = outcome.error_code or "request_failed"
                if code == "not_found":
                    code = "not_found_user" if kind == "user" else "not_found_repo"
                errors[code] += 1
            if outcome.retry_after:
                retry_values.append(outcome.retry_after)

            for value in outcome.values:
                try:
                    item = (
                        _event_item(
                            value,
                            configured_user=target,
                            fetched_at=fetched_at,
                            lower=lower,
                            upper=upper,
                        )
                        if kind == "user"
                        else _release_item(
                            value,
                            repository=target,
                            fetched_at=fetched_at,
                            lower=lower,
                            upper=upper,
                        )
                    )
                except (TypeError, ValueError):
                    item = None
                    errors["invalid_response"] += 1
                if item is not None and item.stable_id not in seen_ids:
                    seen_ids.add(item.stable_id)
                    items.append(item)

            if outcome.rate_limit_exhausted and index < len(targets) - 1:
                if outcome.complete:
                    errors["rate_limited"] += 1
                break
            if outcome.error_code in {"authentication_failed", "rate_limited"}:
                break

        warnings = tuple(
            f"{_WARNING_TEXT[code]} ({count})" if count > 1 else _WARNING_TEXT[code]
            for code, count in sorted(errors.items())
            if code in _WARNING_TEXT
        )
        if errors:
            status = CoverageStatus.PARTIAL if items else CoverageStatus.FAILED
        elif items:
            status = CoverageStatus.COMPLETE
        else:
            status = CoverageStatus.EMPTY
        retry_after = min(retry_values) if retry_values else None
        cache_status = (
            CacheStatus.UNAVAILABLE
            if status is CoverageStatus.FAILED
            else CacheStatus.REFRESHED if request.refresh else CacheStatus.FETCHED
        )
        return CollectorResult(
            source_id=self.source_id,
            items=tuple(items),
            warnings=warnings,
            coverage=SourceCoverage(
                status,
                len(items),
                detail=f"processed {successful_targets} of {len(targets)} configured targets",
                retry_after=retry_after,
            ),
            fetched_at=fetched_at,
            retry_after=retry_after,
            cache_status=cache_status,
        )


__all__ = [
    "GitHubCollector",
    "GitHubCollectorSettings",
]
