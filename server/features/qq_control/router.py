"""Versioned and legacy HTTP routes for the standalone QQ bridge controller."""
from __future__ import annotations

import ipaddress
import json
from typing import Callable
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .models import (
    DailyBriefingScheduleUpdate,
    LifeSupportReminderRequest,
    LifeSupportScheduleUpdate,
)
from qq_bridge.configuration import QQConfigurationError
from .repository import SchedulePersistenceError, ScheduleStateError
from .service import QQControlService

TRUSTED_ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://[::1]:8000",
}
PROTECTED_WRITES = {
    "/api/v1/qq-control/start",
    "/api/v1/qq-control/stop",
    "/api/v1/qq-control/schedules/daily-briefing",
    "/api/v1/qq-control/schedules/life-support",
    "/api/v1/qq-control/configuration",
    "/dashboard/qq-bridge/start",
    "/dashboard/qq-bridge/stop",
    "/dashboard/briefing/schedule",
    "/dashboard/life-support/schedule",
}


def is_real_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def is_trusted_origin(origin: str | None) -> bool:
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    return not parsed.path.rstrip("/") and not parsed.query and not parsed.fragment and normalized in TRUSTED_ORIGINS


def allow_loopback_read(request: Request) -> bool:
    return is_real_loopback(request) and (not request.headers.get("origin") or is_trusted_origin(request.headers.get("origin")))


def allow_control_write(request: Request) -> bool:
    return is_real_loopback(request) and is_trusted_origin(request.headers.get("origin"))


