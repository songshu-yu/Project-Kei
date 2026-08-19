"""Local-only install, state, and restart-time loading lifecycle."""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import shutil
import stat
import tempfile
import threading
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from functools import cmp_to_key
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .contracts import (
    CORE_RESERVED_MODULE_IDS,
    conflicting_core_namespace,
)
from .exceptions import (
    ManifestValidationError,
    ModuleConflictError,
    ModuleNotFoundError,
    ModuleOperationError,
    PackageValidationError,
    SidecarReadinessError,
)
from .manifest import (
    CORE_VERSION,
    MODULE_ID_PATTERN,
    SEMVER_PATTERN,
    ModuleManifest,
    compare_semver,
    validate_manifest,
)
from .registry import ModuleRegistry
from .sidecar import (
    READINESS_READY,
    SidecarAdapterRegistry,
    SidecarDeploymentDescriptor,
    SidecarReadiness,
    is_deployment_sidecar_adapter,
    normalize_deployment_readiness,
    normalize_sidecar_readiness,
)
from .runtime_requirements import (
    RuntimeProbe,
    check_runtime_requirements,
    probe_host_runtime,
)


MAX_PACKAGE_FILES = 10_000
MAX_PACKAGE_BYTES = 512 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _operation(action: str, status: str, message: str) -> Dict[str, str]:
    return {"action": action, "status": status, "message": message, "at": _now()}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


