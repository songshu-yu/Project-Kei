"""Versioned and legacy HTTP boundary for daily briefing."""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request

from .legacy_adapter import DailyBriefingService
from .models import BriefingGenerateRequest, LifeForecastProjectionUpdate
from .repository import (
    BriefingCachePersistenceError,
    LifeForecastProjectionPersistenceError,
)


ServiceProvider = Callable[[], Optional[DailyBriefingService]]
LocalRequestGuard = Callable[[Request], bool]


def create_briefing_router(
    service_provider: ServiceProvider,
    *,
    local_request_guard: LocalRequestGuard,
) -> APIRouter:
    router = APIRouter(tags=["daily-briefing"])

    def service() -> DailyBriefingService:
        value = service_provider()
        if value is None:
            raise HTTPException(status_code=503, detail="每日情报服务尚未启动完成")
        return value

    def local_only(request: Request) -> None:
        if not local_request_guard(request):
            raise HTTPException(status_code=403, detail="This action is available only from this computer")

    def persistence_error(exc: BriefingCachePersistenceError) -> HTTPException:
        if exc.cache_state_preserved:
            detail = "每日情报保存失败，已恢复提交前缓存"
        else:
            detail = "每日情报保存失败，缓存状态无法确认，请先执行只读检查"
        return HTTPException(status_code=500, detail=detail)

    @router.get("/api/v1/briefing/today")
    async def read_today() -> dict:
        current = service()
        value = current.core.read_today()
        projection = current.core.life_forecast_projection()
        if value is None:
            return {
                "ready": False,
                "date": current.core.today().isoformat(),
                "cached": False,
                "cache_status": "unavailable",
                "counts": {},
                "items": [],
                "coverage": {},
                "warnings": [],
                "text": "",
                "script": "",
                "generated": False,
                "fallback": False,
                "life_forecast": projection,
            }
        return {
            "ready": True,
            **current.core.public_result(value),
            "life_forecast": projection,
        }

    @router.get("/api/v1/briefing/life-forecast-projection")
    async def read_life_forecast_projection(request: Request) -> dict:
        local_only(request)
        return service().core.life_forecast_projection_configuration()

    @router.put("/api/v1/briefing/life-forecast-projection")
    async def update_life_forecast_projection(
        request: Request,
        update: LifeForecastProjectionUpdate,
    ) -> dict:
        local_only(request)
        try:
            return service().core.save_life_forecast_projection_configuration(
                update
            )
        except LifeForecastProjectionPersistenceError as exc:
            raise HTTPException(
                status_code=500,
                detail="生活预报投影设置保存失败，原设置保持不变",
            ) from exc

    @router.get("/api/v1/briefing/generation-status")
    async def generation_status(request: Request) -> dict:
        local_only(request)
        return service().core.generation_status()

    async def generate(request: Request, update: BriefingGenerateRequest, *, force_refresh: bool) -> dict:
        local_only(request)
        try:
            value = await service().core.generate(
                source_ids=update.source_ids,
                refresh=force_refresh or update.refresh,
                rewrite=update.rewrite,
                rewrite_refresh=update.rewrite_refresh,
                patch_missing=update.patch_missing,
                lookback=update.lookback,
            )
            return {"ready": True, **service().core.public_result(value)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except BriefingCachePersistenceError as exc:
            raise persistence_error(exc) from exc

    @router.post("/api/v1/briefing/generate")
    async def generate_today(request: Request, update: BriefingGenerateRequest) -> dict:
        return await generate(request, update, force_refresh=False)

    @router.post("/api/v1/briefing/refresh")
    async def refresh_today(request: Request, update: BriefingGenerateRequest) -> dict:
        return await generate(request, update, force_refresh=True)

    @router.get("/api/v1/briefing/today/script")
    async def read_today_script() -> dict:
        return service().load_current_summary()

    @router.get("/briefing/today")
    async def legacy_today(
        fetch: bool = False,
        rewrite: bool = False,
        date: Optional[str] = None,
        cache: bool = True,
        refresh: bool = False,
        rewrite_refresh: bool = False,
    ) -> dict:
        try:
            result = await service().build(
                target_date=date,
                fetch=fetch,
                rewrite=rewrite,
                synthesize=False,
                use_cache=cache,
                refresh=refresh,
                rewrite_refresh=rewrite_refresh,
            )
            return vars(result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except BriefingCachePersistenceError as exc:
            raise persistence_error(exc) from exc

    @router.post("/briefing/today/voice")
    async def legacy_voice(
        fetch: bool = False,
        rewrite: bool = True,
        date: Optional[str] = None,
        cache: bool = True,
        refresh: bool = False,
        rewrite_refresh: bool = False,
    ) -> dict:
        try:
            result = await service().build(
                target_date=date,
                fetch=fetch,
                rewrite=rewrite,
                synthesize=True,
                use_cache=cache,
                refresh=refresh,
                rewrite_refresh=rewrite_refresh,
            )
            return vars(result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except BriefingCachePersistenceError as exc:
            raise persistence_error(exc) from exc

    @router.post("/dashboard/briefing/generate")
    async def dashboard_generate(request: Request, refresh: bool = False) -> dict:
        local_only(request)
        try:
            result = await service().build(
                fetch=True,
                rewrite=True,
                synthesize=False,
                use_cache=True,
                refresh=refresh,
                rewrite_refresh=refresh,
            )
        except BriefingCachePersistenceError as exc:
            raise persistence_error(exc) from exc
        return {
            "date": result.date,
            "cached": result.cached,
            "counts": result.counts,
            "coverage": result.coverage,
            "warnings": result.warnings,
            "refresh_status": result.refresh_status,
            "refresh_message": result.refresh_message,
            "message": result.refresh_message or "Today's briefing is ready",
        }

    @router.get("/dashboard/briefing/status")
    async def dashboard_status(request: Request) -> dict:
        local_only(request)
        return service().status()

    return router


__all__ = ["create_briefing_router"]
