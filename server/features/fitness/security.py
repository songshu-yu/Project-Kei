"""Local-client and trusted-dashboard-Origin protection for fitness data."""

from __future__ import annotations

from typing import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse


LOCAL_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
PROTECTED_PREFIXES = ("/api/v1/fitness", "/fitness")


def is_trusted_local_origin(origin: str | None) -> bool:
    if origin is None or not origin.strip():
        return True
    if origin != origin.strip() or "," in origin:
        return False
    try:
        parsed = urlparse(origin)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in LOCAL_CLIENT_HOSTS
        and port == 8000
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def default_local_control_guard(request: Request) -> bool:
    client = request.client
    if client is not None and client.host not in LOCAL_CLIENT_HOSTS:
        return False
    return is_trusted_local_origin(request.headers.get("origin"))


def _is_protected_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)


class FitnessOriginGuardMiddleware:
    """Reject remote and cross-site fitness requests before wildcard CORS."""

    def __init__(self, app):
        self.app = app

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        path = str(scope.get("path", ""))
        if scope.get("type") != "http" or not _is_protected_path(path):
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        client = scope.get("client")
        if client is not None and client[0] not in LOCAL_CLIENT_HOSTS:
            response = JSONResponse(
                status_code=403,
                content={"detail": {"code": "fitness_local_only", "message": "Fitness data is available only from this computer"}},
            )
            await response(scope, receive, send)
            return
        if not is_trusted_local_origin(headers.get("origin")):
            response = JSONResponse(
                status_code=403,
                content={"detail": {"code": "fitness_origin_forbidden", "message": "Cross-site fitness access is not allowed"}},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


__all__ = [
    "FitnessOriginGuardMiddleware",
    "default_local_control_guard",
    "is_trusted_local_origin",
]