class ModuleManager:
    """Manage only packages explicitly supplied from the local computer."""

    def __init__(
        self,
        runtime_root: Path,
        registry_path: Path,
        data_root: Path,
        core_version: str = CORE_VERSION,
        sidecar_adapters: Optional[Mapping[str, object]] = None,
        dependency_deployment_root: Optional[Path] = None,
        runtime_probe: Optional[RuntimeProbe] = None,
    ):
        self.runtime_root = Path(runtime_root)
        self.data_root = Path(data_root)
        self.dependency_deployment_root = Path(
            dependency_deployment_root
            or self.runtime_root.parent / "module-dependencies"
        )
        if (
            _is_within(self.dependency_deployment_root, self.runtime_root)
            or _is_within(self.runtime_root, self.dependency_deployment_root)
        ):
            raise ValueError("module dependency root must be separate from package runtime")
        self.core_version = core_version
        self.registry = ModuleRegistry(Path(registry_path))
        self._sidecar_adapters = SidecarAdapterRegistry(sidecar_adapters)
        self._runtime_probe = runtime_probe or probe_host_runtime
        self._lock = threading.RLock()

    def register_sidecar_adapter(self, name: str, adapter: object) -> None:
        self._sidecar_adapters.register(name, adapter)

    def resolve_sidecar_adapter(self, name: str) -> Optional[object]:
        """Return a trusted Core adapter without changing registry state."""

        return self._sidecar_adapters.resolve(name)

    def _assert_optional_module_id(self, module_id: str) -> None:
        if module_id in CORE_RESERVED_MODULE_IDS:
            raise ModuleConflictError(
                "module id %s is reserved by Project Kei Core" % module_id
            )

    def _validate_core_reservations(self, manifest: ModuleManifest) -> None:
        self._assert_optional_module_id(manifest.id)
        for namespace in manifest.api_namespaces:
            reserved = conflicting_core_namespace(namespace)
            if reserved:
                raise ModuleConflictError(
                    "API namespace %s conflicts with Core namespace %s"
                    % (namespace, reserved)
                )
        core_conflicts = sorted(set(manifest.conflicts) & CORE_RESERVED_MODULE_IDS)
        if core_conflicts:
            raise ModuleConflictError(
                "optional modules cannot conflict with required Core modules: %s"
                % ", ".join(core_conflicts)
            )

    def _entry(self, registry: Dict[str, Any], module_id: str) -> Dict[str, Any]:
        self._assert_optional_module_id(module_id)
        entry = registry["modules"].get(module_id)
        if not isinstance(entry, dict):
            raise ModuleNotFoundError("module %s is not installed" % module_id)
        return entry

    def _manifest_from_entry(self, entry: Dict[str, Any]) -> ModuleManifest:
        manifest = validate_manifest(entry.get("manifest"), self.core_version)
        self._validate_core_reservations(manifest)
        return manifest

    def _version_root(self, module_id: str, version: str) -> Path:
        if not MODULE_ID_PATTERN.fullmatch(module_id):
            raise ModuleOperationError("unsafe module id")
        target = self.runtime_root / module_id / version
        if not _is_within(target, self.runtime_root):
            raise ModuleOperationError("module runtime path escapes its root")
        return target

    def _package_root_for_entry(self, entry: Dict[str, Any], version: Optional[str] = None) -> Path:
        selected_version = version or entry.get("current_version")
        versions = entry.get("versions")
        if not isinstance(selected_version, str) or not isinstance(versions, dict):
            raise ModuleOperationError("module registry version metadata is invalid")
        record = versions.get(selected_version)
        if not isinstance(record, dict):
            raise ModuleOperationError("module version %s is not registered" % selected_version)
        relative = record.get("path")
        if not isinstance(relative, str):
            raise ModuleOperationError("module package path is invalid")
        target = self.runtime_root / PurePosixPath(relative)
        if not _is_within(target, self.runtime_root):
            raise ModuleOperationError("registered package path escapes runtime root")
        return target

    def _assert_safe_dependency_path(self, target: Path) -> None:
        root = self.dependency_deployment_root
        if not _is_within(target, root) or target == root:
            raise ModuleOperationError("dependency deployment path escapes its root")
        current = root
        if current.exists() and _is_link_or_reparse(current):
            raise ModuleOperationError("dependency deployment root cannot be a link")
        if current.exists() and not current.is_dir():
            raise ModuleOperationError(
                "dependency deployment root is not a directory"
            )
        try:
            relative_parts = target.absolute().relative_to(root.absolute()).parts
        except ValueError as exc:
            raise ModuleOperationError("dependency deployment path escapes its root") from exc
        for part in relative_parts:
            current = current / part
            if (current.exists() or current.is_symlink()) and _is_link_or_reparse(current):
                raise ModuleOperationError("dependency deployment path cannot contain links")
            if current.exists() and not current.is_dir():
                raise ModuleOperationError(
                    "dependency deployment path contains a non-directory"
                )
        if target.exists():
            if not target.is_dir():
                raise ModuleOperationError("dependency deployment target is not a directory")
            for path in target.rglob("*"):
                if _is_link_or_reparse(path) or not _is_within(path, target):
                    raise ModuleOperationError(
                        "dependency deployment cannot contain links or unsafe entries"
                    )

    def _build_sidecar_deployment_descriptor(
        self,
        module_id: str,
        version: str,
        package_root: Path,
        installed_tree_sha256: str,
    ) -> SidecarDeploymentDescriptor:
        if (
            not isinstance(module_id, str)
            or not MODULE_ID_PATTERN.fullmatch(module_id)
            or module_id in CORE_RESERVED_MODULE_IDS
        ):
            raise ModuleOperationError("invalid sidecar deployment module id")
        if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
            raise ModuleOperationError("invalid sidecar deployment version")
        expected_package_root = self._version_root(module_id, version)
        if (
            package_root != expected_package_root
            or not package_root.is_dir()
            or not _is_within(package_root, self.runtime_root)
        ):
            raise ModuleOperationError("sidecar package root is not the installed version")
        self._directory_files(package_root)
        if (
            not isinstance(installed_tree_sha256, str)
            or len(installed_tree_sha256) != 64
            or any(character not in "0123456789abcdef" for character in installed_tree_sha256.lower())
        ):
            raise ModuleOperationError("installed package digest is invalid")
        dependency_root = self.dependency_deployment_root / module_id / version
        self._assert_safe_dependency_path(dependency_root)
        return SidecarDeploymentDescriptor(
            module_id=module_id,
            version=version,
            package_root=package_root,
            dependency_deployment_root=dependency_root,
            installed_tree_sha256=installed_tree_sha256.lower(),
        )

    def _sidecar_deployment_for_entry(
        self,
        module_id: str,
        entry: Dict[str, Any],
        version: Optional[str] = None,
    ) -> SidecarDeploymentDescriptor:
        current = entry.get("current_version")
        selected = version or current
        if not isinstance(current, str) or selected != current:
            raise ModuleConflictError(
                "sidecar deployment must use the installed current version"
            )
        manifest = self._manifest_from_entry(entry)
        if manifest.type != "sidecar" or manifest.id != module_id:
            raise ModuleConflictError("module is not an installed sidecar")
        versions = entry.get("versions")
        record = versions.get(current) if isinstance(versions, dict) else None
        if not isinstance(record, dict):
            raise ModuleOperationError("current sidecar version metadata is invalid")
        expected_relative = "%s/%s" % (module_id, current)
        if record.get("path") != expected_relative:
            raise ModuleOperationError("current sidecar package path is invalid")
        return self._build_sidecar_deployment_descriptor(
            module_id,
            current,
            self._package_root_for_entry(entry),
            record.get("installed_tree_sha256"),
        )

    def resolve_sidecar_deployment(
        self,
        module_id: str,
        version: Optional[str] = None,
    ) -> SidecarDeploymentDescriptor:
        """Resolve an internal descriptor for PK-020 or a trusted adapter."""

        with self._lock:
            if (
                not isinstance(module_id, str)
                or not MODULE_ID_PATTERN.fullmatch(module_id)
                or module_id in CORE_RESERVED_MODULE_IDS
            ):
                raise ModuleOperationError("invalid sidecar deployment module id")
            if version is not None and (
                not isinstance(version, str)
                or not SEMVER_PATTERN.fullmatch(version)
            ):
                raise ModuleOperationError("invalid sidecar deployment version")
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            return self._sidecar_deployment_for_entry(module_id, entry, version)

    def _available_actions(self, entry: Dict[str, Any]) -> List[str]:
        actions = ["configuration_check", "uninstall", "purge_data"]
        actions.append("disable" if entry.get("enabled") else "enable")
        actions.extend(["update_official", "update_local"])
        previous = entry.get("previous_version")
        versions = entry.get("versions", {})
        if isinstance(previous, str) and isinstance(versions, dict) and previous in versions:
            actions.append("rollback")
            previous_record = versions.get(previous)
            if isinstance(previous_record, dict) and previous_record.get("source") == "official_github_release":
                actions.append("rollback_official")
        return actions

    def _dependency_readiness(
        self,
        registry: Dict[str, Any],
        manifest: ModuleManifest,
    ) -> Dict[str, Any]:
        checks = []
        for dependency in manifest.dependencies:
            if dependency in CORE_RESERVED_MODULE_IDS:
                status = "ready"
            else:
                dependency_entry = registry.get("modules", {}).get(dependency)
                if not isinstance(dependency_entry, dict):
                    status = "missing"
                elif dependency_entry.get("enabled"):
                    status = "ready"
                else:
                    status = "disabled"
            checks.append({"module_id": dependency, "status": status})
        return {
            "ready": all(check["status"] == "ready" for check in checks),
            "checks": checks,
        }

    def _describe(
        self,
        module_id: str,
        entry: Dict[str, Any],
        registry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        manifest = self._manifest_from_entry(entry)
        dependency_readiness = self._dependency_readiness(
            registry or self.registry.load(),
            manifest,
        )
        versions = entry.get("versions", {})
        current = entry.get("current_version")
        current_record = versions.get(current, {}) if isinstance(versions, dict) else {}
        return {
            "module_id": module_id,
            "name": manifest.name,
            "managed": True,
            "source": "local_package",
            "type": manifest.type,
            "required": manifest.required,
            "install_status": entry.get("state", "broken"),
            "installed_version": current,
            "available_versions": sorted(versions, key=cmp_to_key(compare_semver)),
            "enabled": bool(entry.get("enabled")),
            "configuration_ready": bool(entry.get("configuration_ready")),
            "sidecar_readiness": entry.get("sidecar_readiness"),
            "dependencies": list(manifest.dependencies),
            "optional_dependencies": list(manifest.optional_dependencies),
            "dependency_readiness": dependency_readiness,
            "runtime_requirements": [
                requirement.to_dict() for requirement in manifest.runtime_requirements
            ],
            "runtime_readiness": entry.get("runtime_readiness", {
                "ready": not manifest.runtime_requirements,
                "checks": [],
            }),
            "conflicts": list(manifest.conflicts),
            "permissions": list(manifest.permissions),
            "requires_restart": manifest.requires_restart,
            "restart_required": bool(entry.get("restart_required")),
            "dashboard_entrypoint": (
                "/api/v1/modules/%s/assets/%s" % (module_id, manifest.dashboard_entrypoint)
                if manifest.dashboard_entrypoint else None
            ),
            "dashboard_entrypoint_path": manifest.dashboard_entrypoint,
            "api_namespaces": list(manifest.api_namespaces),
            "legacy_endpoints": list(manifest.legacy_endpoints),
            "package_sha256": current_record.get("sha256"),
            "package_source": current_record.get("source", "local_import"),
            "release": current_record.get("release"),
            "previous_version": entry.get("previous_version"),
            "last_operation": entry.get("last_operation"),
            "data_policy": "preserve_on_uninstall",
            "available_actions": self._available_actions(entry),
        }

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        registry = self.registry.load()
        result = {}
        for module_id, entry in registry["modules"].items():
            if module_id in CORE_RESERVED_MODULE_IDS:
                continue
            try:
                result[module_id] = self._describe(module_id, entry, registry)
            except Exception as exc:
                result[module_id] = {
                    "module_id": module_id,
                    "managed": True,
                    "source": "local_package",
                    "install_status": "broken",
                    "enabled": bool(entry.get("enabled")) if isinstance(entry, dict) else False,
                    "last_operation": _operation(
                        "inspect", "failed", "%s: %s" % (type(exc).__name__, str(exc))
                    ),
                }
        return result

    def get(self, module_id: str) -> Dict[str, Any]:
        registry = self.registry.load()
        return self._describe(module_id, self._entry(registry, module_id), registry)

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _directory_files(self, root: Path) -> List[Tuple[Path, str]]:
        if _is_link_or_reparse(root):
            raise PackageValidationError("module package root cannot be a link or reparse point")
        files = []
        total_size = 0
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
            if _is_link_or_reparse(path):
                raise PackageValidationError("module packages cannot contain links or reparse points")
            if path.is_dir():
                continue
            if not path.is_file() or not _is_within(path, root):
                raise PackageValidationError("module package contains an unsafe filesystem entry")
            relative = path.relative_to(root).as_posix()
            if Path(relative).name.lower() == ".env":
                raise PackageValidationError("module packages cannot contain .env files")
            total_size += path.stat().st_size
            files.append((path, relative))
            if len(files) > MAX_PACKAGE_FILES or total_size > MAX_PACKAGE_BYTES:
                raise PackageValidationError("module package exceeds the local safety limit")
        return files

    def _hash_directory(self, root: Path, files: Iterable[Tuple[Path, str]]) -> str:
        digest = hashlib.sha256()
        for path, relative in files:
            encoded = relative.encode("utf-8")
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
            digest.update(path.stat().st_size.to_bytes(8, "big"))
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        return digest.hexdigest()

    def calculate_package_sha256(self, package_path: Path) -> str:
        path = Path(package_path).resolve()
        if path.is_file():
            return self._hash_file(path)
        if path.is_dir():
            files = self._directory_files(path)
            return self._hash_directory(path, files)
        raise PackageValidationError("local module package does not exist")

    def _validate_expected_hash(self, package_path: Path, expected_sha256: str) -> str:
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise PackageValidationError("expected_sha256 must be a 64-character SHA-256 digest")
        expected = expected_sha256.lower()
        if any(character not in "0123456789abcdef" for character in expected):
            raise PackageValidationError("expected_sha256 is not hexadecimal")
        actual = self.calculate_package_sha256(package_path)
        if actual != expected:
            raise PackageValidationError("module package SHA-256 does not match expected_sha256")
        return actual

    def _extract_zip(self, archive: Path, destination: Path) -> None:
        try:
            source = zipfile.ZipFile(str(archive), "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise PackageValidationError("module archive is not a readable ZIP file") from exc
        with source:
            infos = source.infolist()
            if len(infos) > MAX_PACKAGE_FILES:
                raise PackageValidationError("module archive contains too many entries")
            total_size = 0
            seen = set()
            for info in infos:
                name = info.filename
                normalized = PurePosixPath(name)
                if (
                    not name
                    or "\\" in name
                    or normalized.is_absolute()
                    or re_drive_path(name)
                    or any(part in {"", ".", ".."} for part in normalized.parts)
                ):
                    raise PackageValidationError("module archive contains an unsafe path")
                lowered = normalized.as_posix().lower().rstrip("/")
                if lowered in seen:
                    raise PackageValidationError("module archive contains duplicate paths")
                seen.add(lowered)
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise PackageValidationError("module archive cannot contain symbolic links")
                if info.create_system == 0 and (info.external_attr & 0x400):
                    raise PackageValidationError("module archive cannot contain reparse points")
                if normalized.name.lower() == ".env":
                    raise PackageValidationError("module packages cannot contain .env files")
                total_size += info.file_size
                if total_size > MAX_PACKAGE_BYTES:
                    raise PackageValidationError("module archive exceeds the local safety limit")
                target = destination.joinpath(*normalized.parts)
                if not _is_within(target, destination):
                    raise PackageValidationError("module archive path escapes the staging directory")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info, "r") as reader, target.open("wb") as writer:
                    shutil.copyfileobj(reader, writer)

    def _stage_package(self, package_path: Path, destination: Path) -> None:
        source = Path(package_path).resolve()
        if source.is_file():
            if source.suffix.lower() != ".zip":
                raise PackageValidationError("local module package files must use .zip")
            self._extract_zip(source, destination)
            return
        if source.is_dir():
            files = self._directory_files(source)
            for path, relative in files:
                target = destination.joinpath(*PurePosixPath(relative).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(target))
            return
        raise PackageValidationError("local module package does not exist")

    def _read_staged_manifest(self, package_root: Path) -> ModuleManifest:
        path = package_root / "manifest.json"
        if not path.is_file():
            raise PackageValidationError("module package must contain manifest.json at its root")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ManifestValidationError("manifest.json is not valid UTF-8 JSON") from exc
        manifest = validate_manifest(payload, self.core_version)
        self._validate_declared_files(package_root, manifest)
        return manifest

    def _validate_declared_files(self, package_root: Path, manifest: ModuleManifest) -> None:
        for field, relative in (
            ("dashboard_entrypoint", manifest.dashboard_entrypoint),
            ("config_schema", manifest.config_schema),
        ):
            if relative is None:
                continue
            target = package_root.joinpath(*PurePosixPath(relative).parts)
            if not _is_within(target, package_root) or not target.is_file():
                raise PackageValidationError("declared %s is missing from the package" % field)
        if manifest.entrypoint:
            module_parts = manifest.entrypoint.split(".")[:-1]
            module_file = package_root.joinpath(*module_parts).with_suffix(".py")
            package_file = package_root.joinpath(*module_parts, "__init__.py")
            if not module_file.is_file() and not package_file.is_file():
                raise PackageValidationError("declared in-process entrypoint module is missing")
        if manifest.config_schema:
            config_path = package_root.joinpath(*PurePosixPath(manifest.config_schema).parts)
            try:
                schema = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise PackageValidationError("config_schema is not valid UTF-8 JSON") from exc
            if not isinstance(schema, dict):
                raise PackageValidationError("config_schema root must be an object")

    def _check_graph(self, registry: Dict[str, Any], candidate: ModuleManifest) -> None:
        self._validate_core_reservations(candidate)
        manifests = {}
        for module_id, entry in registry["modules"].items():
            if module_id == candidate.id or module_id in CORE_RESERVED_MODULE_IDS:
                continue
            manifests[module_id] = self._manifest_from_entry(entry)
        manifests[candidate.id] = candidate

        namespaces = {}
        for module_id, manifest in manifests.items():
            for namespace in manifest.api_namespaces:
                owner = namespaces.get(namespace)
                if owner and owner != module_id:
                    raise ModuleConflictError(
                        "API namespace %s is already owned by module %s" % (namespace, owner)
                    )
                namespaces[namespace] = module_id

        enabled = {
            module_id for module_id, entry in registry["modules"].items()
            if (
                module_id != candidate.id
                and module_id not in CORE_RESERVED_MODULE_IDS
                and bool(entry.get("enabled"))
            )
        }
        collisions = sorted(set(candidate.conflicts) & enabled)
        reverse_collisions = sorted(
            module_id for module_id in enabled if candidate.id in manifests[module_id].conflicts
        )
        if collisions or reverse_collisions:
            raise ModuleConflictError(
                "module conflicts with enabled modules: %s" % ", ".join(collisions + reverse_collisions)
            )

        visiting, visited = set(), set()

        def visit(module_id: str, trail: List[str]) -> None:
            if module_id in visiting:
                start = trail.index(module_id) if module_id in trail else 0
                raise ModuleConflictError("module dependency cycle: %s" % " -> ".join(trail[start:] + [module_id]))
            if module_id in visited or module_id not in manifests:
                return
            visiting.add(module_id)
            trail.append(module_id)
            for dependency in manifests[module_id].dependencies:
                visit(dependency, trail)
            trail.pop()
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in sorted(manifests):
            visit(module_id, [])

    def _sidecar_readiness(
        self,
        package_root: Path,
        manifest: ModuleManifest,
        deployment: Optional[SidecarDeploymentDescriptor] = None,
    ) -> Optional[SidecarReadiness]:
        if manifest.type != "sidecar" or not manifest.sidecar:
            return None
        adapter = self._sidecar_adapters.resolve(manifest.sidecar.adapter)
        if is_deployment_sidecar_adapter(adapter):
            if deployment is None:
                return SidecarReadiness.from_code("adapter_unavailable")
            return normalize_deployment_readiness(adapter, manifest, deployment)
        return normalize_sidecar_readiness(adapter, manifest, str(package_root))

    def _configuration_status(
        self,
        package_root: Path,
        manifest: ModuleManifest,
        deployment: Optional[SidecarDeploymentDescriptor] = None,
    ) -> Tuple[bool, List[str], Dict[str, object], Optional[SidecarReadiness]]:
        missing = []
        if manifest.config_schema:
            config_path = package_root.joinpath(*PurePosixPath(manifest.config_schema).parts)
            schema = json.loads(config_path.read_text(encoding="utf-8"))
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            if not isinstance(required, list) or not isinstance(properties, dict):
                raise ModuleOperationError("config_schema required/properties declarations are invalid")
            for field in required:
                declaration = properties.get(field, {})
                env_name = declaration.get("x-env-var") if isinstance(declaration, dict) else None
                if not isinstance(env_name, str) or not env_name or not os.getenv(env_name):
                    missing.append(str(field))
        sidecar_readiness = self._sidecar_readiness(
            package_root,
            manifest,
            deployment,
        )
        sidecar_ready = (
            sidecar_readiness is None
            or sidecar_readiness.status == READINESS_READY
        )
        runtime_readiness = check_runtime_requirements(
            manifest.runtime_requirements,
            self._runtime_probe,
        )
        return (
            not missing and bool(runtime_readiness["ready"]) and sidecar_ready,
            missing,
            runtime_readiness,
            sidecar_readiness,
        )

    def _install_record(
        self,
        manifest: ModuleManifest,
        digest: str,
        installed_tree_sha256: str,
        version_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata = dict(version_metadata or {})
        source = metadata.pop("source", "local_import")
        if source not in {"local_import", "official_github_release"}:
            raise ModuleOperationError("unsupported module package source")
        record = {
            "path": "%s/%s" % (manifest.id, manifest.version),
            "sha256": digest,
            "installed_tree_sha256": installed_tree_sha256,
            "source": source,
            "installed_at": _now(),
        }
        if source == "official_github_release":
            allowed = {
                "publisher", "owner", "repository", "release_tag",
                "asset_name", "manifest_sha256",
            }
            if set(metadata) != allowed or any(not isinstance(metadata[key], str) for key in allowed):
                raise ModuleOperationError("official module release metadata is incomplete")
            record["release"] = metadata
        elif metadata:
            raise ModuleOperationError("local module metadata contains unsupported fields")
        return record

    def install(
        self,
        package_path: Path,
        expected_sha256: str,
        expected_module_id: Optional[str] = None,
        version_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if expected_module_id is not None:
            self._assert_optional_module_id(expected_module_id)
        return self._install_or_update(
            package_path,
            expected_sha256,
            expected_module_id,
            update=False,
            version_metadata=version_metadata,
        )

    def update(
        self,
        module_id: str,
        package_path: Path,
        expected_sha256: str,
        version_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._assert_optional_module_id(module_id)
        return self._install_or_update(
            package_path,
            expected_sha256,
            module_id,
            update=True,
            version_metadata=version_metadata,
        )

    def _install_or_update(
        self,
        package_path: Path,
        expected_sha256: str,
        expected_module_id: Optional[str],
        update: bool,
        version_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        with self._lock:
            digest = self._validate_expected_hash(Path(package_path), expected_sha256)
            with tempfile.TemporaryDirectory(prefix="project-kei-module-") as temp_dir:
                staging = Path(temp_dir) / "package"
                staging.mkdir()
                self._stage_package(Path(package_path), staging)
                if Path(package_path).resolve().is_dir():
                    staged_files = self._directory_files(staging)
                    if self._hash_directory(staging, staged_files) != digest:
                        raise PackageValidationError("module directory changed while it was being staged")
                manifest = self._read_staged_manifest(staging)
                if expected_module_id is not None and manifest.id != expected_module_id:
                    raise ManifestValidationError(
                        "package id %s does not match requested module %s" % (manifest.id, expected_module_id)
                    )
                self._validate_core_reservations(manifest)
                registry = self.registry.load()
                existing = registry["modules"].get(manifest.id)
                old_entry_snapshot = None
                if update:
                    if not isinstance(existing, dict):
                        raise ModuleNotFoundError("module %s is not installed" % manifest.id)
                    current_version = existing.get("current_version")
                    if not isinstance(current_version, str) or compare_semver(manifest.version, current_version) <= 0:
                        raise ModuleConflictError("update version must be newer than the installed version")
                    old_manifest = self._manifest_from_entry(existing)
                    old_entry_snapshot = deepcopy(existing)
                    if (
                        manifest.type != old_manifest.type
                        or manifest.required != old_manifest.required
                        or manifest.data_namespace != old_manifest.data_namespace
                    ):
                        raise ModuleConflictError(
                            "updates cannot change module type, required status, or data namespace"
                        )
                elif existing is not None:
                    raise ModuleConflictError("module %s is already installed" % manifest.id)
                elif manifest.required:
                    raise ModuleConflictError("required Core modules cannot be installed from optional local packages")

                self._check_graph(registry, manifest)
                final_root = self._version_root(manifest.id, manifest.version)
                if final_root.exists():
                    raise ModuleConflictError("module version directory already exists")
                final_root.parent.mkdir(parents=True, exist_ok=True)
                prepared_parent = Path(tempfile.mkdtemp(prefix=".%s-" % manifest.version, dir=str(final_root.parent)))
                prepared_root = prepared_parent / "package"
                try:
                    shutil.copytree(str(staging), str(prepared_root))
                    os.replace(str(prepared_root), str(final_root))
                finally:
                    shutil.rmtree(str(prepared_parent), ignore_errors=True)
                try:
                    installed_tree_sha256 = self._hash_directory(
                        final_root,
                        self._directory_files(final_root),
                    )
                    deployment = (
                        self._build_sidecar_deployment_descriptor(
                            manifest.id,
                            manifest.version,
                            final_root,
                            installed_tree_sha256,
                        )
                        if manifest.type == "sidecar"
                        else None
                    )
                    configuration_ready, missing, runtime_readiness, sidecar_readiness = self._configuration_status(
                        final_root,
                        manifest,
                        deployment,
                    )
                except Exception:
                    shutil.rmtree(str(final_root), ignore_errors=True)
                    raise
                if update and bool(existing.get("enabled")) and not configuration_ready:
                    shutil.rmtree(str(final_root), ignore_errors=True)
                    raise ModuleConflictError("enabled module update requires complete configuration")
                sidecar_switched = False
                try:
                    if update:
                        old_manifest = self._manifest_from_entry(existing)
                        if bool(existing.get("enabled")) and old_manifest.type == "sidecar":
                            self._switch_sidecar(
                                existing,
                                old_manifest,
                                manifest,
                                final_root,
                                deployment,
                            )
                            sidecar_switched = True
                        previous = existing.get("current_version")
                        existing.setdefault("versions", {})[manifest.version] = self._install_record(
                            manifest,
                            digest,
                            installed_tree_sha256,
                            version_metadata,
                        )
                        existing.update({
                            "manifest": manifest.to_dict(),
                            "current_version": manifest.version,
                            "previous_version": previous,
                            "configuration_ready": configuration_ready,
                            "sidecar_readiness": (
                                sidecar_readiness.to_dict() if sidecar_readiness else None
                            ),
                            "runtime_readiness": runtime_readiness,
                            "state": (
                                "needs_configuration" if not configuration_ready
                                else "enabled" if existing.get("enabled")
                                else "installed_disabled"
                            ),
                            "restart_required": bool(existing.get("enabled")) and manifest.requires_restart,
                            "last_operation": _operation("update", "success", "updated to %s" % manifest.version),
                        })
                    else:
                        registry["modules"][manifest.id] = {
                            "manifest": manifest.to_dict(),
                            "current_version": manifest.version,
                            "previous_version": None,
                            "versions": {
                                manifest.version: self._install_record(
                                    manifest,
                                    digest,
                                    installed_tree_sha256,
                                    version_metadata,
                                )
                            },
                            "enabled": False,
                            "configuration_ready": configuration_ready,
                            "sidecar_readiness": (
                                sidecar_readiness.to_dict() if sidecar_readiness else None
                            ),
                            "runtime_readiness": runtime_readiness,
                            "state": "installed_disabled" if configuration_ready else "needs_configuration",
                            "restart_required": False,
                            "last_operation": _operation(
                                "install",
                                "success",
                                (
                                    "installed; missing configuration: %s"
                                    % ", ".join(missing)
                                )
                                if missing
                                else (
                                    "installed; sidecar requirements are not ready"
                                    if sidecar_readiness
                                    and sidecar_readiness.status != READINESS_READY
                                    else "installed"
                                ),
                            ),
                        }
                    self.registry.save(registry)
                except Exception:
                    if sidecar_switched:
                        self._restore_sidecar(
                            old_entry_snapshot,
                            old_manifest,
                            manifest,
                            final_root,
                            deployment,
                        )
                    shutil.rmtree(str(final_root), ignore_errors=True)
                    raise
                return self._describe(manifest.id, registry["modules"][manifest.id], registry)

    def _adapter_for(self, manifest: ModuleManifest) -> object:
        if not manifest.sidecar:
            raise ModuleOperationError("sidecar declaration is missing")
        adapter = self._sidecar_adapters.resolve(manifest.sidecar.adapter)
        if adapter is None:
            raise ModuleOperationError(
                "Core sidecar adapter %s is not registered" % manifest.sidecar.adapter
            )
        return adapter

    def _sidecar_starts_automatically(self, manifest: ModuleManifest) -> bool:
        """Default to the historical lifecycle unless an adapter opts out."""

        if not manifest.sidecar:
            return True
        adapter = self._sidecar_adapters.resolve(manifest.sidecar.adapter)
        return getattr(adapter, "start_automatically", True) is not False

    def _start_sidecar(
        self,
        manifest: ModuleManifest,
        package_root: Path,
        deployment: Optional[SidecarDeploymentDescriptor] = None,
    ) -> SidecarReadiness:
        if not manifest.sidecar:
            raise ModuleOperationError("sidecar declaration is missing")
        adapter = self._sidecar_adapters.resolve(manifest.sidecar.adapter)
        if is_deployment_sidecar_adapter(adapter):
            if deployment is None:
                readiness = SidecarReadiness.from_code("adapter_unavailable")
            else:
                readiness = normalize_deployment_readiness(
                    adapter,
                    manifest,
                    deployment,
                )
        else:
            readiness = normalize_sidecar_readiness(
                adapter,
                manifest,
                str(package_root),
            )
        if readiness.status != READINESS_READY:
            raise SidecarReadinessError(readiness)
        if adapter is None:
            raise SidecarReadinessError(
                SidecarReadiness.from_code("adapter_unavailable")
            )
        try:
            if is_deployment_sidecar_adapter(adapter):
                adapter.start_deployment(manifest, deployment)
                healthy = adapter.is_deployment_healthy(manifest, deployment)
            else:
                adapter.start(manifest, str(package_root))
                healthy = adapter.is_healthy(manifest, str(package_root))
        except Exception as exc:
            try:
                if is_deployment_sidecar_adapter(adapter):
                    adapter.stop_deployment(manifest, deployment)
                else:
                    adapter.stop(manifest, str(package_root))
            except Exception:
                pass
            raise ModuleOperationError(
                "sidecar start or health check failed"
            ) from exc
        if not healthy:
            try:
                if is_deployment_sidecar_adapter(adapter):
                    adapter.stop_deployment(manifest, deployment)
                else:
                    adapter.stop(manifest, str(package_root))
            finally:
                raise ModuleOperationError("sidecar health check failed")
        return readiness

    def _stop_sidecar(
        self,
        manifest: ModuleManifest,
        package_root: Path,
        deployment: Optional[SidecarDeploymentDescriptor] = None,
    ) -> None:
        adapter = self._adapter_for(manifest)
        try:
            if is_deployment_sidecar_adapter(adapter):
                if deployment is None:
                    raise ModuleOperationError(
                        "verified sidecar deployment is unavailable"
                    )
                adapter.stop_deployment(manifest, deployment)
                return
            adapter.stop(manifest, str(package_root))
        except ModuleOperationError:
            raise
        except Exception as exc:
            raise ModuleOperationError("sidecar stop failed") from exc

    def _switch_sidecar(
        self,
        old_entry: Dict[str, Any],
        old_manifest: ModuleManifest,
        new_manifest: ModuleManifest,
        new_root: Path,
        new_deployment: Optional[SidecarDeploymentDescriptor],
    ) -> None:
        old_root = self._package_root_for_entry(old_entry)
        old_deployment = self._sidecar_deployment_for_entry(
            old_manifest.id,
            old_entry,
        )
        self._stop_sidecar(old_manifest, old_root, old_deployment)
        if not self._sidecar_starts_automatically(new_manifest):
            return
        try:
            self._start_sidecar(new_manifest, new_root, new_deployment)
        except Exception:
            self._start_sidecar(old_manifest, old_root, old_deployment)
            raise

    def _restore_sidecar(
        self,
        old_entry: Dict[str, Any],
        old_manifest: ModuleManifest,
        new_manifest: ModuleManifest,
        new_root: Path,
        new_deployment: Optional[SidecarDeploymentDescriptor],
    ) -> None:
        restore_automatically = self._sidecar_starts_automatically(old_manifest)
        try:
            self._stop_sidecar(new_manifest, new_root, new_deployment)
        finally:
            old_root = self._package_root_for_entry(old_entry)
            old_deployment = self._sidecar_deployment_for_entry(
                old_manifest.id,
                old_entry,
            )
            if restore_automatically:
                try:
                    self._start_sidecar(
                        old_manifest,
                        old_root,
                        old_deployment,
                    )
                except Exception as exc:
                    raise ModuleOperationError(
                        "old sidecar could not be restored after registry failure"
                    ) from exc

    def check_configuration(self, module_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            manifest = self._manifest_from_entry(entry)
            package_root = self._package_root_for_entry(entry)
            deployment = (
                self._sidecar_deployment_for_entry(module_id, entry)
                if manifest.type == "sidecar"
                else None
            )
            ready, missing, runtime_readiness, sidecar_readiness = self._configuration_status(
                package_root,
                manifest,
                deployment,
            )
            entry["configuration_ready"] = ready
            entry["sidecar_readiness"] = (
                sidecar_readiness.to_dict() if sidecar_readiness else None
            )
            entry["runtime_readiness"] = runtime_readiness
            if not ready:
                entry["state"] = "needs_configuration"
            elif entry.get("state") == "needs_configuration":
                entry["state"] = "enabled" if entry.get("enabled") else "installed_disabled"
            entry["last_operation"] = _operation(
                "check_configuration",
                "success" if ready else "attention_required",
                (
                    "configuration is ready"
                    if ready
                    else "missing configuration fields: %s" % ", ".join(missing)
                    if missing
                    else "sidecar requirements are not ready"
                ),
            )
            self.registry.save(registry)
            result = self._describe(module_id, entry, registry)
            result["missing_configuration_fields"] = missing
            result["missing_requirements"] = (
                list(sidecar_readiness.missing_requirements)
                if sidecar_readiness else []
            )
            result["missing_runtime_requirements"] = [
                check["id"]
                for check in runtime_readiness["checks"]
                if check["status"] != "ready"
            ]
            return result

    def _ensure_enable_dependencies(
        self, registry: Dict[str, Any], manifest: ModuleManifest
    ) -> None:
        missing, disabled = [], []
        for dependency in manifest.dependencies:
            if dependency in CORE_RESERVED_MODULE_IDS:
                continue
            entry = registry["modules"].get(dependency)
            if not isinstance(entry, dict):
                missing.append(dependency)
            elif not entry.get("enabled"):
                disabled.append(dependency)
        if missing:
            raise ModuleConflictError("missing required modules: %s" % ", ".join(missing))
        if disabled:
            raise ModuleConflictError("required modules are disabled: %s" % ", ".join(disabled))
        enabled = {
            key for key, entry in registry["modules"].items()
            if (
                key != manifest.id
                and key not in CORE_RESERVED_MODULE_IDS
                and isinstance(entry, dict)
                and entry.get("enabled")
            )
        }
        collisions = sorted(set(manifest.conflicts) & enabled)
        for module_id in enabled:
            other = self._manifest_from_entry(registry["modules"][module_id])
            if manifest.id in other.conflicts:
                collisions.append(module_id)
        if collisions:
            raise ModuleConflictError("conflicting modules are enabled: %s" % ", ".join(sorted(set(collisions))))

    def enable(self, module_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            manifest = self._manifest_from_entry(entry)
            if entry.get("enabled") and entry.get("state") == "enabled":
                return self._describe(module_id, entry, registry)
            self._ensure_enable_dependencies(registry, manifest)
            package_root = self._package_root_for_entry(entry)
            deployment = (
                self._sidecar_deployment_for_entry(module_id, entry)
                if manifest.type == "sidecar"
                else None
            )
            ready, missing, runtime_readiness, sidecar_readiness = self._configuration_status(
                package_root,
                manifest,
                deployment,
            )
            entry["configuration_ready"] = ready
            entry["sidecar_readiness"] = (
                sidecar_readiness.to_dict() if sidecar_readiness else None
            )
            entry["runtime_readiness"] = runtime_readiness
            if not ready:
                entry["enabled"] = False
                entry["state"] = "needs_configuration"
                entry["last_operation"] = _operation(
                    "enable",
                    "attention_required",
                    (
                        "runtime requirements are not ready"
                        if not runtime_readiness["ready"]
                        else "sidecar requirements are not ready"
                        if sidecar_readiness and sidecar_readiness.status != READINESS_READY
                        else "module configuration is incomplete"
                    ),
                )
                self.registry.save(registry)
                if not runtime_readiness["ready"]:
                    missing_runtime = ", ".join(
                        check["id"]
                        for check in runtime_readiness["checks"]
                        if check["status"] != "ready"
                    )
                    raise ModuleConflictError(
                        "module runtime requirements are not ready: %s" % missing_runtime
                    )
                if sidecar_readiness and sidecar_readiness.status != READINESS_READY:
                    raise SidecarReadinessError(sidecar_readiness)
                raise ModuleConflictError("module configuration is incomplete")
            try:
                if (
                    manifest.type == "sidecar"
                    and self._sidecar_starts_automatically(manifest)
                ):
                    self._start_sidecar(manifest, package_root, deployment)
            except SidecarReadinessError as exc:
                entry["enabled"] = False
                entry["configuration_ready"] = False
                entry["sidecar_readiness"] = exc.readiness.to_dict()
                entry["state"] = "needs_configuration"
                entry["last_operation"] = _operation(
                    "enable",
                    "attention_required",
                    "sidecar requirements are not ready",
                )
                self.registry.save(registry)
                raise
            except Exception as exc:
                entry["enabled"] = False
                entry["state"] = "broken"
                entry["last_operation"] = _operation(
                    "enable", "failed", "sidecar start failed"
                )
                self.registry.save(registry)
                raise ModuleOperationError("sidecar start failed") from exc
            entry["enabled"] = True
            entry["state"] = "enabled"
            entry["restart_required"] = manifest.type == "in_process" and manifest.requires_restart
            entry["last_operation"] = _operation("enable", "success", "module enabled")
            self.registry.save(registry)
            return self._describe(module_id, entry, registry)

    def disable(self, module_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            manifest = self._manifest_from_entry(entry)
            if manifest.required:
                raise ModuleConflictError("required modules cannot be disabled")
            dependents = []
            for other_id, other_entry in registry["modules"].items():
                if (
                    other_id == module_id
                    or other_id in CORE_RESERVED_MODULE_IDS
                    or not other_entry.get("enabled")
                ):
                    continue
                if module_id in self._manifest_from_entry(other_entry).dependencies:
                    dependents.append(other_id)
            if dependents:
                raise ModuleConflictError("enabled modules depend on this module: %s" % ", ".join(dependents))
            if entry.get("enabled") and manifest.type == "sidecar":
                try:
                    package_root = self._package_root_for_entry(entry)
                    deployment = self._sidecar_deployment_for_entry(
                        module_id,
                        entry,
                    )
                    self._stop_sidecar(manifest, package_root, deployment)
                except Exception as exc:
                    entry["state"] = "broken"
                    entry["last_operation"] = _operation(
                        "disable", "failed", "%s: %s" % (type(exc).__name__, str(exc))
                    )
                    self.registry.save(registry)
                    raise ModuleOperationError("sidecar stop failed") from exc
            entry["enabled"] = False
            entry["state"] = "installed_disabled"
            entry["restart_required"] = manifest.type == "in_process" and manifest.requires_restart
            entry["last_operation"] = _operation("disable", "success", "module disabled")
            self.registry.save(registry)
            return self._describe(module_id, entry, registry)

    def rollback(
        self,
        module_id: str,
        *,
        expected_version: Optional[str] = None,
        expected_package_sha256: Optional[str] = None,
        expected_manifest_sha256: Optional[str] = None,
        require_official: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            previous = entry.get("previous_version")
            if not isinstance(previous, str) or previous not in entry.get("versions", {}):
                raise ModuleConflictError("no rollback version is available")
            if expected_version is not None and previous != expected_version:
                raise ModuleConflictError("requested rollback version is not the registered previous version")
            previous_record = entry["versions"][previous]
            if not isinstance(previous_record, dict):
                raise ModuleOperationError("rollback version metadata is invalid")
            if require_official:
                release = previous_record.get("release")
                if previous_record.get("source") != "official_github_release" or not isinstance(release, dict):
                    raise ModuleConflictError("rollback target is not an official catalog release")
                if previous_record.get("sha256") != expected_package_sha256:
                    raise ModuleConflictError("rollback package digest no longer matches the official catalog")
                if release.get("manifest_sha256") != expected_manifest_sha256:
                    raise ModuleConflictError("rollback manifest digest no longer matches the official catalog")
            current = entry.get("current_version")
            old_entry_snapshot = deepcopy(entry)
            previous_root = self._package_root_for_entry(entry, previous)
            tree_sha256 = previous_record.get("installed_tree_sha256")
            if require_official:
                if not isinstance(tree_sha256, str):
                    raise ModuleConflictError("rollback target predates installed-content verification")
                actual_tree_sha256 = self._hash_directory(
                    previous_root,
                    self._directory_files(previous_root),
                )
                if actual_tree_sha256 != tree_sha256:
                    raise ModuleConflictError("rollback target files no longer match the installed digest")
                manifest_bytes = (previous_root / "manifest.json").read_bytes()
                if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
                    raise ModuleConflictError("rollback manifest no longer matches the official catalog")
            previous_payload = json.loads((previous_root / "manifest.json").read_text(encoding="utf-8"))
            previous_manifest = validate_manifest(previous_payload, self.core_version)
            current_manifest = self._manifest_from_entry(entry)
            self._check_graph(registry, previous_manifest)
            sidecar_switched = bool(entry.get("enabled")) and current_manifest.type == "sidecar"
            previous_deployment = (
                self._build_sidecar_deployment_descriptor(
                    module_id,
                    previous,
                    previous_root,
                    previous_record.get("installed_tree_sha256"),
                )
                if sidecar_switched
                else None
            )
            if sidecar_switched:
                self._switch_sidecar(
                    entry,
                    current_manifest,
                    previous_manifest,
                    previous_root,
                    previous_deployment,
                )
            entry["current_version"] = previous
            entry["previous_version"] = current
            entry["manifest"] = previous_manifest.to_dict()
            entry["restart_required"] = bool(entry.get("enabled")) and previous_manifest.requires_restart
            entry["state"] = "enabled" if entry.get("enabled") else "installed_disabled"
            entry["last_operation"] = _operation("rollback", "success", "rolled back to %s" % previous)
            try:
                self.registry.save(registry)
            except Exception:
                if sidecar_switched:
                    self._restore_sidecar(
                        old_entry_snapshot,
                        current_manifest,
                        previous_manifest,
                        previous_root,
                        previous_deployment,
                    )
                raise
            return self._describe(module_id, entry, registry)

    def uninstall(self, module_id: str) -> Dict[str, Any]:
        with self._lock:
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            manifest = self._manifest_from_entry(entry)
            restart_required = bool(entry.get("restart_required"))
            if manifest.required:
                raise ModuleConflictError("required modules cannot be uninstalled")
            for other_id, other_entry in registry["modules"].items():
                if (
                    other_id == module_id
                    or other_id in CORE_RESERVED_MODULE_IDS
                    or not other_entry.get("enabled")
                ):
                    continue
                if module_id in self._manifest_from_entry(other_entry).dependencies:
                    raise ModuleConflictError("enabled module %s depends on this module" % other_id)
            if entry.get("enabled"):
                self.disable(module_id)
                registry = self.registry.load()
                entry = self._entry(registry, module_id)
                restart_required = restart_required or bool(entry.get("restart_required"))

            module_root = self.runtime_root / module_id
            if not _is_within(module_root, self.runtime_root):
                raise ModuleOperationError("refusing to remove an unsafe module path")
            tombstone = self.runtime_root / (".%s-uninstalling" % module_id)
            if tombstone.exists():
                raise ModuleConflictError("a previous uninstall cleanup is incomplete")
            renamed = False
            if module_root.exists():
                os.replace(str(module_root), str(tombstone))
                renamed = True
            removed_entry = registry["modules"].pop(module_id)
            try:
                self.registry.save(registry)
            except Exception:
                registry["modules"][module_id] = removed_entry
                if renamed and tombstone.exists():
                    os.replace(str(tombstone), str(module_root))
                raise
            if renamed:
                shutil.rmtree(str(tombstone))
            return {
                "module_id": module_id,
                "install_status": "available",
                "enabled": False,
                "configuration_ready": False,
                "requires_restart": manifest.requires_restart,
                "restart_required": restart_required,
                "data_preserved": True,
                "data_path": "modules/%s" % manifest.data_namespace,
                "available_actions": ["install_official", "install_local"],
                "last_operation": _operation("uninstall", "success", "program files removed; data preserved"),
            }

    def purge_data(self, module_id: str, confirmation: str) -> Dict[str, Any]:
        with self._lock:
            registry = self.registry.load()
            entry = self._entry(registry, module_id)
            manifest = self._manifest_from_entry(entry)
            if confirmation != module_id:
                raise ModuleConflictError("purge confirmation must exactly match the module id")
            target = self.data_root / manifest.data_namespace
            if not _is_within(target, self.data_root) or target == self.data_root:
                raise ModuleOperationError("refusing to purge an unsafe data path")
            existed = target.exists()
            if existed:
                shutil.rmtree(str(target))
            entry["last_operation"] = _operation("purge_data", "success", "module data removed")
            self.registry.save(registry)
            return {
                "module_id": module_id,
                "purged": existed,
                "data_path": "modules/%s" % manifest.data_namespace,
                "last_operation": entry["last_operation"],
            }

    def asset_path(self, module_id: str, relative_path: str) -> Path:
        registry = self.registry.load()
        entry = self._entry(registry, module_id)
        manifest = self._manifest_from_entry(entry)
        enabled = entry.get("enabled") and entry.get("state") == "enabled"
        configuration_sidecar = (
            manifest.type == "sidecar"
            and entry.get("state") == "needs_configuration"
            and not entry.get("enabled")
        )
        if not enabled and not configuration_sidecar:
            raise ModuleConflictError(
                "module assets are available only while enabled or while a sidecar needs configuration"
            )
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
            raise PackageValidationError("invalid module asset path")
        parts = PurePosixPath(relative_path).parts
        if PurePosixPath(relative_path).is_absolute() or any(part in {"", ".", ".."} for part in parts):
            raise PackageValidationError("module asset path escapes the package")
        if not manifest.dashboard_entrypoint:
            raise ModuleNotFoundError("module has no dashboard assets")
        package_root = self._package_root_for_entry(entry)
        dashboard_root = package_root / "dashboard"
        target = package_root.joinpath(*parts)
        if not _is_within(target, dashboard_root) or not target.is_file():
            raise ModuleNotFoundError("module asset was not found")
        return target

    def enabled_in_process_descriptors(self) -> List[Dict[str, Any]]:
        return [
            descriptor
            for descriptor in self.enabled_activation_descriptors()
            if descriptor["manifest_object"].type == "in_process"
        ]

    def enabled_activation_descriptors(self) -> List[Dict[str, Any]]:
        """Preflight and deterministically order the complete enabled graph."""

        registry = self.registry.load()
        nodes: Dict[str, Dict[str, Any]] = {}
        for module_id in sorted(registry["modules"]):
            if module_id in CORE_RESERVED_MODULE_IDS:
                continue
            entry = registry["modules"][module_id]
            if not isinstance(entry, dict) or not entry.get("enabled"):
                continue
            manifest_payload = entry.get("manifest")
            if isinstance(manifest_payload, dict) and module_id in (
                list(manifest_payload.get("dependencies") or [])
                + list(manifest_payload.get("optional_dependencies") or [])
            ):
                raise ModuleConflictError(
                    "module dependency self-cycle: %s" % module_id
                )
            try:
                manifest = self._manifest_from_entry(entry)
            except Exception as exc:
                raise ModuleConflictError(
                    "module manifest unavailable: %s" % module_id
                ) from exc
            current = entry.get("current_version")
            versions = entry.get("versions")
            record = versions.get(current) if isinstance(versions, dict) else None
            if (
                not isinstance(current, str)
                or not SEMVER_PATTERN.fullmatch(current)
                or current != manifest.version
                or not isinstance(record, dict)
            ):
                raise ModuleConflictError(
                    "module version mismatch: %s" % module_id
                )
            expected_relative = "%s/%s" % (module_id, current)
            if record.get("path") != expected_relative:
                raise ModuleConflictError(
                    "module package unavailable: %s" % module_id
                )
            package_root = self._package_root_for_entry(entry)
            if (
                not package_root.is_dir()
                or _is_link_or_reparse(package_root)
            ):
                raise ModuleConflictError(
                    "module package unavailable: %s" % module_id
                )
            deployment = (
                self._sidecar_deployment_for_entry(module_id, entry)
                if manifest.type == "sidecar"
                else None
            )
            nodes[module_id] = {
                "module_id": module_id,
                "manifest": manifest.to_dict(),
                "manifest_object": manifest,
                "package_root": str(package_root),
                "deployment": deployment,
                "entry": entry,
            }

        outgoing: Dict[str, set[str]] = {
            module_id: set() for module_id in nodes
        }
        indegree = {module_id: 0 for module_id in nodes}
        for module_id, descriptor in nodes.items():
            manifest = descriptor["manifest_object"]
            for dependency in manifest.dependencies:
                if dependency in CORE_RESERVED_MODULE_IDS:
                    continue
                dependency_entry = registry["modules"].get(dependency)
                if not isinstance(dependency_entry, dict):
                    raise ModuleConflictError(
                        "module dependency missing: %s->%s"
                        % (module_id, dependency)
                    )
                if not dependency_entry.get("enabled"):
                    raise ModuleConflictError(
                        "module dependency not enabled: %s->%s"
                        % (module_id, dependency)
                    )
                if dependency not in nodes:
                    raise ModuleConflictError(
                        "module dependency unavailable: %s->%s"
                        % (module_id, dependency)
                    )
                if (
                    not dependency_entry.get("configuration_ready")
                    or dependency_entry.get("state") in {
                        "broken",
                        "needs_configuration",
                    }
                ):
                    raise ModuleConflictError(
                        "module dependency unavailable: %s->%s"
                        % (module_id, dependency)
                    )
                if module_id not in outgoing[dependency]:
                    outgoing[dependency].add(module_id)
                    indegree[module_id] += 1
            for dependency in manifest.optional_dependencies:
                dependency_entry = registry["modules"].get(dependency)
                if (
                    dependency in nodes
                    and isinstance(dependency_entry, dict)
                    and dependency_entry.get("enabled")
                    and module_id not in outgoing[dependency]
                ):
                    outgoing[dependency].add(module_id)
                    indegree[module_id] += 1

        ready = sorted(
            module_id for module_id, count in indegree.items() if count == 0
        )
        ordered = []
        while ready:
            ordered.extend(ready)
            next_ready = []
            for module_id in ready:
                for consumer in sorted(outgoing[module_id]):
                    indegree[consumer] -= 1
                    if indegree[consumer] == 0:
                        heapq.heappush(next_ready, consumer)
            ready = [heapq.heappop(next_ready) for _ in range(len(next_ready))]
        if len(ordered) != len(nodes):
            cycle = sorted(
                module_id
                for module_id, count in indegree.items()
                if count > 0
            )
            raise ModuleConflictError(
                "module dependency cycle: %s" % ",".join(cycle)
            )
        return [nodes[module_id] for module_id in ordered]

    def record_load_results(self, results: Iterable[Dict[str, str]]) -> None:
        with self._lock:
            registry = self.registry.load()
            changed = False
            for result in results:
                module_id = result.get("module_id")
                if module_id in CORE_RESERVED_MODULE_IDS:
                    continue
                entry = registry["modules"].get(module_id)
                if not isinstance(entry, dict):
                    continue
                status = result.get("status")
                if status in {"loaded", "already_loaded"}:
                    entry["state"] = "enabled"
                    entry["restart_required"] = False
                    entry["last_operation"] = _operation("load", "success", "in-process entrypoint loaded")
                else:
                    entry["state"] = "broken"
                    entry["last_operation"] = _operation("load", "failed", result.get("error", "load failed"))
                changed = True
            if changed:
                self.registry.save(registry)

    def start_sidecar_descriptor(
        self,
        descriptor: Dict[str, Any],
    ) -> SidecarReadiness:
        """Start one sidecar from a descriptor produced by the graph preflight."""

        manifest = descriptor["manifest_object"]
        if manifest.type != "sidecar":
            raise ModuleConflictError(
                "module is not a sidecar: %s" % manifest.id
            )
        deployment = descriptor.get("deployment")
        if not isinstance(deployment, SidecarDeploymentDescriptor):
            raise ModuleConflictError(
                "module deployment unavailable: %s" % manifest.id
            )
        return self._start_sidecar(
            manifest,
            Path(descriptor["package_root"]),
            deployment,
        )

    def stop_sidecar_descriptor(self, descriptor: Dict[str, Any]) -> None:
        """Stop one preflighted sidecar; callers choose reverse graph order."""

        manifest = descriptor["manifest_object"]
        if manifest.type != "sidecar":
            raise ModuleConflictError(
                "module is not a sidecar: %s" % manifest.id
            )
        deployment = descriptor.get("deployment")
        if not isinstance(deployment, SidecarDeploymentDescriptor):
            raise ModuleConflictError(
                "module deployment unavailable: %s" % manifest.id
            )
        self._stop_sidecar(
            manifest,
            Path(descriptor["package_root"]),
            deployment,
        )

    def start_enabled_sidecars(self) -> List[Dict[str, Any]]:
        descriptors = [
            descriptor
            for descriptor in self.enabled_activation_descriptors()
            if (
                descriptor["manifest_object"].type == "sidecar"
                and self._sidecar_starts_automatically(
                    descriptor["manifest_object"]
                )
            )
        ]
        results: List[Dict[str, Any]] = []
        readiness_by_id: Dict[str, Dict[str, object]] = {}
        for descriptor in descriptors:
            module_id = descriptor["module_id"]
            try:
                readiness = self.start_sidecar_descriptor(descriptor)
                readiness_by_id[module_id] = readiness.to_dict()
                results.append({"module_id": module_id, "status": "started"})
            except SidecarReadinessError as exc:
                results.append({
                    "module_id": module_id,
                    "status": exc.readiness.status,
                    "code": exc.readiness.code,
                    "sidecar_readiness": exc.readiness.to_dict(),
                })
            except Exception:
                results.append({"module_id": module_id, "status": "failed"})

        if results:
            registry = self.registry.load()
            for result in results:
                entry = registry["modules"].get(result["module_id"])
                if not isinstance(entry, dict):
                    continue
                status = result["status"]
                if status == "started":
                    entry["configuration_ready"] = True
                    entry["sidecar_readiness"] = readiness_by_id[result["module_id"]]
                    entry["state"] = "enabled"
                    entry["last_operation"] = _operation(
                        "start", "success", "sidecar started and healthy"
                    )
                elif status in {"needs_configuration", "unavailable"}:
                    entry["configuration_ready"] = False
                    entry["sidecar_readiness"] = result["sidecar_readiness"]
                    entry["state"] = "needs_configuration"
                    entry["last_operation"] = _operation(
                        "start",
                        "attention_required",
                        "sidecar requirements are not ready",
                    )
                elif status == "rolled_back":
                    entry["restart_required"] = True
                    entry["last_operation"] = _operation(
                        "start", "rolled_back", "module assembly was rolled back"
                    )
                else:
                    entry["state"] = "broken"
                    entry["last_operation"] = _operation(
                        "start", "failed", "sidecar startup failed"
                    )
            self.registry.save(registry)
        return results

    def stop_enabled_sidecars(self) -> List[Dict[str, str]]:
        descriptors = [
            descriptor
            for descriptor in reversed(self.enabled_activation_descriptors())
            if descriptor["manifest_object"].type == "sidecar"
        ]
        results = []
        for descriptor in descriptors:
            module_id = descriptor["module_id"]
            try:
                self.stop_sidecar_descriptor(descriptor)
                results.append({"module_id": module_id, "status": "stopped"})
            except Exception:
                results.append({"module_id": module_id, "status": "failed"})
        return results


def re_drive_path(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"
