"""Path-free loopback API for explicit GPT-SoVITS folder selection."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core.local_access import (
    TRUSTED_LOCAL_ORIGINS,
    is_loopback_host,
    is_trusted_local_origin,
)

from .local_selection import EngineSelectionError, LocalEngineSelectionService


RequestGuard = Callable[[Request], bool]


def _request_origin(request: Request) -> Optional[str]:
    values = request.headers.getlist("origin")
    if len(values) > 1:
        return ""
    return values[0] if values else None


def local_read_guard(request: Request) -> bool:
    client = request.client
    return bool(
        client is not None
        and is_loopback_host(client.host)
        and is_trusted_local_origin(_request_origin(request))
    )


def local_write_guard(request: Request) -> bool:
    client = request.client
    return bool(
        client is not None
        and is_loopback_host(client.host)
        and _request_origin(request) in TRUSTED_LOCAL_ORIGINS
    )


def _http_error(exc: EngineSelectionError) -> HTTPException:
    if exc.code == "selection_in_progress":
        status_code = 409
    elif exc.code == "picker_unavailable":
        status_code = 503
    elif exc.code == "local_config_write_failed":
        status_code = 500
    else:
        status_code = 422
    return HTTPException(status_code=status_code, detail=exc.to_public_dict())


def create_gpt_sovits_engine_router(
    service: LocalEngineSelectionService,
    *,
    read_guard: RequestGuard = local_read_guard,
    write_guard: RequestGuard = local_write_guard,
) -> APIRouter:
    router = APIRouter(tags=["gpt-sovits-engine"])

    @router.get("/api/v1/gpt-sovits-engine/status")
    async def status(request: Request) -> Dict[str, Any]:
        if not read_guard(request):
            raise HTTPException(status_code=403, detail="local_loopback_required")
        if request.url.query:
            raise HTTPException(status_code=422, detail="invalid_request")
        return await run_in_threadpool(service.status)

    @router.post("/api/v1/gpt-sovits-engine/select-existing")
    async def select_existing(request: Request) -> Dict[str, Any]:
        if not write_guard(request):
            raise HTTPException(status_code=403, detail="local_trusted_origin_required")
        if request.url.query or (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        try:
            return await run_in_threadpool(service.select_existing_install)
        except EngineSelectionError as exc:
            raise _http_error(exc) from exc

    return router


__all__ = [
    "create_gpt_sovits_engine_router",
    "local_read_guard",
    "local_write_guard",
]
