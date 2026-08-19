"""Restart-time registration for installable Voice Pack distribution."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException, Request

from .catalog import CatalogError, VoicePackCatalog
from .downloader import HTTPSDownloader
from .errors import DistributionError
from .service import VoicePackDistributionService


API_PREFIX = "/api/v1/voice-pack-distribution"
_TRUSTED_ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://[::1]:8000",
}


def _server_root() -> Path:
    source = Path(__file__).resolve()
    for parent in source.parents:
        if parent.name == "server":
            return parent
    return source.parents[4]


def _existing_routes(app: Any) -> bool:
    return any(
        getattr(route, "path", "") == API_PREFIX
        or getattr(route, "path", "").startswith(API_PREFIX + "/")
        for route in getattr(app, "routes", ())
    )


def _default_local_guard(request: Request) -> None:
    host = (request.client.host if request.client else "").lower()
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="local control is required")
    origin = request.headers.get("origin")
    if origin is None:
        return
    parsed = urlparse(origin)
    normalized = (
        f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        if parsed.hostname and parsed.port
        else ""
    )
    if normalized not in _TRUSTED_ORIGINS:
        raise HTTPException(status_code=403, detail="trusted local origin is required")


async def _guard(
    request: Request,
    candidate: Callable[[Request], Any],
) -> None:
    result = candidate(request)
    if inspect.isawaitable(result):
        await result


def _error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "voice_pack_distribution_failed")
    return HTTPException(
        status_code=400,
        detail={"code": code, "message": str(exc)},
    )


def create_router(
    service: VoicePackDistributionService,
    *,
    local_guard: Callable[[Request], Any],
) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["voice-pack-distribution"])

    @router.get("/releases")
    async def releases() -> Dict[str, Any]:
        try:
            return await service.list()
        except (CatalogError, DistributionError) as exc:
            raise _error(exc) from exc

    @router.get("/status/{key}")
    async def status(key: str) -> Dict[str, Any]:
        try:
            return await service.status(key)
        except (CatalogError, DistributionError) as exc:
            raise _error(exc) from exc

    @router.get("/verify/{key}")
    async def verify(key: str) -> Dict[str, Any]:
        try:
            return await service.verify(key)
        except Exception as exc:
            raise _error(exc) from exc

    @router.post("/install")
    async def install(
        request: Request,
        payload: Dict[str, Any] = Body(...),
    ) -> Dict[str, Any]:
        await _guard(request, local_guard)
        try:
            key = str(payload.get("key") or "")
            confirmation = str(payload.get("confirmation") or "")
            if payload.get("download_only"):
                return await service.download_only(key, confirmation=confirmation)
            return await service.install(
                key,
                confirmation=confirmation,
                select=payload.get("select"),
            )
        except Exception as exc:
            raise _error(exc) from exc

    @router.post("/import")
    async def import_local(
        request: Request,
        payload: Dict[str, Any] = Body(...),
    ) -> Dict[str, Any]:
        await _guard(request, local_guard)
        try:
            source = payload.get("source")
            if not isinstance(source, str) or not source.strip():
                raise DistributionError(
                    "local import requires an explicit path",
                    code="voice_pack_local_source_invalid",
                )
            return await service.import_local(
                Path(source),
                expected_key=payload.get("expected_key"),
                expected_sha256=payload.get("expected_sha256"),
            )
        except Exception as exc:
            raise _error(exc) from exc

    @router.post("/select")
    async def select(
        request: Request,
        payload: Dict[str, Any] = Body(...),
    ) -> Dict[str, Any]:
        await _guard(request, local_guard)
        try:
            return await service.select(str(payload.get("key") or ""))
        except Exception as exc:
            raise _error(exc) from exc

    return router


def _activate(app: Any, registry_service: Any) -> None:
    if getattr(app.state, "voice_pack_distribution_module_registered", False):
        return
    package_root = Path(__file__).resolve().parent.parent
    catalog_root = package_root / "catalog"
    cache_root = Path(
        getattr(
            app.state,
            "voice_pack_distribution_cache_root",
            _server_root() / "data" / "voice_pack_distribution" / "downloads",
        )
    )
    downloader = getattr(app.state, "voice_pack_distribution_downloader", None)
    engine_status = getattr(app.state, "voice_pack_engine_status", None)
    local_guard = getattr(
        app.state,
        "voice_pack_local_control_guard",
        _default_local_guard,
    )
    service = VoicePackDistributionService(
        catalog=VoicePackCatalog.load(catalog_root),
        registry_service=registry_service,
        cache_root=cache_root,
        downloader=downloader or HTTPSDownloader(),
        engine_status=engine_status,
    )
    app.include_router(create_router(service, local_guard=local_guard))
    app.state.voice_pack_distribution_service = service
    app.state.voice_pack_distribution_module_registered = True
    app.state.voice_pack_distribution_module_mode = "installable"


def register(app: Any) -> None:
    """Register once using PK-212's frozen, path-free app.state service seam."""
    if getattr(app.state, "voice_pack_distribution_module_registered", False):
        return
    if _existing_routes(app):
        app.state.voice_pack_distribution_module_registered = True
        app.state.voice_pack_distribution_module_mode = "existing_routes"
        return
    registry_service = getattr(app.state, "voice_pack_registry_service", None)
    if registry_service is not None:
        _activate(app, registry_service)
        return

    previous_consumer = getattr(app.state, "voice_pack_resolver_consumer", None)

    def bind_registry(candidate: Any) -> None:
        if callable(previous_consumer):
            previous_consumer(candidate)
        _activate(app, candidate)

    app.state.voice_pack_resolver_consumer = bind_registry
    app.state.voice_pack_distribution_module_registered = False
    app.state.voice_pack_distribution_module_mode = "dependency_unavailable"
