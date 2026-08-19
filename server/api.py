"""Project Kei Core API.

Only the module manager, Catalog and dashboard shell are assembled statically.
Every business route is registered from an installed, enabled module package
before the ASGI middleware stack is frozen.
"""

from __future__ import annotations

import inspect
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from core.env_loader import load_env_file, mask_env_names
from core.local_access import (
    LoopbackAccessMiddleware,
    TRUSTED_LOCAL_ORIGINS,
    is_loopback_host,
    is_trusted_local_origin,
)
from core.restart_supervisor import RestartControlClient
from features.catalog.router import router as module_catalog_router
from features.dashboard.router import (
    create_dashboard_ui_router,
    router as dashboard_shell_router,
)
from features.dashboard.ui_assets import DashboardUiAssetStore
from features.dashboard.restart_router import create_restart_router
from features.module_manager.router import router as module_lifecycle_router
from features.module_manager.service import (
    drain_module_cleanup_awaitables,
    get_module_manager,
    load_enabled_in_process_modules,
    start_enabled_sidecars,
    stop_enabled_sidecars,
    unload_enabled_in_process_modules,
)
from module_composition import InstalledModuleHost


SERVER_ROOT = Path(__file__).resolve().parent
CONTROL_DASHBOARD_PATH = SERVER_ROOT / "static" / "dashboard.html"
QQ_LAUNCH_IMAGE_PATH = SERVER_ROOT / "static" / "assets" / "qq-launch.png"
DASHBOARD_UI_ASSET_ROOT = SERVER_ROOT / "data" / "dashboard_ui" / "avatars"
ENV_FILE_PATH = Path(
    os.getenv("PROJECT_KEI_ENV_FILE", str(SERVER_ROOT / ".env"))
)
LOADED_ENV_KEYS = load_env_file(ENV_FILE_PATH)
MODULE_LOAD_RESULTS: list[dict[str, Any]] = []
SIDECAR_START_RESULTS: list[dict[str, Any]] = []


