"""Local-only lifecycle routes for trusted module packages."""

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.local_access import is_loopback_host, is_trusted_local_origin
from core.modules.exceptions import (
    ManifestValidationError,
    ModuleConflictError,
    ModuleNotFoundError,
    ModuleOperationError,
    PackageValidationError,
    RegistryError,
    SidecarReadinessError,
)
from core.modules.official_catalog import OfficialCatalogError
from .models import InstallModuleRequest, OfficialModuleRequest, PurgeModuleDataRequest
from .service import get_module_manager, get_official_module_service


router = APIRouter(prefix="/api/v1/modules", tags=["module-lifecycle"])

LOCAL_MODULE_UPLOAD_MAX_BYTES = 64 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_UPLOAD_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


def _require_local(request: Request) -> None:
    if (
        request.client is None
        or not is_loopback_host(request.client.host)
        or not is_trusted_local_origin(request.headers.get("origin"))
    ):
        raise HTTPException(status_code=403, detail="This action is available only from this computer")


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, OfficialCatalogError):
        if exc.code in {"official_module_not_found", "official_module_not_installed"}:
            status = 404
        elif exc.code in {
            "official_module_confirmation_required",
            "official_module_conflict",
        }:
            status = 409
        elif exc.code == "official_github_rate_limited":
            status = 429
        elif exc.code in {
            "official_catalog_refresh_failed",
            "official_module_download_failed",
        }:
            status = 502
        elif exc.code == "official_module_download_timeout":
            status = 504
        elif exc.code == "official_module_install_failed":
            status = 500
        elif exc.code in {
            "official_catalog_unavailable",
            "official_catalog_cache_invalid",
        }:
            status = 503
        else:
            status = 422
        raise HTTPException(status_code=status, detail=exc.detail()) from exc
    if isinstance(exc, SidecarReadinessError):
        raise HTTPException(status_code=409, detail=exc.detail()) from exc
    if isinstance(exc, ModuleNotFoundError):
        status = 404
    elif isinstance(exc, ModuleConflictError):
        status = 409
    elif isinstance(exc, (ManifestValidationError, PackageValidationError)):
        status = 422
    elif isinstance(exc, (RegistryError, ModuleOperationError)):
        status = 500
    else:
        status = 500
    raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/official-catalog")
async def official_catalog(request: Request) -> dict:
    _require_local(request)
    try:
        return get_official_module_service().list_catalog()
    except Exception as exc:
        _raise_http(exc)


