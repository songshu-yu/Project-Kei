"""HTTP boundary shared by versioned and legacy calendar APIs."""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException

from .models import CalendarEventRequest, CalendarResetRequest, PracticeLogRequest
from .repository import CalendarPersistenceError, CalendarStateError
from .service import CalendarService


def _invoke(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CalendarStateError as exc:
        raise HTTPException(status_code=500, detail="calendar state is invalid") from exc
    except CalendarPersistenceError as exc:
        raise HTTPException(status_code=500, detail="calendar state could not be saved") from exc


def create_calendar_router(service: CalendarService) -> APIRouter:
    router = APIRouter(tags=["calendar"])

    async def today_handler(date: Optional[str] = None) -> dict:
        return _invoke(lambda: service.today_summary(date))

    async def status_handler(date: Optional[str] = None) -> dict:
        return _invoke(lambda: service.get_status(date))

    async def event_handler(request: CalendarEventRequest) -> dict:
        event = _invoke(lambda: service.add_event(
            request.title,
            request.date,
            repeat=request.repeat,
            note=request.note,
            tags=request.tags,
        ))
        return {"status": "ok", "event": event}

    async def practice_handler(request: PracticeLogRequest) -> dict:
        return _invoke(lambda: service.add_practice(
            request.skill,
            request.hours,
            day=request.date,
            note=request.note,
        ))

    async def versioned_reset_handler(request: CalendarResetRequest) -> dict:
        if request.confirmation != "calendar":
            raise HTTPException(status_code=422, detail="confirmation must exactly match 'calendar'")
        return {"status": "ok", "cleared": _invoke(service.reset)}

    async def legacy_reset_handler() -> dict:
        return {"status": "ok", "cleared": _invoke(service.reset)}

    for group, prefix, event_path in (
        ("versioned", "/api/v1/calendar", "events"),
        ("legacy", "/calendar", "event"),
    ):
        router.add_api_route(f"{prefix}/today", today_handler, methods=["GET"], name=f"calendar_today_{group}")
        router.add_api_route(f"{prefix}/status", status_handler, methods=["GET"], name=f"calendar_status_{group}")
        router.add_api_route(f"{prefix}/{event_path}", event_handler, methods=["POST"], name=f"calendar_event_{group}")
        router.add_api_route(f"{prefix}/practice", practice_handler, methods=["POST"], name=f"calendar_practice_{group}")
    router.add_api_route("/api/v1/calendar/reset", versioned_reset_handler, methods=["POST"], name="calendar_reset_versioned")
    router.add_api_route("/calendar/reset", legacy_reset_handler, methods=["POST"], name="calendar_reset_legacy")
    return router


__all__ = ["create_calendar_router"]