class QQControlOriginGuardMiddleware(BaseHTTPMiddleware):
    """Reject cross-site QQ control writes before permissive global CORS can answer."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PROTECTED_WRITES and request.method in {"POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
            if not allow_control_write(request):
                return JSONResponse(status_code=403, content={"detail": "local_trusted_origin_required"})
        response = await call_next(request)
        if request.url.path in PROTECTED_WRITES and response.status_code == 422:
            return JSONResponse(status_code=422, content={"detail": "invalid_request"})
        return response


def create_qq_control_router(
    service: QQControlService,
    *,
    read_guard: Callable[[Request], bool] = allow_loopback_read,
    write_guard: Callable[[Request], bool] = allow_control_write,
) -> APIRouter:
    router = APIRouter()

    def require_read(request: Request) -> None:
        if not read_guard(request):
            raise HTTPException(status_code=403, detail="local_loopback_required")

    def require_write(request: Request) -> None:
        if not write_guard(request):
            raise HTTPException(status_code=403, detail="local_trusted_origin_required")

    def read_daily():
        try:
            return service.get_daily_schedule()
        except ScheduleStateError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def read_life_support():
        try:
            return service.get_life_support_schedule()
        except ScheduleStateError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def write_daily(update: DailyBriefingScheduleUpdate):
        try:
            return service.update_daily_schedule(update)
        except ScheduleStateError as exc:
            raise HTTPException(status_code=409, detail="schedule_state_invalid") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SchedulePersistenceError as exc:
            raise HTTPException(status_code=500, detail="schedule_save_failed") from exc

    def write_life_support(update: LifeSupportScheduleUpdate):
        try:
            return service.update_life_support_schedule(update)
        except ScheduleStateError as exc:
            raise HTTPException(status_code=409, detail="schedule_state_invalid") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SchedulePersistenceError as exc:
            raise HTTPException(status_code=500, detail="schedule_save_failed") from exc

    @router.get("/api/v1/qq-control/status")
    @router.get("/dashboard/qq-bridge/status")
    async def status(request: Request):
        require_read(request)
        return service.status()

    @router.post("/api/v1/qq-control/start")
    @router.post("/dashboard/qq-bridge/start")
    async def start(request: Request):
        require_write(request)
        if (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        try:
            result = service.start()
        except OSError as exc:
            raise HTTPException(status_code=500, detail="qq_bridge_start_failed") from exc
        if not result["running"] and result["state"] != "ready":
            raise HTTPException(status_code=409, detail=result["message"])
        return result

    @router.post("/api/v1/qq-control/stop")
    @router.post("/dashboard/qq-bridge/stop")
    async def stop(request: Request):
        require_write(request)
        if (await request.body()).strip():
            raise HTTPException(status_code=422, detail="invalid_request")
        method = getattr(service, "stop", None)
        if not callable(method):
            raise HTTPException(status_code=503, detail="qq_bridge_stop_unavailable")
        try:
            result = method()
        except Exception as exc:
            raise HTTPException(status_code=500, detail="qq_bridge_stop_failed") from exc
        if result.get("stopped") is not True:
            raise HTTPException(status_code=409, detail=result.get("message", "qq_bridge_not_stopped"))
        return result

    @router.get("/api/v1/qq-control/configuration")
    async def configuration_status(request: Request):
        require_read(request)
        read_async = getattr(service, "get_configuration_async", None)
        read = getattr(service, "get_configuration", None)
        if not callable(read_async) and not callable(read):
            raise HTTPException(status_code=503, detail="configuration_unavailable")
        try:
            return await read_async() if callable(read_async) else read()
        except QQConfigurationError as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="configuration_unavailable") from exc

    @router.post("/api/v1/qq-control/configuration")
    async def update_configuration(request: Request):
        require_write(request)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="invalid_request")
        raw = await request.body()
        if not raw or len(raw) > 2048:
            raise HTTPException(status_code=422, detail="invalid_request")

        def strict_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate")
                result[key] = value
            return result

        try:
            payload = json.loads(raw, object_pairs_hook=strict_object)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="invalid_request")
        if (
            not isinstance(payload, dict)
            or not set(payload).issubset({
                "appid",
                "secret",
                "reply_with_voice",
                "qq_media_upload_capability",
                "life_forecast_enabled",
            })
            or any(
                value is not None and not isinstance(value, str)
                for key, value in payload.items()
                if key in {"appid", "secret"}
            )
            or (
                "reply_with_voice" in payload
                and not isinstance(payload["reply_with_voice"], bool)
            )
            or (
                "qq_media_upload_capability" in payload
                and not isinstance(payload["qq_media_upload_capability"], str)
            )
            or (
                "life_forecast_enabled" in payload
                and not isinstance(payload["life_forecast_enabled"], bool)
            )
        ):
            raise HTTPException(status_code=422, detail="invalid_request")
        update_async = getattr(service, "update_configuration_async", None)
        update = getattr(service, "update_configuration", None)
        if not callable(update_async) and not callable(update):
            raise HTTPException(status_code=503, detail="configuration_unavailable")
        try:
            kwargs = {
                "appid": payload.get("appid"),
                "secret": payload.get("secret"),
                "reply_with_voice": payload.get("reply_with_voice"),
                "qq_media_upload_capability": payload.get(
                    "qq_media_upload_capability"
                ),
                "life_forecast_enabled": payload.get(
                    "life_forecast_enabled"
                ),
            }
            return await update_async(**kwargs) if callable(update_async) else update(**kwargs)
        except QQConfigurationError as exc:
            status_code = 422 if exc.code in {
                "invalid_appid",
                "invalid_secret",
                "invalid_voice_setting",
                "invalid_media_capability",
                "invalid_life_forecast_setting",
                "configuration_incomplete",
            } else 409 if exc.code == "voice_unavailable" else 500
            raise HTTPException(status_code=status_code, detail=exc.code) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="configuration_save_failed") from exc

    @router.get("/api/v1/qq-control/schedules/daily-briefing")
    @router.get("/dashboard/briefing/schedule")
    async def daily_schedule(request: Request):
        require_read(request)
        return read_daily()

    @router.put("/api/v1/qq-control/schedules/daily-briefing")
    @router.put("/dashboard/briefing/schedule")
    async def update_daily(request: Request, update: DailyBriefingScheduleUpdate):
        require_write(request)
        return write_daily(update)

    @router.get("/api/v1/qq-control/schedules/life-support")
    @router.get("/dashboard/life-support/schedule")
    async def life_support_schedule(request: Request):
        require_read(request)
        return read_life_support()

    @router.put("/api/v1/qq-control/schedules/life-support")
    @router.put("/dashboard/life-support/schedule")
    async def update_life_support(request: Request, update: LifeSupportScheduleUpdate):
        require_write(request)
        return write_life_support(update)

    @router.post("/life-support/reminder")
    async def life_support_reminder(
        request: Request,
        payload: LifeSupportReminderRequest,
    ):
        require_read(request)
        generate = getattr(service, "generate_life_support_reminder", None)
        if not callable(generate):
            raise HTTPException(
                status_code=503,
                detail="life_support_reminder_unavailable",
            )
        try:
            return await generate(payload.kind)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="unsupported_reminder_kind",
            ) from exc

    return router
