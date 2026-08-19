"""Manifest parsing and compatibility checks for installable modules."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .exceptions import ManifestValidationError


MANIFEST_SCHEMA_VERSION = 1
CORE_VERSION = "1.0.0"
ALLOWED_MODULE_TYPES = {"in_process", "sidecar"}
ALLOWED_PERMISSIONS = {"local_state", "network_download"}
MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
COMPATIBILITY_PART_PATTERN = re.compile(
    r"^(>=|<=|>|<|==|=)?"
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True)
class SidecarDeclaration:
    adapter: str
    healthcheck_timeout_seconds: int = 10


@dataclass(frozen=True)
class RuntimeRequirement:
    """A declarative host-runtime prerequisite; never an executable command."""

    id: str
    supported_major_versions: Tuple[int, ...]
    architecture: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "supported_major_versions": list(self.supported_major_versions),
            "architecture": self.architecture,
        }


@dataclass(frozen=True)
class ModuleManifest:
    schema_version: int
    id: str
    name: str
    version: str
    type: str
    required: bool
    core_compatibility: str
    entrypoint: Optional[str]
    dependencies: Tuple[str, ...]
    optional_dependencies: Tuple[str, ...]
    runtime_requirements: Tuple[RuntimeRequirement, ...]
    conflicts: Tuple[str, ...]
    api_namespaces: Tuple[str, ...]
    legacy_endpoints: Tuple[str, ...]
    dashboard_entrypoint: Optional[str]
    data_namespace: str
    config_schema: Optional[str]
    permissions: Tuple[str, ...]
    requires_restart: bool
    sidecar: Optional[SidecarDeclaration] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["dependencies"] = list(self.dependencies)
        payload["optional_dependencies"] = list(self.optional_dependencies)
        payload["runtime_requirements"] = [
            requirement.to_dict() for requirement in self.runtime_requirements
        ]
        payload["conflicts"] = list(self.conflicts)
        payload["api_namespaces"] = list(self.api_namespaces)
        payload["legacy_endpoints"] = list(self.legacy_endpoints)
        payload["permissions"] = list(self.permissions)
        return payload


def _require_string(payload: Dict[str, Any], field: str, max_length: int = 200) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError("manifest.%s must be a non-empty string" % field)
    value = value.strip()
    if len(value) > max_length:
        raise ManifestValidationError("manifest.%s is too long" % field)
    return value


def _require_bool(payload: Dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ManifestValidationError("manifest.%s must be a boolean" % field)
    return value


def _string_list(payload: Dict[str, Any], field: str) -> Tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ManifestValidationError("manifest.%s must be an array of strings" % field)
    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized):
        raise ManifestValidationError("manifest.%s cannot contain empty values" % field)
    if len(normalized) != len(set(normalized)):
        raise ManifestValidationError("manifest.%s cannot contain duplicates" % field)
    return normalized


def _safe_relative_path(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError("manifest.%s must be a non-empty relative path" % field)
    value = value.strip()
    if "\\" in value or re.match(r"^[A-Za-z]:", value):
        raise ManifestValidationError("manifest.%s must use a package-relative POSIX path" % field)
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ManifestValidationError("manifest.%s escapes the module package" % field)
    return value


def _validate_module_ids(values: Iterable[str], field: str) -> None:
    for value in values:
        if not MODULE_ID_PATTERN.fullmatch(value):
            raise ManifestValidationError("manifest.%s contains invalid module id %r" % (field, value))


def parse_runtime_requirements(payload: Dict[str, Any]) -> Tuple[RuntimeRequirement, ...]:
    value = payload.get("runtime_requirements", [])
    if not isinstance(value, list):
        raise ManifestValidationError("manifest.runtime_requirements must be an array")
    if len(value) > 8:
        raise ManifestValidationError("manifest.runtime_requirements contains too many entries")
    requirements = []
    seen = set()
    for declaration in value:
        if not isinstance(declaration, dict) or set(declaration) != {
            "id", "supported_major_versions", "architecture"
        }:
            raise ManifestValidationError(
                "manifest.runtime_requirements entries have invalid fields"
            )
        runtime_id = declaration.get("id")
        versions = declaration.get("supported_major_versions")
        architecture = declaration.get("architecture")
        if runtime_id not in {"node"}:
            raise ManifestValidationError(
                "manifest.runtime_requirements contains unsupported runtime id"
            )
        if runtime_id in seen:
            raise ManifestValidationError(
                "manifest.runtime_requirements cannot contain duplicate runtime ids"
            )
        if (
            not isinstance(versions, list)
            or not versions
            or len(versions) > 16
            or any(
                not isinstance(version, int)
                or isinstance(version, bool)
                or not 1 <= version <= 999
                for version in versions
            )
            or versions != sorted(set(versions))
        ):
            raise ManifestValidationError(
                "manifest.runtime_requirements supported_major_versions must be sorted unique integers"
            )
        if architecture != "x64":
            raise ManifestValidationError(
                "manifest.runtime_requirements architecture must be x64"
            )
        seen.add(runtime_id)
        requirements.append(
            RuntimeRequirement(
                id=runtime_id,
                supported_major_versions=tuple(versions),
                architecture=architecture,
            )
        )
    return tuple(requirements)


def parse_semver(value: str) -> Tuple[int, int, int, Tuple[str, ...]]:
    match = SEMVER_PATTERN.fullmatch(value)
    if not match:
        raise ManifestValidationError("invalid semantic version: %s" % value)
    prerelease = tuple((match.group(4) or "").split(".")) if match.group(4) else ()
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def compare_semver(left: str, right: str) -> int:
    left_value = parse_semver(left)
    right_value = parse_semver(right)
    if left_value[:3] != right_value[:3]:
        return -1 if left_value[:3] < right_value[:3] else 1
    left_pre, right_pre = left_value[3], right_value[3]
    if left_pre == right_pre:
        return 0
    if not left_pre:
        return 1
    if not right_pre:
        return -1
    for left_part, right_part in zip(left_pre, right_pre):
        if left_part == right_part:
            continue
        left_numeric, right_numeric = left_part.isdigit(), right_part.isdigit()
        if left_numeric and right_numeric:
            return -1 if int(left_part) < int(right_part) else 1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return -1 if left_part < right_part else 1
    return -1 if len(left_pre) < len(right_pre) else 1


def version_satisfies(version: str, compatibility: str) -> bool:
    parse_semver(version)
    compatibility = compatibility.strip()
    if compatibility == "*":
        return True
    parts = compatibility.replace(",", " ").split()
    if not parts:
        raise ManifestValidationError("core_compatibility cannot be empty")
    for part in parts:
        match = COMPATIBILITY_PART_PATTERN.fullmatch(part)
        if not match:
            raise ManifestValidationError("unsupported core compatibility constraint: %s" % part)
        operator = match.group(1) or "="
        required = ".".join(match.group(index) for index in (2, 3, 4))
        if match.group(5):
            required += "-" + match.group(5)
        comparison = compare_semver(version, required)
        accepted = {
            ">": comparison > 0,
            ">=": comparison >= 0,
            "<": comparison < 0,
            "<=": comparison <= 0,
            "=": comparison == 0,
            "==": comparison == 0,
        }[operator]
        if not accepted:
            return False
    return True


def validate_manifest(payload: Any, core_version: str = CORE_VERSION) -> ModuleManifest:
    if not isinstance(payload, dict):
        raise ManifestValidationError("manifest root must be a JSON object")
    allowed_fields = {
        "schema_version", "id", "name", "version", "type", "required",
        "core_compatibility", "entrypoint", "dependencies", "optional_dependencies",
        "conflicts", "runtime_requirements", "api_namespaces", "legacy_endpoints", "dashboard_entrypoint",
        "data_namespace", "config_schema", "permissions", "requires_restart", "sidecar",
    }
    unknown = sorted(set(payload) - allowed_fields)
    if unknown:
        raise ManifestValidationError("unknown manifest fields: %s" % ", ".join(unknown))
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError("unsupported manifest schema_version")

    module_id = _require_string(payload, "id", 64)
    if not MODULE_ID_PATTERN.fullmatch(module_id):
        raise ManifestValidationError("manifest.id must use lowercase letters, digits, and underscores")
    name = _require_string(payload, "name", 120)
    version = _require_string(payload, "version", 80)
    parse_semver(version)
    module_type = _require_string(payload, "type", 40)
    if module_type not in ALLOWED_MODULE_TYPES:
        raise ManifestValidationError("unsupported module type: %s" % module_type)
    required = _require_bool(payload, "required")
    compatibility = _require_string(payload, "core_compatibility", 160)
    if not version_satisfies(core_version, compatibility):
        raise ManifestValidationError(
            "module %s %s is not compatible with Core %s" % (module_id, version, core_version)
        )

    entrypoint = payload.get("entrypoint")
    if entrypoint is not None:
        entrypoint = _require_string(payload, "entrypoint", 160)
        parts = entrypoint.split(".")
        if len(parts) != 2 or any(not part.isidentifier() or part.startswith("_") for part in parts):
            raise ManifestValidationError("manifest.entrypoint must be a public module.callable path")
    if module_type == "in_process" and entrypoint is None:
        raise ManifestValidationError("in_process modules require manifest.entrypoint")

    dependencies = _string_list(payload, "dependencies")
    optional_dependencies = _string_list(payload, "optional_dependencies")
    runtime_requirements = parse_runtime_requirements(payload)
    conflicts = _string_list(payload, "conflicts")
    for field, values in (
        ("dependencies", dependencies),
        ("optional_dependencies", optional_dependencies),
        ("conflicts", conflicts),
    ):
        _validate_module_ids(values, field)
    all_relations = list(dependencies) + list(optional_dependencies) + list(conflicts)
    if module_id in all_relations:
        raise ManifestValidationError("a module cannot depend on or conflict with itself")
    if set(dependencies) & set(optional_dependencies):
        raise ManifestValidationError("required and optional dependencies must be disjoint")
    if (set(dependencies) | set(optional_dependencies)) & set(conflicts):
        raise ManifestValidationError("dependencies and conflicts must be disjoint")

    api_namespaces = _string_list(payload, "api_namespaces")
    legacy_endpoints = _string_list(payload, "legacy_endpoints")
    if any(not path.startswith("/api/v1/") or ".." in path or "//" in path for path in api_namespaces):
        raise ManifestValidationError("api_namespaces must stay under /api/v1/<module>")
    if any(not path.startswith("/") or ".." in path or "//" in path for path in legacy_endpoints):
        raise ManifestValidationError("legacy_endpoints must be absolute API paths")

    dashboard_entrypoint = _safe_relative_path(payload.get("dashboard_entrypoint"), "dashboard_entrypoint")
    data_namespace = _require_string(payload, "data_namespace", 64)
    if not MODULE_ID_PATTERN.fullmatch(data_namespace):
        raise ManifestValidationError("manifest.data_namespace must be a safe module id")
    config_schema = _safe_relative_path(payload.get("config_schema"), "config_schema")
    permissions = _string_list(payload, "permissions")
    unsupported_permissions = sorted(set(permissions) - ALLOWED_PERMISSIONS)
    if unsupported_permissions:
        raise ManifestValidationError(
            "permissions require PK-000 approval: %s" % ", ".join(unsupported_permissions)
        )
    requires_restart = _require_bool(payload, "requires_restart")

    sidecar_payload = payload.get("sidecar")
    sidecar = None
    if module_type == "sidecar":
        if not isinstance(sidecar_payload, dict):
            raise ManifestValidationError("sidecar modules require a sidecar declaration")
        if set(sidecar_payload) - {"adapter", "healthcheck_timeout_seconds"}:
            raise ManifestValidationError("sidecar declaration contains unsupported fields")
        adapter = sidecar_payload.get("adapter")
        timeout = sidecar_payload.get("healthcheck_timeout_seconds", 10)
        if not isinstance(adapter, str) or not MODULE_ID_PATTERN.fullmatch(adapter):
            raise ManifestValidationError("sidecar.adapter must name a Core-registered adapter")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 120:
            raise ManifestValidationError("sidecar healthcheck timeout must be between 1 and 120 seconds")
        sidecar = SidecarDeclaration(adapter=adapter, healthcheck_timeout_seconds=timeout)
    elif sidecar_payload is not None:
        raise ManifestValidationError("in_process modules cannot declare sidecar settings")

    return ModuleManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        id=module_id,
        name=name,
        version=version,
        type=module_type,
        required=required,
        core_compatibility=compatibility,
        entrypoint=entrypoint,
        dependencies=dependencies,
        optional_dependencies=optional_dependencies,
        runtime_requirements=runtime_requirements,
        conflicts=conflicts,
        api_namespaces=api_namespaces,
        legacy_endpoints=legacy_endpoints,
        dashboard_entrypoint=dashboard_entrypoint,
        data_namespace=data_namespace,
        config_schema=config_schema,
        permissions=permissions,
        requires_restart=requires_restart,
        sidecar=sidecar,
    )
