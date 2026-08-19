"""Local same-origin dashboard contract for requesting a Core restart."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response

from core.restart_supervisor import RestartControlClient


LocalControlGuard = Callable[[Request], bool]


def create_restart_router(
    client: RestartControlClient,
    *,
    local_read_guard: LocalControlGuard,
    local_control_guard: LocalControlGuard,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/dashboard/service", tags=["dashboard-shell"])

    def require_local_same_origin(request: Request) -> None:
        if not local_control_guard(request):
            raise HTTPException(status_code=403, detail="Service control is available only from the local dashboard")

    @router.get("/restart/status")
    async def restart_status(request: Request, response: Response) -> dict:
        if not local_read_guard(request):
            raise HTTPException(status_code=403, detail="Service status is available only on this device")
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return client.status()

    @router.post("/restart", status_code=202)
    async def restart_core(request: Request, response: Response) -> dict:
        require_local_same_origin(request)
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if media_type != "application/json":
            raise HTTPException(status_code=415, detail="Service restart requires application/json")
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="A restart confirmation object is required") from exc
        if not isinstance(body, dict) or set(body) != {"confirmation"} or not isinstance(body["confirmation"], str):
            raise HTTPException(status_code=400, detail="Only the restart confirmation field is accepted")
        result = client.request_restart(body["confirmation"])
        response.status_code = result.status_code
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return result.payload

    return router


__all__ = ["create_restart_router"]
