"""Global loopback-only access boundary for the Project Kei local API."""

from __future__ import annotations

import ipaddress
from typing import Awaitable, Callable

from starlette.responses import JSONResponse


LOCAL_ONLY_MESSAGE = "仅允许本机访问"
TRUSTED_LOCAL_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://[::1]:8000",
)


def is_loopback_host(host: object) -> bool:
    """Trust only the peer address supplied by the ASGI server."""

    if not isinstance(host, str) or not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return address in ipaddress.ip_network("127.0.0.0/8")
    return address == ipaddress.IPv6Address("::1")


def is_loopback_scope(scope: dict) -> bool:
    client = scope.get("client")
    return (
        isinstance(client, (tuple, list))
        and len(client) >= 1
        and is_loopback_host(client[0])
    )


def is_trusted_local_origin(origin: str | None) -> bool:
    """Allow non-browser clients or one exact same-machine dashboard Origin."""

    return origin is None or origin in TRUSTED_LOCAL_ORIGINS


def _origin_from_scope(scope: dict) -> str | None:
    origin = None
    for raw_name, raw_value in scope.get("headers", ()):
        if raw_name.lower() == b"origin":
            if origin is not None:
                return ""
            try:
                origin = raw_value.decode("latin-1")
            except UnicodeDecodeError:
                return ""
    return origin


class LoopbackAccessMiddleware:
    """Fail closed before routing for every HTTP and WebSocket request."""

    def __init__(self, app):
        self.app = app

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        scope_type = scope.get("type")
        if scope_type not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        allowed = is_loopback_scope(scope) and is_trusted_local_origin(
            _origin_from_scope(scope)
        )
        if allowed:
            await self.app(scope, receive, send)
            return

        if scope_type == "websocket":
            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": LOCAL_ONLY_MESSAGE,
                }
            )
            return

        response = JSONResponse(
            status_code=403,
            content={"detail": LOCAL_ONLY_MESSAGE},
        )
        await response(scope, receive, send)


__all__ = [
    "LOCAL_ONLY_MESSAGE",
    "LoopbackAccessMiddleware",
    "TRUSTED_LOCAL_ORIGINS",
    "is_loopback_host",
    "is_loopback_scope",
    "is_trusted_local_origin",
]