@router.post("/official-catalog/refresh")
async def refresh_official_catalog(request: Request) -> dict:
    _require_local(request)
    try:
        return get_official_module_service().refresh_catalog()
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/install-official")
async def install_official_module(
    module_id: str,
    payload: OfficialModuleRequest,
    request: Request,
) -> dict:
    _require_local(request)
    try:
        return get_official_module_service().install(
            module_id,
            payload.version,
            payload.confirmation,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/update-official")
async def update_official_module(
    module_id: str,
    payload: OfficialModuleRequest,
    request: Request,
) -> dict:
    _require_local(request)
    try:
        return get_official_module_service().update(
            module_id,
            payload.version,
            payload.confirmation,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/rollback-official")
async def rollback_official_module(
    module_id: str,
    payload: OfficialModuleRequest,
    request: Request,
) -> dict:
    _require_local(request)
    try:
        return get_official_module_service().rollback(
            module_id,
            payload.version,
            payload.confirmation,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/install")
async def install_module(module_id: str, payload: InstallModuleRequest, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().install(
            Path(payload.package_path), payload.expected_sha256, expected_module_id=module_id
        )
    except Exception as exc:
        _raise_http(exc)


def _normalize_expected_upload_module_id(module_id: Optional[str]) -> Optional[str]:
    normalized = module_id.strip() if module_id is not None else ""
    if not normalized:
        return None
    if not _MODULE_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "local_module_upload_module_id_invalid",
                "message": "module id is invalid",
            },
        )
    return normalized


async def _install_uploaded_module(
    request: Request,
    requested_module_id: Optional[str],
) -> dict:
    """Stream a browser-selected ZIP into an isolated temporary file, then install it."""

    _require_local(request)
    expected_module_id = _normalize_expected_upload_module_id(requested_module_id)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/zip":
        raise HTTPException(
            status_code=415,
            detail={
                "code": "local_module_upload_content_type_invalid",
                "message": "local module upload must use application/zip",
            },
        )
    expected_sha256 = request.headers.get("x-project-kei-package-sha256", "").strip()
    if not _SHA256_PATTERN.fullmatch(expected_sha256):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "local_module_upload_sha256_required",
                "message": "a 64-character package SHA-256 header is required",
            },
        )
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "local_module_upload_length_invalid",
                    "message": "Content-Length is invalid",
                },
            ) from exc
        if declared_length < 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "local_module_upload_empty",
                    "message": "local module ZIP is empty",
                },
            )
        if declared_length > LOCAL_MODULE_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "local_module_upload_too_large",
                    "message": "local module ZIP exceeds the 64 MiB limit",
                },
            )

    try:
        with _UPLOAD_TEMPORARY_DIRECTORY(prefix="project-kei-module-upload-") as temp_dir:
            package_path = Path(temp_dir) / "module.zip"
            digest = hashlib.sha256()
            received_bytes = 0
            with package_path.open("wb") as handle:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    received_bytes += len(chunk)
                    if received_bytes > LOCAL_MODULE_UPLOAD_MAX_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "code": "local_module_upload_too_large",
                                "message": "local module ZIP exceeds the 64 MiB limit",
                            },
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if received_bytes == 0:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "local_module_upload_empty",
                        "message": "local module ZIP is empty",
                    },
                )
            actual_sha256 = digest.hexdigest()
            if actual_sha256 != expected_sha256.lower():
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "local_module_upload_integrity_mismatch",
                        "message": "uploaded ZIP SHA-256 does not match the browser digest",
                    },
                )
            result = get_module_manager().install(
                package_path,
                actual_sha256,
                expected_module_id=expected_module_id,
            )
            return {
                **result,
                "local_upload": {
                    "status": "success",
                    "received_bytes": received_bytes,
                    "sha256": actual_sha256,
                },
            }
    except HTTPException:
        raise
    except (
        ManifestValidationError,
        ModuleConflictError,
        ModuleNotFoundError,
        ModuleOperationError,
        PackageValidationError,
        RegistryError,
        SidecarReadinessError,
    ) as exc:
        _raise_http(exc)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "local_module_upload_failed",
                "message": "local module upload failed before installation completed",
            },
        ) from exc


@router.post("/install-upload")
async def install_uploaded_module_from_manifest(
    request: Request,
    expected_module_id: Optional[str] = None,
) -> dict:
    """Install a ZIP using its verified manifest identity by default."""

    return await _install_uploaded_module(
        request,
        expected_module_id,
    )


@router.post("/{module_id}/install-upload")
async def install_uploaded_module(module_id: str, request: Request) -> dict:
    """Compatibility route that explicitly checks the manifest identity."""

    return await _install_uploaded_module(
        request,
        module_id,
    )


@router.post("/{module_id}/enable")
async def enable_module(module_id: str, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().enable(module_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/disable")
async def disable_module(module_id: str, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().disable(module_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/update")
async def update_module(module_id: str, payload: InstallModuleRequest, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().update(module_id, Path(payload.package_path), payload.expected_sha256)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/rollback")
async def rollback_module(module_id: str, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().rollback(module_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/configuration/check")
async def check_module_configuration(module_id: str, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().check_configuration(module_id)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/{module_id}")
async def uninstall_module(module_id: str, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().uninstall(module_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/{module_id}/purge-data")
async def purge_module_data(module_id: str, payload: PurgeModuleDataRequest, request: Request) -> dict:
    _require_local(request)
    try:
        return get_module_manager().purge_data(module_id, payload.confirmation)
    except Exception as exc:
        _raise_http(exc)


@router.get("/{module_id}/assets/{asset_path:path}", include_in_schema=False)
async def module_asset(module_id: str, asset_path: str) -> FileResponse:
    try:
        target = get_module_manager().asset_path(module_id, asset_path)
        return FileResponse(str(target))
    except Exception as exc:
        _raise_http(exc)
