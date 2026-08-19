"""Closed-world HTTP policy for configured RSS/Atom feeds."""

from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from core.intel_contracts import normalize_url


_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".localdomain")
Resolver = Callable[[str], Iterable[object]]


class FeedFetchError(RuntimeError):
    """A finite feed failure that deliberately carries no response body or URL."""

    def __init__(self, code: str, retry_after: Optional[datetime] = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def _public_hostname(value: object) -> str:
    host = str(value or "").strip().rstrip(".").casefold()
    if not host or "." not in host or host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        raise ValueError("feed host must be a public DNS name")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP-literal feed hosts are not allowed")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("feed host is invalid") from exc
    labels = ascii_host.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        raise ValueError("feed host is invalid")
    return ascii_host


def normalize_feed_url(value: object) -> str:
    normalized = normalize_url(value)
    if not normalized:
        raise ValueError("feed URL must be an absolute HTTPS URL without credentials")
    parsed = urlsplit(normalized)
    if parsed.scheme != "https":
        raise ValueError("feed URL must use HTTPS")
    try:
        if parsed.port not in {None, 443}:
            raise ValueError("feed URL must use the default HTTPS port")
    except ValueError as exc:
        raise ValueError("feed URL port is invalid") from exc
    _public_hostname(parsed.hostname)
    return normalized


def normalize_entry_url(value: object) -> str:
    """Keep public display links but never turn them into fetch targets."""
    normalized = normalize_url(value)
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port not in {None, 80, 443}:
        return ""
    try:
        _public_hostname(parsed.hostname)
    except ValueError:
        return ""
    return normalized


def _system_resolver(host: str) -> Iterable[object]:
    return socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)


def _resolved_addresses(values: Iterable[object]) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    addresses = []
    for value in values:
        candidate = value
        if isinstance(value, tuple) and len(value) >= 5:
            socket_address = value[4]
            if isinstance(socket_address, tuple) and socket_address:
                candidate = socket_address[0]
        try:
            address = ipaddress.ip_address(str(candidate).split("%", 1)[0])
        except ValueError as exc:
            raise FeedFetchError("dns_rejected") from exc
        addresses.append(address)
    if not addresses:
        raise FeedFetchError("network_error")
    return tuple(addresses)


class FeedURLPolicy:
    """Allow only configured feed URLs and explicitly approved redirect hosts."""

    def __init__(
        self,
        feed_urls: Iterable[object],
        *,
        allowed_redirect_hosts: Iterable[object] = (),
        resolver: Optional[Resolver] = None,
        max_feeds: int = 32,
    ) -> None:
        values = (feed_urls,) if isinstance(feed_urls, str) else tuple(feed_urls)
        if len(values) > max(0, int(max_feeds)):
            raise ValueError("too many configured RSS feeds")
        normalized = []
        seen = set()
        for value in values:
            url = normalize_feed_url(value)
            if url not in seen:
                seen.add(url)
                normalized.append(url)
        hosts = {_public_hostname(urlsplit(url).hostname) for url in normalized}
        redirect_hosts = (
            (allowed_redirect_hosts,)
            if isinstance(allowed_redirect_hosts, str)
            else tuple(allowed_redirect_hosts)
        )
        hosts.update(_public_hostname(value) for value in redirect_hosts)
        self.feed_urls = tuple(normalized)
        self.allowed_hosts = frozenset(hosts)
        self._resolver = resolver or _system_resolver

    def assert_public_resolution(self, url: str) -> None:
        host = _public_hostname(urlsplit(url).hostname)
        try:
            addresses = _resolved_addresses(self._resolver(host))
        except FeedFetchError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise FeedFetchError("network_error") from exc
        if any(not address.is_global for address in addresses):
            raise FeedFetchError("dns_rejected")

    def redirect_target(self, current_url: str, location: object) -> str:
        value = str(location or "").strip()
        if not value:
            raise FeedFetchError("redirect_missing_location")
        try:
            target = normalize_feed_url(urljoin(current_url, value))
        except ValueError as exc:
            raise FeedFetchError("redirect_rejected") from exc
        host = _public_hostname(urlsplit(target).hostname)
        if host not in self.allowed_hosts:
            raise FeedFetchError("redirect_rejected")
        return target


def _retry_after(value: object, now: datetime) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return now + timedelta(seconds=min(int(text), 24 * 60 * 60))
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def fetch_feed_xml(
    client: httpx.AsyncClient,
    url: str,
    policy: FeedURLPolicy,
    *,
    now: datetime,
    max_bytes: int = 1024 * 1024,
    max_redirects: int = 3,
) -> bytes:
    current = normalize_feed_url(url)
    for redirect_count in range(max(0, int(max_redirects)) + 1):
        policy.assert_public_resolution(current)
        try:
            async with client.stream("GET", current) as response:
                if response.status_code in _REDIRECT_CODES:
                    if redirect_count >= max_redirects:
                        raise FeedFetchError("too_many_redirects")
                    current = policy.redirect_target(current, response.headers.get("location"))
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    retry_at = _retry_after(response.headers.get("retry-after"), now)
                    if response.status_code == 429:
                        code = "rate_limited"
                    elif response.status_code in {401, 403}:
                        code = "access_denied"
                    elif response.status_code == 404:
                        code = "not_found"
                    elif 500 <= response.status_code <= 599:
                        code = "upstream_unavailable"
                    else:
                        code = "http_error"
                    raise FeedFetchError(code, retry_at)
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max(1, int(max_bytes)):
                        raise FeedFetchError("response_too_large")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.TimeoutException as exc:
            raise FeedFetchError("timeout") from exc
        except httpx.HTTPError as exc:
            raise FeedFetchError("network_error") from exc
    raise FeedFetchError("too_many_redirects")


__all__ = [
    "FeedFetchError",
    "FeedURLPolicy",
    "Resolver",
    "fetch_feed_xml",
    "normalize_entry_url",
    "normalize_feed_url",
]
