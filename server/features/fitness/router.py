"""HTTP boundary shared by versioned and legacy fitness APIs."""

from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request

from .models import (
    FitnessCheckinRequest,
    FitnessCheckinResponse,
    FitnessResetResponse,
    FitnessStatusResponse,
    LegacyFitnessCheckinRequest,
    LegacyFitnessCheckinResponse,
)
from .repository import FitnessPersistenceError, FitnessStateError
from .security import default_local_control_guard
from .service import FitnessService


AudioSynthesizer = Callable[[str, str], Awaitable[Optional[bytes]]]
LocalControlGuard = Callable[[Request], bool]


def _invoke(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FitnessStateError as exc:
        raise HTTPException(status_code=500, detail="fitness state is invalid") from exc
    except FitnessPersistenceError as exc:
        raise HTTPException(status_code=500, detail="fitness state could not be saved") from exc


def _require_local(request: Request, guard: LocalControlGuard) -> None:
    if not guard(request):
        raise HTTPException(status_code=403, detail="fitness access is local-only")


def create_fitness_router(
    service: FitnessService,
    *,
    audio_synthesizer: AudioSynthesizer | None = None,
    local_control_guard: LocalControlGuard = default_local_control_guard,
    local_read_guard: LocalControlGuard | None = None,
) -> APIRouter:
    router = APIRouter(tags=["fitness"])

    async def status_handler(request: Request, date: Optional[str] = None) -> dict:
        _require_local(request, local_read_guard or local_control_guard)
        return _invoke(lambda: service.get_status(date))

    async def versioned_checkin_handler(request: Request, payload: FitnessCheckinRequest) -> dict:
        _require_local(request, local_control_guard)
        return _invoke(lambda: service.check_in(payload.date, payload.note)).to_dict()

    async def legacy_checkin_handler(request: Request, payload: LegacyFitnessCheckinRequest) -> dict:
        _require_local(request, local_control_guard)
        result = _invoke(lambda: service.check_in(payload.date, payload.note))
        response = result.to_dict()
        response["audio_base64"] = ""
        if result.reward_unlocked and payload.with_audio and audio_synthesizer is not None:
            try:
                audio = await audio_synthesizer(result.reward_text, "happy")
            except Exception:
                audio = None
            if audio:
                response["audio_base64"] = base64.b64encode(audio).decode("ascii")
        return response

    async def legacy_reset_handler(request: Request) -> dict:
        _require_local(request, local_control_guard)
        checkins, rewards = _invoke(service.reset)
        return {"status": "ok", "cleared_checkins": checkins, "cleared_rewards": rewards}

    router.add_api_route(
        "/api/v1/fitness/status",
        status_handler,
        methods=["GET"],
        response_model=FitnessStatusResponse,
        name="fitness_status_versioned",
    )
    router.add_api_route(
        "/api/v1/fitness/checkins",
        versioned_checkin_handler,
        methods=["POST"],
        response_model=FitnessCheckinResponse,
        name="fitness_checkin_versioned",
    )
    router.add_api_route(
        "/fitness/status",
        status_handler,
        methods=["GET"],
        response_model=FitnessStatusResponse,
        name="fitness_status_legacy",
    )
    router.add_api_route(
        "/fitness/checkin",
        legacy_checkin_handler,
        methods=["POST"],
        response_model=LegacyFitnessCheckinResponse,
        name="fitness_checkin_legacy",
    )
    router.add_api_route(
        "/fitness/reset",
        legacy_reset_handler,
        methods=["POST"],
        response_model=FitnessResetResponse,
        name="fitness_reset_legacy",
    )
    return router


__all__ = ["create_fitness_router"]
