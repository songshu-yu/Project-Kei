"""Installable Bilibili module registration against frozen public providers."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, Request
from core.intel_contracts import CollectorRegistry

from .client import BilibiliPublicClient
from .collector import BilibiliCollector
from .credentials import BilibiliCredentialRepository, BilibiliCredentials
from .models import BilibiliProfileResolveRequest
from .router import create_bilibili_router
from .service import BilibiliService


def _provider(app: Any, name: str) -> Any:
    provider = getattr(app.state, name, None)
    if not callable(provider):
        raise RuntimeError("Bilibili module provider is unavailable: %s" % name)
    value = provider()
    if value is None:
        raise RuntimeError("Bilibili module provider returned no value: %s" % name)
    return value


def _local_guard(app: Any, name: str) -> Callable[[Any], bool]:
    guard = getattr(app.state, name, None)
    if not callable(guard):
        raise RuntimeError("Bilibili local request guard is unavailable: %s" % name)
    return guard


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(str(path)), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RuntimeError("Bilibili data path could not be inspected") from exc
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & marker)


def _data_root(app: Any) -> Path:
    root = Path(_provider(app, "bilibili_data_root_provider"))
    if not root.is_absolute():
        raise RuntimeError("Bilibili data root must be an absolute path")
    if ".." in root.parts:
        raise RuntimeError("Bilibili data root must be normalized")

    # Inspect the caller-provided path before canonicalization so an existing
    # symlink/junction cannot be hidden by resolve().  Windows 8.3 aliases are
    # legitimate absolute paths, however, and resolve() expands them to the
    # long spelling.  Treat that spelling change as canonicalization rather
    # than as a traversal attempt.
    current = root
    while True:
        if (current.exists() or current.is_symlink()) and _is_link_or_reparse(current):
            raise RuntimeError("Bilibili data root cannot traverse a link or reparse point")
        if current.parent == current:
            break
        current = current.parent
    try:
        resolved = root.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("Bilibili data root could not be resolved") from exc
    current = resolved
    while True:
        if (current.exists() or current.is_symlink()) and _is_link_or_reparse(current):
            raise RuntimeError("Bilibili data root cannot traverse a link or reparse point")
        if current.parent == current:
            break
        current = current.parent
    if resolved.exists() and not resolved.is_dir():
        raise RuntimeError("Bilibili data root must be a directory")
    return resolved


def _existing_paths(app: Any) -> set[str]:
    return {
        str(getattr(route, "path", ""))
        for route in getattr(app, "routes", ())
        if getattr(route, "path", None)
    }


def register(app: Any) -> None:
    """Register routes and Collector once, or fail before mutating the app."""
    if getattr(app.state, "bilibili_module_registered", False):
        return

    source_registry = _provider(app, "intel_source_registry_provider")
    collector_registry = _provider(app, "intel_collector_registry_provider")
    if not hasattr(source_registry, "read"):
        raise RuntimeError("intel_sources provider does not expose read()")
    if not isinstance(collector_registry, CollectorRegistry):
        raise RuntimeError("collector provider did not return CollectorRegistry")
    guard = _local_guard(app, "bilibili_local_request_guard")
    read_guard = getattr(app.state, "bilibili_local_read_guard", guard)
    if not callable(read_guard):
        raise RuntimeError("Bilibili local read guard is unavailable")
    data_root = _data_root(app)

    credential_repository = BilibiliCredentialRepository(
        data_root / "bilibili_credentials.local.json",
        environment_provider=lambda: {},
    )
    now_provider = getattr(app.state, "bilibili_now_provider", None)
    if now_provider is not None and not callable(now_provider):
        raise RuntimeError("Bilibili clock provider is not callable")
    fixed_now = now_provider() if now_provider is not None else None

    def uid_provider() -> list[object]:
        payload = source_registry.read()
        values = payload.get("bilibili_uids", []) if isinstance(payload, dict) else []
        return list(values) if isinstance(values, (list, tuple)) else []

    injected_client_factory = getattr(
        app.state, "bilibili_client_factory_provider", None
    )
    if injected_client_factory is not None and not callable(injected_client_factory):
        raise RuntimeError("Bilibili client factory provider is not callable")

    def client_factory(credentials: BilibiliCredentials) -> BilibiliPublicClient:
        if injected_client_factory is not None:
            return injected_client_factory(credentials)
        return BilibiliPublicClient(cookies=credentials.as_cookies())

    service = BilibiliService(
        uid_provider,
        profile_path=data_root / "bilibili_profiles.json",
        now=fixed_now,
        credential_repository=credential_repository,
        client_factory=client_factory,
    )
    collector_client = (
        injected_client_factory(None)
        if injected_client_factory is not None
        else BilibiliPublicClient(
            cookies_provider=lambda: _active_cookies(credential_repository)
        )
    )
    collector = BilibiliCollector(
        client=collector_client,
        now=now_provider if now_provider is not None else None,
    ) if now_provider is not None else BilibiliCollector(client=collector_client)
    router = create_bilibili_router(
        service,
        local_request_guard=guard,
        local_read_guard=read_guard,
    )

    @router.post("/dashboard/intel-sources/bilibili-profiles/resolve")
    async def legacy_resolve_profiles(
        payload: BilibiliProfileResolveRequest,
        request: Request,
    ) -> dict:
        if not guard(request):
            raise HTTPException(
                status_code=403,
                detail="This action is available only from this computer",
            )
        try:
            return await service.resolve_profiles(payload.uid, refresh=payload.refresh)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Bilibili profile cache could not be saved",
            ) from exc

    declared_paths = {str(route.path) for route in router.routes}
    existing = _existing_paths(app)
    overlap = declared_paths & existing
    if overlap:
        raise RuntimeError(
            "Bilibili routes already exist: %s" % ", ".join(sorted(overlap))
        )

    collector_registry.register(collector)
    route_count = len(app.router.routes)
    try:
        app.include_router(router)
    except Exception:
        del app.router.routes[route_count:]
        collector_registry.unregister("bilibili", collector=collector)
        raise

    app.state.bilibili_service = service
    app.state.bilibili_collector = collector
    app.state.bilibili_module_registered = True


def _active_cookies(repository: BilibiliCredentialRepository) -> dict[str, str]:
    credentials = repository.active_credentials()
    return credentials.as_cookies() if credentials is not None else {}


__all__ = ["register"]
