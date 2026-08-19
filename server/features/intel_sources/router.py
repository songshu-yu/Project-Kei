"""Versioned local-control HTTP boundary for the PK-115 source registry."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from .repository import IntelSourcePersistenceError, IntelSourceStateError
from .service import IntelSourceRegistry


LocalControlGuard = Callable[[Request], bool]


class SourceTargetUpdate(BaseModel):
    value: Any


class LegacyIntelSourcesUpdate(BaseModel):
    twitter_users: Optional[list] = None
    money_twitter_users: Optional[list] = None
    github_users: Optional[list] = None
    github_repos: Optional[list] = None
    bilibili_uids: Optional[list] = None
    youtube_channel_ids: Optional[list] = None
    paper_priority_authors: Optional[list] = None
    paper_secondary_authors: Optional[list] = None
    paper_ai_authors: Optional[list] = None


def _legacy_update_payload(update: LegacyIntelSourcesUpdate) -> Dict[str, Any]:
    if hasattr(update, "model_dump"):
        return update.model_dump(exclude_none=True)
    return update.dict(exclude_none=True)


def create_intel_sources_router(
    registry: IntelSourceRegistry,
    *,
    local_control_guard: LocalControlGuard,
    local_read_guard: Optional[LocalControlGuard] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/intel-sources", tags=["intel-sources"])

    read_guard = local_read_guard or local_control_guard

    def require_read(request: Request) -> None:
        if not read_guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    def require_control(request: Request) -> None:
        if not local_control_guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    @router.get("")
    async def read_sources(request: Request) -> Dict[str, Any]:
        require_read(request)
        return registry.read()

    @router.put("")
    async def replace_sources(
        request: Request,
        payload: Dict[str, Any] = Body(...),
    ) -> Dict[str, Any]:
        require_control(request)
        try:
            return registry.replace(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IntelSourcePersistenceError as exc:
            raise HTTPException(status_code=500, detail="Source registry could not be saved") from exc

    @router.post("/{field}")
    async def add_source(
        field: str,
        update: SourceTargetUpdate,
        request: Request,
    ) -> Dict[str, Any]:
        require_control(request)
        try:
            return registry.add(field, update.value)
        except (ValueError, IntelSourceStateError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IntelSourcePersistenceError as exc:
            raise HTTPException(status_code=500, detail="Source registry could not be saved") from exc

    @router.put("/{field}/{index}")
    async def update_source(
        field: str,
        index: int,
        update: SourceTargetUpdate,
        request: Request,
    ) -> Dict[str, Any]:
        require_control(request)
        try:
            return registry.update(field, index, update.value)
        except (ValueError, IntelSourceStateError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IntelSourcePersistenceError as exc:
            raise HTTPException(status_code=500, detail="Source registry could not be saved") from exc

    @router.delete("/{field}/{index}")
    async def remove_source(field: str, index: int, request: Request) -> Dict[str, Any]:
        require_control(request)
        try:
            return registry.remove(field, index)
        except (ValueError, IntelSourceStateError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IntelSourcePersistenceError as exc:
            raise HTTPException(status_code=500, detail="Source registry could not be saved") from exc

    return router


def create_legacy_intel_sources_router(
    registry: IntelSourceRegistry,
    *,
    local_control_guard: LocalControlGuard,
    local_read_guard: Optional[LocalControlGuard] = None,
) -> APIRouter:
    """Keep the dashboard compatibility API on the exact same registry."""
    router = APIRouter(prefix="/dashboard/intel-sources", tags=["intel-sources-legacy"])

    read_guard = local_read_guard or local_control_guard

    def require_read(request: Request) -> None:
        if not read_guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    def require_control(request: Request) -> None:
        if not local_control_guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    @router.get("")
    async def read_sources(request: Request) -> Dict[str, Any]:
        require_read(request)
        return registry.read()

    @router.put("")
    async def replace_sources(
        request: Request,
        update: LegacyIntelSourcesUpdate,
    ) -> Dict[str, Any]:
        require_control(request)
        current = registry.read()
        payload = {
            field: current[field]
            for field in registry_source_fields()
        }
        payload.update(_legacy_update_payload(update))
        try:
            return registry.replace(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except IntelSourcePersistenceError as exc:
            raise HTTPException(status_code=500, detail="Source registry could not be saved") from exc

    return router


def registry_source_fields() -> tuple[str, ...]:
    # Local import keeps router construction independent from persistence.
    from .models import SOURCE_FIELDS

    return SOURCE_FIELDS


__all__ = [
    "LegacyIntelSourcesUpdate",
    "LocalControlGuard",
    "SourceTargetUpdate",
    "create_intel_sources_router",
    "create_legacy_intel_sources_router",
]
