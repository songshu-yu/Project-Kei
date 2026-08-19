"""Same-origin protection for local Voice Pack state mutations."""

from __future__ import annotations

from typing import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse


VOICE_PACK_API_PREFIX = "/api/v1/voice-packs"
VOICE_PACK_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOCAL_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
LOCAL_CONTROL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def is_trusted_local_origin(origin: str | None) -> bool:
    """Allow non-browser calls without Origin or the fixed local dashboard origin."""
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
        and parsed.hostname in LOCAL_CONTROL_HOSTS
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


def _forbidden_response(code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": {"code": code, "message": message}},
    )


class VoicePackOriginGuardMiddleware:
    """Reject cross-site Voice Pack writes before wildcard CORS handles preflight."""

    def __init__(self, app):
        self.app = app

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        path = str(scope.get("path", ""))
        if scope.get("type") != "http" or not (
            path == VOICE_PACK_API_PREFIX or path.startswith(VOICE_PACK_API_PREFIX + "/")
        ):
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        requested_method = headers.get("access-control-request-method", "").upper()
        is_write = method in VOICE_PACK_WRITE_METHODS
        is_write_preflight = method == "OPTIONS" and requested_method in VOICE_PACK_WRITE_METHODS
        if not is_write and not is_write_preflight:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if client is not None and client[0] not in LOCAL_CLIENT_HOSTS:
            response = _forbidden_response(
                "voice_pack_local_only",
                "Voice Pack changes are available only from this computer",
            )
            await response(scope, receive, send)
            return
        if not is_trusted_local_origin(headers.get("origin")):
            response = _forbidden_response(
                "voice_pack_origin_forbidden",
                "Cross-site Voice Pack changes are not allowed",
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
