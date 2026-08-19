"""Process-wide HTTP ownership for paper upstreams.

Every Collector 1.0 adapter and legacy facade delegates requests here.  A
runtime owns one client and one limiter per upstream, so independently invoked
consumers cannot bypass concurrency, minimum-interval, or Retry-After state.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import AsyncIterator, Awaitable, Callable, Mapping, Optional

import httpx


Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]
WallClock = Callable[[], datetime]


def _enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _bounded_float(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


@dataclass(frozen=True)
class UpstreamPolicy:
    min_interval: float = 0.0
    max_concurrency: int = 1
    timeout: float = 30.0
    trust_env: bool = False
    follow_redirects: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_interval", max(0.0, float(self.min_interval)))
        object.__setattr__(self, "max_concurrency", max(1, int(self.max_concurrency)))
        object.__setattr__(self, "timeout", max(0.1, float(self.timeout)))


def default_upstream_policies() -> dict[str, UpstreamPolicy]:
    return {
        "arxiv": UpstreamPolicy(
            min_interval=_bounded_float(
                os.getenv("ARXIV_MIN_INTERVAL", "3.5"),
                3.5,
                0.0,
                300.0,
            ),
            timeout=45.0,
            trust_env=_enabled("ARXIV_TRUST_ENV", True),
        ),
        "crossref": UpstreamPolicy(),
        "semantic": UpstreamPolicy(
            min_interval=_bounded_float(
                os.getenv("SEMANTIC_SCHOLAR_MIN_INTERVAL", "2.0"),
                2.0,
                0.0,
                300.0,
            ),
        ),
        "openalex": UpstreamPolicy(trust_env=True, follow_redirects=True),
        "publisher": UpstreamPolicy(trust_env=True, follow_redirects=True),
    }


class UpstreamLimiter:
    """Cancellation-safe concurrency, interval, and cooldown coordination."""

    def __init__(
        self,
        policy: UpstreamPolicy,
        *,
        monotonic: Optional[Monotonic] = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.policy = policy
        self._monotonic = monotonic
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(policy.max_concurrency)
        self._schedule_lock = asyncio.Lock()
        self._next_request_at = 0.0

    def _now(self) -> float:
        if self._monotonic is not None:
            return self._monotonic()
        return asyncio.get_running_loop().time()

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await self._semaphore.acquire()
        try:
            async with self._schedule_lock:
                delay = self._next_request_at - self._now()
                if delay > 0:
                    await self._sleep(delay)
                self._next_request_at = self._now() + self.policy.min_interval
            yield
        finally:
            self._semaphore.release()

    async def defer(self, delay: float) -> None:
        bounded = max(0.0, float(delay))
        async with self._schedule_lock:
            self._next_request_at = max(
                self._next_request_at,
                self._now() + bounded,
            )


def retry_after_seconds(
    response: httpx.Response,
    fallback: float,
    *,
    minimum: bool = False,
    clock: WallClock = lambda: datetime.now(timezone.utc),
) -> float:
    raw = response.headers.get("Retry-After", "").strip()
    delay: Optional[float] = None
    if raw:
        try:
            delay = max(0.0, float(raw))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                delay = max(0.0, (parsed.astimezone(timezone.utc) - clock().astimezone(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                delay = None
    if delay is None:
        return max(0.0, float(fallback))
    return max(delay, float(fallback)) if minimum else delay


class PaperHttpRuntime:
    """Own shared clients and limiter state for all paper-source consumers."""

    def __init__(
        self,
        *,
        policies: Optional[Mapping[str, UpstreamPolicy]] = None,
        transports: Optional[Mapping[str, httpx.AsyncBaseTransport]] = None,
        monotonic: Optional[Monotonic] = None,
        sleep: Sleep = asyncio.sleep,
        clock: WallClock = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.policies = {
            key: value if isinstance(value, UpstreamPolicy) else UpstreamPolicy(**value)
            for key, value in (policies or default_upstream_policies()).items()
        }
        self.transports = dict(transports or {})
        self.monotonic = monotonic
        self.sleep = sleep
        self.clock = clock
        self._limiters: dict[str, UpstreamLimiter] = {}
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._client_lock = asyncio.Lock()
        self._closed = False

    def policy(self, upstream: str) -> UpstreamPolicy:
        return self.policies.get(upstream, UpstreamPolicy())

    def limiter(self, upstream: str) -> UpstreamLimiter:
        limiter = self._limiters.get(upstream)
        if limiter is None:
            limiter = UpstreamLimiter(
                self.policy(upstream),
                monotonic=self.monotonic,
                sleep=self.sleep,
            )
            self._limiters[upstream] = limiter
        return limiter

    async def _client(self, upstream: str) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._closed:
                raise RuntimeError("paper HTTP runtime is closed")
            client = self._clients.get(upstream)
            if client is not None:
                return client
            policy = self.policy(upstream)
            transport = self.transports.get(upstream)
            client = httpx.AsyncClient(
                timeout=policy.timeout,
                transport=transport,
                trust_env=policy.trust_env if transport is None else False,
                follow_redirects=policy.follow_redirects,
            )
            self._clients[upstream] = client
            return client

    async def get(
        self,
        upstream: str,
        url: str,
        *,
        params: Optional[Mapping[str, object]] = None,
        headers: Optional[Mapping[str, str]] = None,
        max_retries: int = 0,
        base_delay: float = 1.0,
        max_delay: float = 300.0,
        retry_after_floor: bool = False,
        retry_server_errors: bool = True,
        follow_redirects: Optional[bool] = None,
    ) -> httpx.Response:
        retries = max(0, int(max_retries))
        limiter = self.limiter(upstream)
        client = await self._client(upstream)
        for attempt in range(retries + 1):
            fallback = min(max(0.0, float(base_delay)) * (2.0 ** attempt), max(0.0, float(max_delay)))
            async with limiter.slot():
                try:
                    request_options = {"params": params, "headers": headers}
                    if follow_redirects is not None:
                        request_options["follow_redirects"] = follow_redirects
                    response = await client.get(url, **request_options)
                except httpx.HTTPError:
                    if attempt >= retries:
                        raise
                    await limiter.defer(fallback)
                    continue
                if response.status_code == 429:
                    delay = retry_after_seconds(
                        response,
                        fallback,
                        minimum=retry_after_floor,
                        clock=self.clock,
                    )
                    await limiter.defer(delay)
                    if attempt < retries:
                        continue
                elif retry_server_errors and response.status_code >= 500 and attempt < retries:
                    await limiter.defer(fallback)
                    continue
                return response
        raise RuntimeError("paper HTTP request exhausted retries")

    async def aclose(self) -> None:
        async with self._client_lock:
            if self._closed:
                return
            self._closed = True
            clients = tuple(self._clients.values())
            self._clients.clear()
        failures: list[Exception] = []
        for client in clients:
            try:
                await client.aclose()
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise RuntimeError(f"{len(failures)} paper HTTP client(s) failed to close")

    @property
    def closed(self) -> bool:
        return self._closed


_default_runtime: Optional[PaperHttpRuntime] = None


def default_paper_http_runtime() -> PaperHttpRuntime:
    global _default_runtime
    if _default_runtime is None or bool(getattr(_default_runtime, "closed", False)):
        _default_runtime = PaperHttpRuntime()
    return _default_runtime


def install_default_paper_http_runtime(runtime: PaperHttpRuntime) -> None:
    """Bind compatibility helpers to the host-owned process runtime."""
    global _default_runtime
    if (
        _default_runtime is not None
        and _default_runtime is not runtime
        and not bool(getattr(_default_runtime, "closed", False))
    ):
        raise RuntimeError("a different paper HTTP runtime is already active")
    _default_runtime = runtime


def uninstall_default_paper_http_runtime(runtime: object) -> None:
    """Detach only the runtime currently exposed to legacy compatibility helpers."""

    global _default_runtime
    if _default_runtime is runtime:
        _default_runtime = None


__all__ = [
    "PaperHttpRuntime",
    "UpstreamLimiter",
    "UpstreamPolicy",
    "default_paper_http_runtime",
    "default_upstream_policies",
    "install_default_paper_http_runtime",
    "uninstall_default_paper_http_runtime",
    "retry_after_seconds",
]
