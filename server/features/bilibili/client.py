"""Small, injectable HTTP boundary for public Bilibili profile/dynamic data."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import time
from typing import Any, Awaitable, Callable, Mapping, Optional
from urllib.parse import urlencode, urlsplit

import httpx


PROFILE_PATH = "/x/space/wbi/acc/info"
DYNAMIC_PATH = "/x/polymer/web-dynamic/v1/feed/space"
NAV_PATH = "/x/web-interface/nav"
ANTI_BOT_CODES = frozenset({-352, -412})
WBI_MIXIN_KEY_TABLE = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)

Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]
WallClock = Callable[[], float]
CookiesProvider = Callable[[], Mapping[str, str]]


class BilibiliClientError(RuntimeError):
    """A bounded upstream failure that never includes a response body."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = str(code or "upstream_failed")[:80]
        self.retryable = bool(retryable)


def normalize_uid(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("Bilibili UID must be a positive integer")
    text = str(value or "").strip()
    if not text.isdigit() or int(text) <= 0:
        raise ValueError("Bilibili UID must be a positive integer")
    return int(text)


class BilibiliPublicClient:
    """Fetch public profile and space-dynamic payloads with bounded retries.

    The caller may inject ``httpx.MockTransport``.  No profile method calls the
    dynamic endpoint, and no dynamic method calls the profile/video endpoint.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.bilibili.com",
        transport: Optional[httpx.AsyncBaseTransport] = None,
        cookies: Optional[Mapping[str, str]] = None,
        cookies_provider: Optional[CookiesProvider] = None,
        timeout: float = 15.0,
        request_delay: float = 2.5,
        retry_delay: float = 15.0,
        max_attempts: int = 2,
        sleep: Sleep = asyncio.sleep,
        monotonic: Monotonic = time.monotonic,
        wall_clock: WallClock = time.time,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._transport = transport
        self._cookies = {
            str(key): str(value)
            for key, value in dict(cookies or {}).items()
            if str(key).strip() and str(value).strip()
        }
        self._cookies_provider = cookies_provider
        self._active_cookies: Optional[dict[str, str]] = None
        self._timeout = max(0.1, float(timeout))
        self._request_delay = max(0.0, float(request_delay))
        self._retry_delay = max(0.0, float(retry_delay))
        self._max_attempts = max(1, min(2, int(max_attempts)))
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._client = client
        self._owns_client = client is None
        # Installable modules are registered synchronously, potentially before
        # an event loop exists. Bind locks lazily on their first async use.
        self._client_lock: Optional[asyncio.Lock] = None
        self._throttle_lock: Optional[asyncio.Lock] = None
        self._wbi_lock: Optional[asyncio.Lock] = None
        self._lock_loops: dict[str, asyncio.AbstractEventLoop] = {}
        self._wbi_mixin_key: Optional[str] = None
        self._last_request_started: Optional[float] = None

    def _lock(self, name: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(self, name)
        if lock is None or self._lock_loops.get(name) is not loop:
            lock = asyncio.Lock()
            setattr(self, name, lock)
            self._lock_loops[name] = loop
        return lock

    async def __aenter__(self) -> "BilibiliPublicClient":
        await self._http_client()
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        await self.aclose()

    async def _http_client(self) -> httpx.AsyncClient:
        if self._client is not None and (
            not self._owns_client or self._cookies_provider is None
        ):
            return self._client
        async with self._lock("_client_lock"):
            cookies = dict(self._cookies)
            if self._cookies_provider is not None:
                try:
                    provided = self._cookies_provider()
                except Exception:
                    provided = {}
                cookies = {
                    str(key): str(value)
                    for key, value in dict(provided or {}).items()
                    if str(key).strip() and str(value).strip()
                }
            if (
                self._client is not None
                and self._owns_client
                and self._active_cookies != cookies
            ):
                stale = self._client
                self._client = None
                await stale.aclose()
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self._base_url,
                    transport=self._transport,
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                    cookies=cookies,
                    headers={
                        "Accept": "application/json",
                        "Referer": "https://space.bilibili.com/",
                        "User-Agent": "ProjectKei/1.0 Bilibili collector",
                    },
                )
                self._active_cookies = cookies
        return self._client

    async def aclose(self) -> None:
        client = self._client
        if client is not None and self._owns_client:
            self._client = None
            self._active_cookies = None
            await client.aclose()

    async def _throttle(self) -> None:
        async with self._lock("_throttle_lock"):
            now = self._monotonic()
            if self._last_request_started is not None:
                remaining = self._request_delay - (now - self._last_request_started)
                if remaining > 0:
                    awaited = self._sleep(remaining)
                    if inspect.isawaitable(awaited):
                        await awaited
            self._last_request_started = self._monotonic()

    @staticmethod
    def _http_error(status_code: int) -> BilibiliClientError:
        if status_code == 412:
            return BilibiliClientError("anti_bot", retryable=True)
        if status_code == 429:
            return BilibiliClientError("rate_limited", retryable=True)
        if 500 <= status_code <= 599:
            return BilibiliClientError("upstream_unavailable", retryable=True)
        if status_code == 404:
            return BilibiliClientError("not_found")
        return BilibiliClientError("upstream_rejected")

    @staticmethod
    def _api_error(code: object) -> Optional[BilibiliClientError]:
        try:
            value = int(code)
        except (TypeError, ValueError):
            return BilibiliClientError("invalid_response")
        if value == 0:
            return None
        if value in ANTI_BOT_CODES:
            return BilibiliClientError("anti_bot", retryable=True)
        if value == -404:
            return BilibiliClientError("not_found")
        return BilibiliClientError("upstream_rejected")

    async def _get_json(
        self,
        path: str,
        params: Mapping[str, object],
        *,
        accepted_api_codes: frozenset[int] = frozenset(),
    ) -> Mapping[str, Any]:
        last_error = BilibiliClientError("upstream_failed")
        for attempt in range(self._max_attempts):
            await self._throttle()
            try:
                response = await (await self._http_client()).get(path, params=params)
                if response.status_code < 200 or response.status_code >= 300:
                    raise self._http_error(response.status_code)
                try:
                    payload = response.json()
                except (TypeError, ValueError):
                    raise BilibiliClientError("invalid_response")
                if not isinstance(payload, Mapping):
                    raise BilibiliClientError("invalid_response")
                raw_code = payload.get("code")
                try:
                    api_code = int(raw_code)
                except (TypeError, ValueError):
                    api_code = None
                api_error = (
                    None
                    if api_code is not None and api_code in accepted_api_codes
                    else self._api_error(raw_code)
                )
                if api_error is not None:
                    raise api_error
                data = payload.get("data")
                if not isinstance(data, Mapping):
                    raise BilibiliClientError("invalid_response")
                return data
            except BilibiliClientError as exc:
                last_error = exc
            except httpx.TimeoutException:
                last_error = BilibiliClientError("timeout", retryable=True)
            except httpx.TransportError:
                last_error = BilibiliClientError("upstream_unavailable", retryable=True)
            if not last_error.retryable or attempt + 1 >= self._max_attempts:
                break
            if self._retry_delay:
                await self._sleep(self._retry_delay)
        raise last_error

    @staticmethod
    def _wbi_filename_key(url: object) -> str:
        path = urlsplit(str(url or "")).path
        filename = path.rsplit("/", 1)[-1]
        return filename.split(".", 1)[0]

    async def _get_wbi_mixin_key(self) -> str:
        if self._wbi_mixin_key:
            return self._wbi_mixin_key
        async with self._lock("_wbi_lock"):
            if self._wbi_mixin_key:
                return self._wbi_mixin_key
            # Anonymous nav responses may use code -101 while still publishing
            # the current public WBI image keys in ``data.wbi_img``.
            data = await self._get_json(
                NAV_PATH,
                {},
                accepted_api_codes=frozenset({-101}),
            )
            wbi_img = data.get("wbi_img")
            if not isinstance(wbi_img, Mapping):
                raise BilibiliClientError("wbi_key_unavailable", retryable=True)
            raw_key = (
                self._wbi_filename_key(wbi_img.get("img_url"))
                + self._wbi_filename_key(wbi_img.get("sub_url"))
            )
            if len(raw_key) <= max(WBI_MIXIN_KEY_TABLE):
                raise BilibiliClientError("wbi_key_unavailable", retryable=True)
            self._wbi_mixin_key = "".join(
                raw_key[index] for index in WBI_MIXIN_KEY_TABLE
            )[:32]
            return self._wbi_mixin_key

    async def _signed_wbi_params(
        self,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        mixin_key = await self._get_wbi_mixin_key()
        signed: dict[str, object] = dict(params)
        signed["wts"] = int(self._wall_clock())
        sanitized = {
            str(key): "".join(
                character
                for character in str(value)
                if character not in "!'()*"
            )
            for key, value in signed.items()
        }
        query = urlencode(sorted(sanitized.items()))
        signed["w_rid"] = hashlib.md5(
            (query + mixin_key).encode("utf-8")
        ).hexdigest()
        return signed

    async def fetch_profile(self, uid: object) -> dict[str, Any]:
        normalized_uid = normalize_uid(uid)
        params = await self._signed_wbi_params({"mid": normalized_uid})
        data = await self._get_json(PROFILE_PATH, params)
        name = str(data.get("name") or "").strip()
        if not name:
            raise BilibiliClientError("invalid_profile")
        avatar_url = str(data.get("face") or "").strip()
        if avatar_url.startswith("//"):
            avatar_url = "https:" + avatar_url
        return {
            "uid": normalized_uid,
            "name": name[:160],
            "avatar_url": avatar_url[:1000],
        }

    async def fetch_space_dynamics(self, uid: object) -> list[Mapping[str, Any]]:
        normalized_uid = normalize_uid(uid)
        data = await self._get_json(DYNAMIC_PATH, {
            "host_mid": normalized_uid,
            "offset": "",
            "features": "itemOpusStyle",
            "timezone_offset": -480,
        })
        items = data.get("items", [])
        if not isinstance(items, list):
            raise BilibiliClientError("invalid_dynamic_feed")
        return [item for item in items if isinstance(item, Mapping)]


__all__ = [
    "ANTI_BOT_CODES",
    "DYNAMIC_PATH",
    "NAV_PATH",
    "PROFILE_PATH",
    "WBI_MIXIN_KEY_TABLE",
    "BilibiliClientError",
    "BilibiliPublicClient",
    "CookiesProvider",
    "normalize_uid",
]
