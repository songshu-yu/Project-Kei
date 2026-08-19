"""Local-only, path-redacted Voice Pack lifecycle API."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .errors import (
    VoicePackConflictError,
    VoicePackManifestError,
    VoicePackNotFoundError,
    VoicePackPackageError,
    VoicePackRegistryError,
    VoicePackSwitchError,
)
from .service import VoicePackRegistryService
from .security import default_local_control_guard


class ImportVoicePackRequest(BaseModel):
    package_path: str


LocalControlGuard = Callable[[Request], bool]


def _require_write_access(request: Request, guard: LocalControlGuard) -> None:
    if not guard(request):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "voice_pack_write_forbidden",
                "message": "Voice Pack changes require a local client and trusted local Origin",
            },
        )


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, VoicePackNotFoundError):
        status = 404
    elif isinstance(exc, VoicePackConflictError):
        status = 409
    elif isinstance(exc, (VoicePackManifestError, VoicePackPackageError)):
        status = 422
    elif isinstance(exc, VoicePackSwitchError):
        status = 503
    elif isinstance(exc, VoicePackRegistryError):
        status = 500
    else:
        status = 500
    code = getattr(exc, "code", "voice_pack_error")
    raise HTTPException(status_code=status, detail={"code": code, "message": str(exc)}) from exc


def create_voice_pack_router(
    get_service: Callable[[], VoicePackRegistryService],
    *,
    local_control_guard: LocalControlGuard = default_local_control_guard,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/voice-packs", tags=["voice-packs"])

    @router.get("")
    async def list_voice_packs() -> dict:
        try:
            return await get_service().list_packs()
        except Exception as exc:
            _raise_http(exc)

    @router.post("/import")
    async def import_voice_pack(payload: ImportVoicePackRequest, request: Request) -> dict:
        _require_write_access(request, local_control_guard)
        try:
            return await get_service().import_pack(Path(payload.package_path))
        except Exception as exc:
            _raise_http(exc)

    @router.post("/{pack_id}/{version}/enable")
    async def enable_voice_pack(pack_id: str, version: str, request: Request) -> dict:
        _require_write_access(request, local_control_guard)
        try:
            return await get_service().enable(pack_id, version)
        except Exception as exc:
            _raise_http(exc)

    @router.post("/{pack_id}/{version}/select")
    async def select_voice_pack(pack_id: str, version: str, request: Request) -> dict:
        _require_write_access(request, local_control_guard)
        try:
            return await get_service().select(pack_id, version)
        except Exception as exc:
            _raise_http(exc)

    @router.post("/{pack_id}/{version}/disable")
    async def disable_voice_pack(pack_id: str, version: str, request: Request) -> dict:
        _require_write_access(request, local_control_guard)
        try:
            return await get_service().disable(pack_id, version)
        except Exception as exc:
            _raise_http(exc)

    @router.delete("/{pack_id}/{version}")
    async def unregister_voice_pack(pack_id: str, version: str, request: Request) -> dict:
        _require_write_access(request, local_control_guard)
        try:
            return await get_service().unregister(pack_id, version)
        except Exception as exc:
            _raise_http(exc)

    return router
