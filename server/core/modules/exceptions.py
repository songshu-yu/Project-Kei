"""Typed failures raised by the local module lifecycle manager."""


class ModuleError(Exception):
    """Base class for module lifecycle failures."""


class ManifestValidationError(ModuleError):
    """The package manifest is invalid or incompatible."""


class PackageValidationError(ModuleError):
    """The package archive or directory is unsafe or incomplete."""


class RegistryError(ModuleError):
    """The local module registry cannot be read or updated safely."""


class ModuleNotFoundError(ModuleError):
    """The requested managed module is not installed."""


class ModuleConflictError(ModuleError):
    """The requested operation conflicts with current module state."""


class ModuleOperationError(ModuleError):
    """A runtime lifecycle operation failed."""


class SidecarReadinessError(ModuleConflictError):
    """A sidecar is safely installed but cannot be started yet."""

    def __init__(self, readiness):
        super().__init__("sidecar requirements are not ready")
        self.readiness = readiness

    def detail(self):
        unavailable = self.readiness.status == "unavailable"
        return {
            "code": (
                "sidecar_unavailable"
                if unavailable
                else "sidecar_needs_configuration"
            ),
            "message": (
                "sidecar is unavailable"
                if unavailable
                else "sidecar requirements are not ready"
            ),
            "sidecar_readiness": self.readiness.to_dict(),
        }
