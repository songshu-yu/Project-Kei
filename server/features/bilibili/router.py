"""Versioned PK-130 profile router used by the main application composition."""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request

from .credentials import BilibiliCredentialPersistenceError
from .models import BilibiliCredentialUpdate, BilibiliProfileResolveRequest
from .service import BilibiliCredentialValidationError, BilibiliService


LocalRequestGuard = Callable[[Request], bool]


def create_bilibili_router(
    service: BilibiliService,
    *,
    local_request_guard: LocalRequestGuard,
    local_read_guard: Optional[LocalRequestGuard] = None,
) -> APIRouter:
    """Create local-only versioned routes without importing ``server.api``."""
    router = APIRouter(tags=["bilibili"])

    read_guard = local_read_guard or local_request_guard

    def require_read(request: Request) -> None:
        if not read_guard(request):
            raise HTTPException(
                status_code=403,
                detail="This action is available only from this computer",
            )

    def require_control(request: Request) -> None:
        if not local_request_guard(request):
            raise HTTPException(
                status_code=403,
                detail="This action is available only from this computer",
            )

    @router.get("/api/v1/bilibili/profiles")
    async def read_profiles(request: Request, uid: Optional[int] = None) -> dict:
        require_read(request)
        try:
            return service.read_profiles(uid)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/v1/bilibili/profiles/resolve")
    async def resolve_profiles(
        payload: BilibiliProfileResolveRequest,
        request: Request,
    ) -> dict:
        require_control(request)
        try:
            return await service.resolve_profiles(payload.uid, refresh=payload.refresh)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Bilibili profile cache could not be saved") from exc

    def status_result() -> dict:
        return service.credential_status()

    async def save_result(payload: BilibiliCredentialUpdate) -> dict:
        try:
            return await service.save_credentials(payload.dict())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except BilibiliCredentialPersistenceError as exc:
            raise HTTPException(
                status_code=500,
                detail="B 站参数未保存，原有配置保持不变。",
            ) from exc

    async def collect_result() -> dict:
        try:
            return await service.validate_and_collect()
        except BilibiliCredentialValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail=exc.message,
            ) from exc
        except BilibiliCredentialPersistenceError as exc:
            raise HTTPException(
                status_code=500,
                detail="B 站参数状态未能原子更新，原有缓存保持不变。",
            ) from exc

    @router.get("/api/v1/bilibili/credentials/status")
    async def read_credentials(request: Request) -> dict:
        require_read(request)
        return status_result()

    @router.put("/api/v1/bilibili/credentials")
    async def save_credentials(
        payload: BilibiliCredentialUpdate,
        request: Request,
    ) -> dict:
        require_control(request)
        return await save_result(payload)

    @router.post("/api/v1/bilibili/credentials/validate-and-collect")
    async def validate_and_collect(request: Request) -> dict:
        require_control(request)
        return await collect_result()

    @router.get("/dashboard/intel-sources/bilibili-credentials/status")
    async def legacy_read_credentials(request: Request) -> dict:
        require_read(request)
        return status_result()

    @router.put("/dashboard/intel-sources/bilibili-credentials")
    async def legacy_save_credentials(
        payload: BilibiliCredentialUpdate,
        request: Request,
    ) -> dict:
        require_control(request)
        return await save_result(payload)

    @router.post("/dashboard/intel-sources/bilibili-credentials/validate-and-collect")
    async def legacy_validate_and_collect(request: Request) -> dict:
        require_control(request)
        return await collect_result()

    return router


__all__ = ["LocalRequestGuard", "create_bilibili_router"]
