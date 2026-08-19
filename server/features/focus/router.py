"""HTTP boundary shared by the versioned and legacy focus APIs."""

from __future__ import annotations

import base64
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request

from .models import FocusEncouragementRequest, FocusEncouragementResponse, FocusStartRequest
from .repository import FocusStateError
from .service import (
    FocusEncouragementService,
    FocusSessionInactiveError,
    FocusService,
    FocusTextGenerator,
)


AudioSynthesizer = Callable[[str], Awaitable[Optional[bytes]]]
TextGeneratorProvider = Callable[[], Optional[FocusTextGenerator]]
LocalRequestGuard = Callable[[Request], bool]


def create_focus_router(
    service: FocusService,
    audio_synthesizer: Optional[AudioSynthesizer] = None,
    *,
    text_generator_provider: Optional[TextGeneratorProvider] = None,
    local_request_guard: Optional[LocalRequestGuard] = None,
) -> APIRouter:
    router = APIRouter(tags=["focus"])
    encouragement_service = (
        FocusEncouragementService(service, text_generator_provider)
        if text_generator_provider is not None
        else None
    )

    async def status_handler() -> dict:
        try:
            return service.status().to_dict()
        except FocusStateError as exc:
            raise HTTPException(status_code=500, detail="focus_state_invalid") from exc

    async def start_handler(request: FocusStartRequest) -> dict:
        try:
            result = service.start(
                mode=request.mode,
                minutes=request.minutes,
                task=request.task,
                force=request.force,
            )
        except FocusStateError as exc:
            raise HTTPException(status_code=500, detail="focus_state_invalid") from exc
        payload = result.to_dict()
        payload["audio_base64"] = ""
        if request.with_audio and audio_synthesizer:
            audio = await audio_synthesizer(result.message)
            if audio:
                payload["audio_base64"] = base64.b64encode(audio).decode()
        return payload

    async def stop_handler() -> dict:
        try:
            return service.stop().to_dict()
        except FocusStateError as exc:
            raise HTTPException(status_code=500, detail="focus_state_invalid") from exc

    async def reset_handler() -> dict:
        try:
            return {"status": "ok", "cleared_sessions": service.reset()}
        except FocusStateError as exc:
            raise HTTPException(status_code=500, detail="focus_state_invalid") from exc

    async def encouragement_handler(
        request: Request,
        payload: FocusEncouragementRequest,
    ) -> FocusEncouragementResponse:
        if local_request_guard is not None and not local_request_guard(request):
            raise HTTPException(status_code=403, detail="local_request_required")
        if encouragement_service is None:
            return FocusEncouragementResponse(
                eligible=True,
                generated=False,
                error_code="generator_unavailable",
            )
        try:
            return await encouragement_service.generate(
                session_id=payload.session_id,
                start_at=payload.start_at,
            )
        except FocusSessionInactiveError as exc:
            raise HTTPException(status_code=409, detail="focus_session_inactive") from exc
        except FocusStateError as exc:
            raise HTTPException(status_code=500, detail="focus_state_invalid") from exc

    for route_group, prefix in (("versioned", "/api/v1/focus"), ("legacy", "/focus")):
        router.add_api_route(
            f"{prefix}/status", status_handler, methods=["GET"], name=f"focus_status_{route_group}"
        )
        router.add_api_route(
            f"{prefix}/start", start_handler, methods=["POST"], name=f"focus_start_{route_group}"
        )
        router.add_api_route(
            f"{prefix}/stop", stop_handler, methods=["POST"], name=f"focus_stop_{route_group}"
        )
        router.add_api_route(
            f"{prefix}/reset", reset_handler, methods=["POST"], name=f"focus_reset_{route_group}"
        )
    router.add_api_route(
        "/api/v1/focus/encouragement",
        encouragement_handler,
        methods=["POST"],
        response_model=FocusEncouragementResponse,
        name="focus_encouragement_versioned",
    )
    return router
