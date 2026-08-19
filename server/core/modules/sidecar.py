"""Core-owned sidecar adapter protocol.

Manifests name an adapter but cannot declare arbitrary commands. A trusted Core
integration must register the adapter implementation explicitly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Protocol

from .manifest import MODULE_ID_PATTERN, ModuleManifest


READINESS_READY = "ready"
READINESS_NEEDS_CONFIGURATION = "needs_configuration"
READINESS_UNAVAILABLE = "unavailable"
DEPENDENCY_DEPLOYMENT_MARKER = ".project-kei-deployment.json"

_READINESS_MESSAGES = {
    "ready": (READINESS_READY, "sidecar requirements are ready"),
    "legacy_healthcheck": (
        READINESS_READY,
        "sidecar uses the compatible runtime health check",
    ),
    "qq_env_missing": (
        READINESS_NEEDS_CONFIGURATION,
        "QQ configuration requirements are missing",
    ),
    "configuration_missing": (
        READINESS_NEEDS_CONFIGURATION,
        "sidecar configuration requirements are missing",
    ),
    "node_missing": (
        READINESS_UNAVAILABLE,
        "the required Node.js runtime is unavailable",
    ),
    "dependencies_missing": (
        READINESS_NEEDS_CONFIGURATION,
        "sidecar dependencies have not been deployed",
    ),
    "deployment_missing": (
        READINESS_NEEDS_CONFIGURATION,
        "the sidecar dependency deployment is missing",
    ),
    "deployment_invalid": (
        READINESS_UNAVAILABLE,
        "the sidecar dependency deployment is invalid",
    ),
    "integrity_mismatch": (
        READINESS_UNAVAILABLE,
        "the sidecar integrity check failed",
    ),
    "package_tampered": (
        READINESS_UNAVAILABLE,
        "the installed sidecar package is not trusted",
    ),
    "runtime_missing": (
        READINESS_UNAVAILABLE,
        "the required sidecar runtime is unavailable",
    ),
    "platform_unsupported": (
        READINESS_UNAVAILABLE,
        "the current platform is unsupported",
    ),
    "entrypoint_missing": (
        READINESS_UNAVAILABLE,
        "the reviewed sidecar entrypoint is unavailable",
    ),
    "adapter_unavailable": (
        READINESS_UNAVAILABLE,
        "the Core sidecar adapter is unavailable",
    ),
}
_REQUIREMENT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class SidecarReadiness:
    """A Core-normalized readiness result that cannot carry secret values."""

    status: str
    code: str
    message: str
    missing_requirements: tuple[str, ...] = ()

    @classmethod
    def from_code(
        cls,
        code: str,
        missing_requirements: tuple[str, ...] | list[str] = (),
    ) -> "SidecarReadiness":
        declaration = _READINESS_MESSAGES.get(code)
        if declaration is None:
            code = "adapter_unavailable"
            declaration = _READINESS_MESSAGES[code]
            missing_requirements = ()
        status, message = declaration
        missing = tuple(missing_requirements)
        if (
            len(missing) != len(set(missing))
            or any(not isinstance(item, str) or not _REQUIREMENT_NAME.fullmatch(item) for item in missing)
        ):
            raise ValueError("invalid sidecar missing requirement name")
        if status == READINESS_READY and missing:
            raise ValueError("ready sidecars cannot report missing requirements")
        return cls(
            status=status,
            code=code,
            message=message,
            missing_requirements=missing,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "missing_requirements": list(self.missing_requirements),
        }


@dataclass(frozen=True)
class SidecarDeploymentDescriptor:
    """Internal-only paths resolved from the installed current version."""

    module_id: str
    version: str
    package_root: Path
    dependency_deployment_root: Path
    installed_tree_sha256: str


class SidecarAdapter(Protocol):
    def start(self, manifest: ModuleManifest, package_root: str) -> None:
        """Start the sidecar without invoking a shell."""

    def stop(self, manifest: ModuleManifest, package_root: str) -> None:
        """Stop every background task owned by this sidecar."""

    def is_healthy(self, manifest: ModuleManifest, package_root: str) -> bool:
        """Return whether the started sidecar passes its offline/local health check."""


class ReadinessSidecarAdapter(SidecarAdapter, Protocol):
    """Optional extension implemented by adapters with pre-start requirements."""

    def readiness(
        self,
        manifest: ModuleManifest,
        package_root: str,
    ) -> SidecarReadiness:
        """Return only a Core-normalized, secret-free readiness result."""


class DeploymentSidecarAdapter(Protocol):
    """Preferred adapter contract that receives only a verified deployment."""

    def deployment_readiness(
        self,
        manifest: ModuleManifest,
        deployment: SidecarDeploymentDescriptor,
    ) -> SidecarReadiness:
        """Return secret-free readiness for this exact installed version."""

    def start_deployment(
        self,
        manifest: ModuleManifest,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        """Start the verified deployment without invoking a shell."""

    def stop_deployment(
        self,
        manifest: ModuleManifest,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        """Stop tasks owned by this exact deployment."""

    def is_deployment_healthy(
        self,
        manifest: ModuleManifest,
        deployment: SidecarDeploymentDescriptor,
    ) -> bool:
        """Return whether this exact deployment is healthy."""


_DEPLOYMENT_ADAPTER_METHODS = (
    "deployment_readiness",
    "start_deployment",
    "stop_deployment",
    "is_deployment_healthy",
)
_LEGACY_ADAPTER_METHODS = ("start", "stop", "is_healthy")


def is_deployment_sidecar_adapter(adapter: object) -> bool:
    return all(callable(getattr(adapter, name, None)) for name in _DEPLOYMENT_ADAPTER_METHODS)


class SidecarAdapterRegistry:
    """Resolve only adapters explicitly registered by trusted Core composition."""

    def __init__(self, adapters: Optional[Mapping[str, object]] = None):
        self._adapters: Dict[str, object] = {}
        for name, adapter in (adapters or {}).items():
            self.register(name, adapter)

    def register(self, name: str, adapter: object) -> None:
        if not isinstance(name, str) or not MODULE_ID_PATTERN.fullmatch(name):
            raise ValueError("invalid sidecar adapter name")
        if name in self._adapters:
            raise ValueError("sidecar adapter is already registered")
        deployment_methods = [
            callable(getattr(adapter, method, None))
            for method in _DEPLOYMENT_ADAPTER_METHODS
        ]
        if any(deployment_methods) and not all(deployment_methods):
            raise ValueError("deployment sidecar adapter protocol is incomplete")
        if not all(deployment_methods) and not all(
            callable(getattr(adapter, method, None))
            for method in _LEGACY_ADAPTER_METHODS
        ):
            raise ValueError("legacy sidecar adapter protocol is incomplete")
        self._adapters[name] = adapter

    def resolve(self, name: str) -> Optional[object]:
        if not isinstance(name, str) or not MODULE_ID_PATTERN.fullmatch(name):
            return None
        return self._adapters.get(name)


def normalize_sidecar_readiness(
    adapter: Optional[SidecarAdapter],
    manifest: ModuleManifest,
    package_root: str,
) -> SidecarReadiness:
    """Call optional readiness without exposing adapter exceptions or payloads."""

    if adapter is None:
        return SidecarReadiness.from_code("adapter_unavailable")
    readiness = getattr(adapter, "readiness", None)
    if not callable(readiness):
        return SidecarReadiness.from_code("legacy_healthcheck")
    try:
        result = readiness(manifest, package_root)
    except Exception:
        return SidecarReadiness.from_code("adapter_unavailable")
    if not isinstance(result, SidecarReadiness):
        return SidecarReadiness.from_code("adapter_unavailable")
    try:
        return SidecarReadiness.from_code(result.code, result.missing_requirements)
    except (TypeError, ValueError):
        return SidecarReadiness.from_code("adapter_unavailable")


def normalize_deployment_readiness(
    adapter: object,
    manifest: ModuleManifest,
    deployment: SidecarDeploymentDescriptor,
) -> SidecarReadiness:
    """Call the descriptor-aware readiness method with the same redaction."""

    if not is_deployment_sidecar_adapter(adapter):
        return SidecarReadiness.from_code("adapter_unavailable")
    try:
        result = adapter.deployment_readiness(manifest, deployment)
    except Exception:
        return SidecarReadiness.from_code("adapter_unavailable")
    if not isinstance(result, SidecarReadiness):
        return SidecarReadiness.from_code("adapter_unavailable")
    try:
        return SidecarReadiness.from_code(result.code, result.missing_requirements)
    except (TypeError, ValueError):
        return SidecarReadiness.from_code("adapter_unavailable")


__all__ = [
    "DEPENDENCY_DEPLOYMENT_MARKER",
    "DeploymentSidecarAdapter",
    "READINESS_NEEDS_CONFIGURATION",
    "READINESS_READY",
    "READINESS_UNAVAILABLE",
    "ReadinessSidecarAdapter",
    "SidecarAdapter",
    "SidecarAdapterRegistry",
    "SidecarDeploymentDescriptor",
    "SidecarReadiness",
    "is_deployment_sidecar_adapter",
    "normalize_deployment_readiness",
    "normalize_sidecar_readiness",
]