class ModuleAwareFastAPI(FastAPI):
    """Prepare installed routes immediately before Starlette freezes middleware."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._module_preparer: Optional[Callable[[], None]] = None
        self._modules_prepared = False

    def set_module_preparer(self, preparer: Callable[[], None]) -> None:
        self._module_preparer = preparer

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "lifespan" and not self._modules_prepared:
            self._modules_prepared = True
            if self._module_preparer is not None:
                self._module_preparer()
        await super().__call__(scope, receive, send)


def _request_origin(request: Request) -> str | None:
    values = request.headers.getlist("origin")
    if len(values) > 1:
        return ""
    return values[0] if values else None


def _is_local_request(request: Request) -> bool:
    return (
        request.client is not None
        and is_loopback_host(request.client.host)
        and (
            _request_origin(request) is None
            or is_trusted_local_origin(_request_origin(request))
        )
    )


def _is_local_control_request(request: Request) -> bool:
    return (
        request.client is not None
        and is_loopback_host(request.client.host)
        and _request_origin(request) in TRUSTED_LOCAL_ORIGINS
    )


async def _close_provider(provider: Any) -> None:
    close = getattr(provider, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SIDECAR_START_RESULTS
    print("=" * 50)
    print("  Project Kei Core")
    print("=" * 50)
    print(f"[Config] .env loaded keys: {mask_env_names(LOADED_ENV_KEYS)}")
    cleanup_errors = await drain_module_cleanup_awaitables(app)
    if cleanup_errors:
        print(f"[Modules] deferred cleanup failures: {len(cleanup_errors)}")
    try:
        SIDECAR_START_RESULTS = start_enabled_sidecars()
    except Exception as exc:
        SIDECAR_START_RESULTS = [{
            "module_id": "module_manager",
            "status": "failed",
            "error": type(exc).__name__,
        }]
    for result in MODULE_LOAD_RESULTS + SIDECAR_START_RESULTS:
        print(f"[Modules] {result.get('module_id')}: {result.get('status')}")
    print("[Server] Core ready: http://127.0.0.1:8000/dashboard")
    yield
    try:
        stop_enabled_sidecars()
    except Exception:
        pass
    try:
        await unload_enabled_in_process_modules(app)
    except Exception:
        pass
    await _close_provider(MODULE_HOST.asr)
    await _close_provider(MODULE_HOST.tts)


app = ModuleAwareFastAPI(
    title="Project Kei API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(TRUSTED_LOCAL_ORIGINS),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoopbackAccessMiddleware)

MODULE_HOST = InstalledModuleHost(
    SERVER_ROOT,
    local_read_guard=_is_local_request,
    local_write_guard=_is_local_control_request,
)
MODULE_HOST.configure_app_state(app)
MODULE_HOST.include_core_routes(app)

app.include_router(module_catalog_router)
app.include_router(dashboard_shell_router)
app.include_router(create_dashboard_ui_router(
    DashboardUiAssetStore(DASHBOARD_UI_ASSET_ROOT),
    local_control_guard=_is_local_control_request,
))
app.include_router(create_restart_router(
    RestartControlClient.from_environment(SERVER_ROOT),
    local_read_guard=_is_local_request,
    local_control_guard=_is_local_control_request,
))
app.include_router(module_lifecycle_router)

def _prepare_installed_modules() -> None:
    """Read the module registry only after ASGI lifespan isolation has begun."""

    global MODULE_LOAD_RESULTS
    try:
        MODULE_LOAD_RESULTS = load_enabled_in_process_modules(app)
    except Exception as exc:
        MODULE_LOAD_RESULTS = [{
            "module_id": "module_manager",
            "status": "failed",
            "error": type(exc).__name__,
        }]
    MODULE_HOST.include_enabled_sidecar_routes(app)


app.set_module_preparer(_prepare_installed_modules)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "name": "Project Kei",
        "status": "online",
        "dashboard": "/dashboard",
        "core_modules": ["module_manager", "catalog", "dashboard"],
    }


@app.get("/dashboard", include_in_schema=False)
async def dashboard() -> FileResponse:
    if not CONTROL_DASHBOARD_PATH.is_file():
        raise HTTPException(status_code=404, detail="Control dashboard is not installed")
    return FileResponse(
        CONTROL_DASHBOARD_PATH,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/dashboard/assets/qq-launch.png", include_in_schema=False)
async def dashboard_qq_launch_image() -> FileResponse:
    if not QQ_LAUNCH_IMAGE_PATH.is_file():
        raise HTTPException(status_code=404, detail="QQ launch image is not installed")
    return FileResponse(QQ_LAUNCH_IMAGE_PATH, media_type="image/png")


@app.get("/dashboard/status")
async def dashboard_status() -> Dict[str, Any]:
    failed = [
        item for item in MODULE_LOAD_RESULTS + SIDECAR_START_RESULTS
        if item.get("status") in {"failed", "rollback_failed"}
    ]
    services: Dict[str, Any] = {
        "api": {
            "ok": True,
            "status": "ok",
            "url": "http://127.0.0.1:8000",
        },
    }

    # Health cards consume the public composition seams only.  They never
    # start a process, probe an upstream LLM, or expose secret configuration.
    runtime_control = getattr(app.state, "voice_runtime_control_provider", None)
    if runtime_control is not None and callable(getattr(runtime_control, "status", None)):
        try:
            voice_status = runtime_control.status()
        except Exception:
            voice_status = {}
        for source_key, service_key, url in (
            ("asr", "asr", "http://127.0.0.1:8010/asr/transcribe"),
            ("gpt-sovits", "tts", "http://127.0.0.1:9880"),
        ):
            value = voice_status.get(source_key, {})
            running = bool(value.get("running")) if isinstance(value, dict) else False
            services[service_key] = {
                "ok": running,
                "status": value.get("state", "unavailable") if isinstance(value, dict) else "unavailable",
                "url": url,
                "error": "" if running else str(value.get("message", "") if isinstance(value, dict) else ""),
            }

    conversation_service = getattr(app.state, "conversation_service", None)
    if conversation_service is not None and callable(getattr(conversation_service, "get_profile", None)):
        try:
            profile = await conversation_service.get_profile()
            services["llm"] = {
                "configured": True,
                "status": "configured",
                "base_url": str(getattr(profile, "base_url", "")),
            }
        except Exception:
            services["llm"] = {
                "configured": False,
                "status": "unavailable",
                "error": "LLM profile is unavailable",
            }

    return {
        "status": "degraded" if failed else "ready",
        "services": services,
        "modules": {
            "load_results": MODULE_LOAD_RESULTS,
            "sidecar_results": SIDECAR_START_RESULTS,
        },
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/health/full")
async def health_full() -> Dict[str, Any]:
    return {
        "status": "ok",
        "api": {"status": "ok"},
        "module_manager": {
            "installed": len(get_module_manager().snapshot()),
            "load_results": MODULE_LOAD_RESULTS,
            "sidecar_results": SIDECAR_START_RESULTS,
        },
    }
