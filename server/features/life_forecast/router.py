"""Versioned HTTP boundary for daily life forecast."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import LifeForecastConfigRequest
from .service import LifeForecastError, LifeForecastService


_ERROR_STATUS = {
    "provider_disabled": 409,
    "provider_unavailable": 503,
    "configuration_invalid": 500,
    "configuration_save_failed": 500,
    "cache_save_failed": 500,
    "upstream_timeout": 504,
    "upstream_rate_limited": 429,
    "upstream_network_error": 503,
    "upstream_unavailable": 503,
}


def _call(operation):
    try:
        return operation()
    except LifeForecastError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, 502),
            detail={"code": exc.code, "message": "每日生活预报暂时不可用"},
        ) from exc


def create_life_forecast_router(service: LifeForecastService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/life-forecast", tags=["life-forecast"])

    @router.get("/today")
    def today() -> dict:
        return _call(service.get_today)

    @router.get("/config")
    def config() -> dict:
        return _call(service.get_config)

    @router.put("/config")
    def save_config(request: LifeForecastConfigRequest) -> dict:
        return _call(lambda: service.save_config(request.to_contract()))

    @router.post("/refresh")
    def refresh() -> dict:
        return _call(service.refresh)

    return router


__all__ = ["create_life_forecast_router"]
