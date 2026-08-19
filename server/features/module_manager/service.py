"""Application-level access to the process-wide module manager."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.modules import (
    DeploymentSidecarAdapter,
    InProcessModuleLoader,
    ModuleActivationCoordinator,
    ModuleManager,
    SidecarAdapter,
    SidecarDeploymentDescriptor,
)
from core.modules.official_catalog import OfficialCatalogHTTPClient, OfficialCatalogStore
from .official_service import OfficialModuleService


SERVER_ROOT = Path(__file__).resolve().parents[2]
_MANAGER = ModuleManager(
    runtime_root=SERVER_ROOT / "runtime" / "modules",
    registry_path=SERVER_ROOT / "data" / "module_registry.json",
    data_root=SERVER_ROOT / "data" / "modules",
)
_LOADER = InProcessModuleLoader()
_ACTIVATION_COORDINATOR = ModuleActivationCoordinator(_MANAGER, _LOADER)
_OFFICIAL_MODULES = OfficialModuleService(
    _MANAGER,
    OfficialCatalogStore(
        bundled_path=SERVER_ROOT / "core" / "modules" / "official-catalog.json",
        cache_path=SERVER_ROOT / "data" / "official_module_catalog.json",
    ),
    OfficialCatalogHTTPClient(),
)


def get_module_manager() -> ModuleManager:
    return _MANAGER


def register_core_sidecar_adapter(
    name: str,
    adapter: Union[SidecarAdapter, DeploymentSidecarAdapter],
) -> None:
    """Production composition seam for explicitly reviewed Core adapters."""

    _MANAGER.register_sidecar_adapter(name, adapter)


def resolve_sidecar_deployment(
    module_id: str,
    version: Optional[str] = None,
) -> SidecarDeploymentDescriptor:
    """Internal PK-020/adapter seam; never expose this object over HTTP."""

    return _MANAGER.resolve_sidecar_deployment(module_id, version)


def get_official_module_service() -> OfficialModuleService:
    return _OFFICIAL_MODULES


def load_enabled_in_process_modules(app: Any) -> List[Dict[str, str]]:
    results = _LOADER.load(app, _MANAGER.enabled_in_process_descriptors())
    _MANAGER.record_load_results(results)
    return results


async def unload_enabled_in_process_modules(app: Any) -> List[Dict[str, str]]:
    """Unload the startup snapshot in reverse dependency order."""

    descriptors = list(reversed(_MANAGER.enabled_in_process_descriptors()))
    return [
        await _LOADER.unload_one_async(app, descriptor["module_id"])
        for descriptor in descriptors
    ]


async def drain_module_cleanup_awaitables(app: Any) -> List[str]:
    """Await cleanup deferred by the synchronous pre-ASGI registration phase."""

    pending = getattr(app.state, "_module_cleanup_awaitables", None)
    if not isinstance(pending, list):
        return []
    app.state._module_cleanup_awaitables = []
    errors: List[str] = []
    for cleanup in pending:
        try:
            await cleanup
        except Exception as exc:
            errors.append(type(exc).__name__)
    return errors


def start_enabled_sidecars() -> List[Dict[str, Any]]:
    """Start enabled sidecars after the ASGI lifespan has begun."""

    return _MANAGER.start_enabled_sidecars()


def stop_enabled_sidecars() -> List[Dict[str, str]]:
    """Stop only sidecars owned by their registered trusted adapters."""

    return _MANAGER.stop_enabled_sidecars()


def activate_enabled_modules(app: Any) -> List[Dict[str, str]]:
    """Atomically assemble all enabled modules in one deterministic graph order."""

    return _ACTIVATION_COORDINATOR.activate(app)


def deactivate_enabled_modules(app: Any) -> List[Dict[str, str]]:
    """Unregister/stop the successful activation set in strict reverse order."""

    return _ACTIVATION_COORDINATOR.deactivate(app)


async def deactivate_enabled_modules_async(app: Any) -> List[Dict[str, str]]:
    """Await cleanup hooks supplied by installed in-process modules."""

    return await _ACTIVATION_COORDINATOR.deactivate_async(app)
