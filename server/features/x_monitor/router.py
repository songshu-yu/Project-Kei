"""Versioned PK-120 router factory used by the main application composition."""
from __future__ import annotations

from typing import Callable, Mapping, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from .models import XPostQueryRequest
from .service import XMonitorService


SourceConfigLoader = Callable[[], Mapping[str, object]]
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _require_local(request: Request) -> None:
    client_host = (request.client.host if request.client else "").casefold()
    if client_host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="This action is available only from this computer")
    origin = request.headers.get("origin", "").strip()
    if not origin:
        return
    try:
        parsed = urlsplit(origin)
        origin_host = (parsed.hostname or "").casefold()
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Untrusted browser origin") from exc
    if parsed.scheme not in {"http", "https"} or origin_host not in _LOCAL_HOSTS or port != 8000:
        raise HTTPException(status_code=403, detail="Untrusted browser origin")


def build_router(
    service: XMonitorService,
    source_config_loader: SourceConfigLoader,
    *,
    include_legacy: bool = False,
) -> APIRouter:
    """Build X routes without importing another feature's implementation."""
    router = APIRouter(tags=["x-monitor"])

    async def read_profiles(request: Request, username: Optional[str] = None):
        _require_local(request)
        try:
            return service.read_profiles(source_config_loader(), username=username)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def resolve_profiles(
        request: Request,
        username: Optional[str] = None,
        refresh: bool = False,
    ):
        _require_local(request)
        try:
            return await service.resolve_profiles(
                source_config_loader(),
                username=username,
                refresh=refresh,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def get_posts(request: Request):
        _require_local(request)
        try:
            return service.get_daily_posts(source_config_loader())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def fetch_posts(request: Request, username: str):
        _require_local(request)
        try:
            return await service.fetch_daily_posts(source_config_loader(), username=username)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail="X sources are temporarily unavailable") from exc

    async def query_posts(payload: XPostQueryRequest, request: Request):
        _require_local(request)
        try:
            return await service.query_posts(
                source_config_loader(),
                username=payload.username,
                mode=payload.mode,
                query_date=payload.date,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail="X sources are temporarily unavailable") from exc

    router.add_api_route(
        "/api/v1/x/profiles",
        read_profiles,
        methods=["GET"],
        name="x_profiles_read_versioned",
    )
    router.add_api_route(
        "/api/v1/x/profiles/resolve",
        resolve_profiles,
        methods=["POST"],
        name="x_profiles_resolve_versioned",
    )
    router.add_api_route(
        "/api/v1/x/posts",
        get_posts,
        methods=["GET"],
        name="x_posts_read_versioned",
    )
    router.add_api_route(
        "/api/v1/x/posts/fetch",
        fetch_posts,
        methods=["POST"],
        name="x_posts_fetch_versioned",
    )
    router.add_api_route(
        "/api/v1/x/posts/query",
        query_posts,
        methods=["POST"],
        name="x_posts_query_versioned",
    )

    if include_legacy:
        router.add_api_route(
            "/dashboard/intel-sources/x-profiles/resolve",
            resolve_profiles,
            methods=["POST"],
            name="x_profiles_resolve_legacy",
        )
        router.add_api_route(
            "/dashboard/intel-sources/x-posts",
            get_posts,
            methods=["GET"],
            name="x_posts_read_legacy",
        )
        router.add_api_route(
            "/dashboard/intel-sources/x-posts/fetch",
            fetch_posts,
            methods=["POST"],
            name="x_posts_fetch_legacy",
        )

    return router


__all__ = ["SourceConfigLoader", "build_router"]
