"""Installable module manifest, registry, and lifecycle primitives."""

from .contracts import (
    CORE_MODULE_CONTRACTS,
    CORE_RESERVED_API_NAMESPACES,
    CORE_RESERVED_MODULE_IDS,
    CoreModuleContract,
)
from .assembly import ModuleActivationCoordinator
from .loader import InProcessModuleLoader
from .manager import ModuleManager
from .manifest import CORE_VERSION, ModuleManifest, RuntimeRequirement, validate_manifest
from .sidecar import (
    DEPENDENCY_DEPLOYMENT_MARKER,
    DeploymentSidecarAdapter,
    ReadinessSidecarAdapter,
    SidecarAdapter,
    SidecarAdapterRegistry,
    SidecarDeploymentDescriptor,
    SidecarReadiness,
)

__all__ = [
    "CORE_VERSION",
    "DEPENDENCY_DEPLOYMENT_MARKER",
    "CORE_MODULE_CONTRACTS",
    "CORE_RESERVED_API_NAMESPACES",
    "CORE_RESERVED_MODULE_IDS",
    "CoreModuleContract",
    "DeploymentSidecarAdapter",
    "InProcessModuleLoader",
    "ModuleManager",
    "ModuleActivationCoordinator",
    "ModuleManifest",
    "RuntimeRequirement",
    "ReadinessSidecarAdapter",
    "SidecarAdapter",
    "SidecarAdapterRegistry",
    "SidecarDeploymentDescriptor",
    "SidecarReadiness",
    "validate_manifest",
]
