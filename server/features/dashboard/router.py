"""Static assets owned by the dashboard public shell."""

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

from .ui_assets import (
    DashboardUiAssetError,
    DashboardUiAssetStore,
    DashboardUiAvatar,
    MAX_AVATAR_BYTES,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard-shell"])
DASHBOARD_ASSET_ROOT = Path(__file__).resolve().parents[2] / "static" / "dashboard"
LocalControlGuard = Callable[[Request], bool]


@router.get("/static/{asset_path:path}", include_in_schema=False)
async def dashboard_static_asset(asset_path: str) -> FileResponse:
    """Serve only files inside the dashboard shell's public asset directory."""
    root = DASHBOARD_ASSET_ROOT.resolve()
    target = (root / asset_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Dashboard asset not found") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Dashboard asset not found")
    return FileResponse(
        target,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _avatar_payload(record: DashboardUiAvatar) -> dict:
    return {
        "panel_id": record.panel_id,
        "url": f"/api/v1/dashboard/ui-assets/{record.panel_id}/avatar",
        "content_type": record.content_type,
        "size": record.size,
        "updated_at": record.updated_at,
    }


def create_dashboard_ui_router(
    store: DashboardUiAssetStore,
    *,
    local_control_guard: LocalControlGuard,
) -> APIRouter:
    ui_router = APIRouter(prefix="/api/v1/dashboard/ui-assets", tags=["dashboard-shell"])

    def require_local_control(request: Request) -> None:
        if not local_control_guard(request):
            raise HTTPException(status_code=403, detail="Dashboard UI assets are local-only")

    @ui_router.get("")
    async def list_dashboard_ui_assets(request: Request, response: Response) -> dict:
        require_local_control(request)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return {"avatars": [_avatar_payload(record) for record in store.list()]}

    @ui_router.get("/{panel_id}/avatar", include_in_schema=False)
    async def get_dashboard_avatar(panel_id: str, request: Request) -> FileResponse:
        require_local_control(request)
        try:
            record = store.get(panel_id)
        except DashboardUiAssetError as exc:
            raise HTTPException(status_code=404, detail="Dashboard avatar not found") from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Dashboard avatar not found")
        return FileResponse(
            record.path,
            media_type=record.content_type,
            headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
        )

    @ui_router.put("/{panel_id}/avatar")
    async def put_dashboard_avatar(panel_id: str, request: Request) -> dict:
        require_local_control(request)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_AVATAR_BYTES:
                    raise HTTPException(status_code=413, detail="Dashboard avatar is too large")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc

        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_AVATAR_BYTES:
                raise HTTPException(status_code=413, detail="Dashboard avatar is too large")
            chunks.append(chunk)
        try:
            record = store.save(
                panel_id,
                request.headers.get("content-type", ""),
                b"".join(chunks),
            )
        except DashboardUiAssetError as exc:
            message = str(exc)
            status = 415 if "type" in message else 400
            raise HTTPException(status_code=status, detail=message) from exc
        return _avatar_payload(record)

    @ui_router.delete("/{panel_id}/avatar")
    async def delete_dashboard_avatar(panel_id: str, request: Request) -> dict:
        require_local_control(request)
        try:
            deleted = store.delete(panel_id)
        except DashboardUiAssetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"panel_id": panel_id, "deleted": deleted}

    return ui_router


__all__ = [
    "DASHBOARD_ASSET_ROOT",
    "create_dashboard_ui_router",
    "dashboard_static_asset",
    "router",
]
