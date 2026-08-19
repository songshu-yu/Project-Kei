"""Package-owned HTTP routes backed only by injected public providers."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from .domain import PAPER_SOURCE_IDS
from .projection import project_today_payload


Provider = Callable[..., Any]


async def _resolve(provider: Provider, *args: Any) -> Any:
    value = provider(*args)
    return await value if inspect.isawaitable(value) else value


async def _guard(request: Request, guard: Optional[Provider]) -> None:
    if guard is None:
        return
    if not bool(await _resolve(guard, request)):
        raise HTTPException(status_code=403, detail="local papers control only")


def create_papers_router(
    today_provider: Optional[Provider],
    refresh_provider: Optional[Provider],
    *,
    local_request_guard: Optional[Provider] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/papers", tags=["papers"])

    @router.get("/today")
    async def read_today() -> Dict[str, Any]:
        if today_provider is None:
            raise HTTPException(
                status_code=503,
                detail="papers today provider is unavailable",
            )
        return project_today_payload(await _resolve(today_provider))

    @router.post("/refresh")
    async def refresh_today(request: Request) -> Dict[str, Any]:
        await _guard(request, local_request_guard)
        if refresh_provider is None:
            raise HTTPException(
                status_code=503,
                detail="papers refresh provider is unavailable",
            )
        payload = await _resolve(refresh_provider, PAPER_SOURCE_IDS)
        return project_today_payload(payload)

    return router


__all__ = ["create_papers_router"]
