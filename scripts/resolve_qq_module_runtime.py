"""Build and inspect a regenerable QQ sidecar dependency deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import uuid
import re
from pathlib import Path
from typing import Any, Iterable


MODULE_ID = "qq_bridge"
PACKAGE_NAME = "project-kei-qq-bridge"
NODE_RANGE = "20.x || 22.x || 24.x || 26.x"
MARKER_NAME = ".project-kei-deployment.json"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
MARKER_FIELDS = {
    "schema_version",
    "module_id",
    "version",
    "installed_tree_sha256",
    "package_json_sha256",
    "lock_sha256",
    "node_version",
    "npm_version",
}
SIDECAR_FILES = (
    "package.json",
    "package-lock.json",
    "src/bridge_core.mjs",
    "src/business_menu.mjs",
    "src/daily_briefing_scheduler.mjs",
    "src/focus_encouragement_scheduler.mjs",
    "src/gateway_client.mjs",
    "src/index.mjs",
    "src/life_support_scheduler.mjs",
    "src/shutdown_control.mjs",
    "src/state_store.mjs",
    "src/voice_reply.mjs",
)


class DeploymentError(RuntimeError):
    """A finite failure that never contains a local path or registry payload."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _lstat_regular(path: Path, missing_code: str) -> os.stat_result:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise DeploymentError(missing_code) from exc
    if _is_link_or_reparse(metadata) or metadata.st_nlink != 1:
        raise DeploymentError("qq_module_link_rejected")
    if not stat.S_ISREG(metadata.st_mode):
        raise DeploymentError("qq_module_package_invalid")
    return metadata


def _read_json(path: Path, missing_code: str) -> dict[str, Any]:
    _lstat_regular(path, missing_code)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeploymentError("qq_module_metadata_invalid") from exc
    if not isinstance(payload, dict):
        raise DeploymentError("qq_module_metadata_invalid")
    return payload


def _sha256(path: Path) -> str:
    _lstat_regular(path, "qq_module_package_invalid")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DeploymentError("qq_module_package_invalid") from exc
    return digest.hexdigest()


def _validate_lock(sidecar_root: Path, version: str) -> str:
    package = _read_json(sidecar_root / "package.json", "qq_module_lock_missing")
    lock_path = sidecar_root / "package-lock.json"
    lock = _read_json(lock_path, "qq_module_lock_missing")
    dependencies = package.get("dependencies")
    engines = package.get("engines")
    packages = lock.get("packages")
    lock_root = packages.get("") if isinstance(packages, dict) else None
    public_entries = isinstance(packages, dict) and all(
        isinstance(declaration, dict)
        and isinstance(declaration.get("resolved"), str)
        and declaration["resolved"].startswith("https://registry.npmjs.org/")
        and isinstance(declaration.get("integrity"), str)
        and bool(declaration["integrity"])
        for relative, declaration in packages.items()
        if relative
    )
    dependency_entries = (
        isinstance(packages, dict)
        and isinstance(dependencies, dict)
        and all(f"node_modules/{name}" in packages for name in dependencies)
    )
    if (
        package.get("name") != PACKAGE_NAME
        or package.get("version") != version
        or package.get("private") is not True
        or package.get("type") != "module"
        or not isinstance(dependencies, dict)
        or engines != {"node": NODE_RANGE}
        or lock.get("name") != PACKAGE_NAME
        or lock.get("version") != version
        or lock.get("lockfileVersion") != 3
        or not isinstance(lock_root, dict)
        or lock_root.get("name") != PACKAGE_NAME
        or lock_root.get("version") != version
        or lock_root.get("dependencies") != dependencies
        or lock_root.get("engines") != engines
        or not public_entries
        or not dependency_entries
    ):
        raise DeploymentError("qq_module_lock_invalid")
    return _sha256(lock_path)


def _assert_tree_safe(root: Path, *, require_exists: bool = True) -> None:
    try:
        root_metadata = os.lstat(root)
    except FileNotFoundError:
        if require_exists:
            raise DeploymentError("qq_module_deployment_missing")
        return
    except OSError as exc:
        raise DeploymentError("qq_module_deployment_invalid") from exc
    if _is_link_or_reparse(root_metadata):
        raise DeploymentError("qq_module_link_rejected")
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise DeploymentError("qq_module_deployment_invalid")
    try:
        for current, directories, files in os.walk(root, followlinks=False):
            for name in (*directories, *files):
                metadata = os.lstat(Path(current) / name)
                if _is_link_or_reparse(metadata) or (
                    stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1
                ):
                    raise DeploymentError("qq_module_link_rejected")
    except OSError as exc:
        raise DeploymentError("qq_module_deployment_invalid") from exc


def _remove_tree_no_follow(root: Path) -> None:
    try:
        metadata = os.lstat(root)
    except FileNotFoundError:
        return
    if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        try:
            root.unlink()
        except IsADirectoryError:
            os.rmdir(root)
        return
    with os.scandir(root) as entries:
        children = [Path(entry.path) for entry in entries]
    for child in children:
        try:
            child_metadata = os.lstat(child)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(child_metadata.st_mode) and not _is_link_or_reparse(child_metadata):
            _remove_tree_no_follow(child)
        else:
            try:
                child.unlink()
            except IsADirectoryError:
                os.rmdir(child)
    os.rmdir(root)


def _copy_allowlist(source_root: Path, destination_root: Path) -> None:
    for relative in SIDECAR_FILES:
        source = source_root.joinpath(*relative.split("/"))
        destination = destination_root.joinpath(*relative.split("/"))
        _lstat_regular(source, "qq_module_package_invalid")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        _lstat_regular(destination, "qq_module_deployment_invalid")
        if _sha256(source) != _sha256(destination):
            raise DeploymentError("qq_module_copy_failed")


def _descriptor(project_root: Path):
    server_root = project_root / "server"
    server_path = str(server_root)
    sys.path.insert(0, server_path)
    try:
        from core.modules.exceptions import ModuleNotFoundError
        from core.modules.manager import ModuleManager
    finally:
        if sys.path and sys.path[0] == server_path:
            sys.path.pop(0)
    manager = ModuleManager(
        runtime_root=server_root / "runtime" / "modules",
        registry_path=server_root / "data" / "module_registry.json",
        data_root=server_root / "data" / "modules",
    )
    try:
        description = manager.get(MODULE_ID)
        descriptor = manager.resolve_sidecar_deployment(MODULE_ID)
    except ModuleNotFoundError:
        return None, None
    except Exception as exc:
        raise DeploymentError("qq_module_registry_invalid") from exc
    if (
        description.get("package_source") not in {
            "official_github_release", "local_import"
        }
        or description.get("installed_version") != descriptor.version
        or description.get("type") != "sidecar"
    ):
        raise DeploymentError("qq_module_registry_invalid")
    try:
        actual_digest = manager.calculate_package_sha256(descriptor.package_root)
    except Exception as exc:
        raise DeploymentError("qq_module_package_invalid") from exc
    if actual_digest != descriptor.installed_tree_sha256:
        raise DeploymentError("qq_module_package_digest_mismatch")
    manifest = _read_json(
        descriptor.package_root / "manifest.json",
        "qq_module_package_invalid",
    )
    sidecar = manifest.get("sidecar") if isinstance(manifest, dict) else None
    if (
        manifest.get("id") != MODULE_ID
        or manifest.get("version") != descriptor.version
        or manifest.get("type") != "sidecar"
        or not isinstance(sidecar, dict)
        or sidecar.get("adapter") != MODULE_ID
    ):
        raise DeploymentError("qq_module_package_invalid")
    return manager, descriptor


def _expected_marker(
    descriptor,
    package_json_sha256: str,
    lock_sha256: str,
    node_version: str,
    npm_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "version": descriptor.version,
        "installed_tree_sha256": descriptor.installed_tree_sha256,
        "package_json_sha256": package_json_sha256,
        "lock_sha256": lock_sha256,
        "node_version": node_version,
        "npm_version": npm_version,
    }


def _validate_marker_versions(node_version: str, npm_version: str) -> None:
    if (
        not isinstance(node_version, str)
        or not VERSION_PATTERN.fullmatch(node_version)
        or int(node_version.split(".", 1)[0]) not in {20, 22, 24, 26}
        or not isinstance(npm_version, str)
        or not VERSION_PATTERN.fullmatch(npm_version)
        or int(npm_version.split(".", 1)[0]) not in {9, 10, 11}
    ):
        raise DeploymentError("qq_module_deployment_marker_invalid")


def _assert_deployment_layout(root: Path) -> None:
    try:
        names = {entry.name for entry in os.scandir(root)}
    except OSError as exc:
        raise DeploymentError("qq_module_deployment_invalid") from exc
    allowed = {
        MARKER_NAME,
        "package.json",
        "package-lock.json",
        "src",
        "node_modules",
    }
    if not names.issubset(allowed):
        raise DeploymentError("qq_module_deployment_layout_invalid")


def _safe_staging(descriptor, locator: str) -> Path:
    prefix = f"{MODULE_ID}/.{descriptor.version}.staging-"
    if not isinstance(locator, str) or not locator.startswith(prefix):
        raise DeploymentError("qq_module_staging_invalid")
    token = locator[len(prefix) :]
    if len(token) != 32 or any(character not in "0123456789abcdef" for character in token):
        raise DeploymentError("qq_module_staging_invalid")
    return descriptor.dependency_deployment_root.parent / f".{descriptor.version}.staging-{token}"


def inspect(project_root: Path) -> dict[str, str]:
    _, descriptor = _descriptor(project_root)
    if descriptor is None:
        return {"status": "absent"}
    source_sidecar = descriptor.package_root / "sidecar"
    lock_sha256 = _validate_lock(source_sidecar, descriptor.version)
    deployment_root = descriptor.dependency_deployment_root
    if not deployment_root.exists():
        return {"status": "missing", "code": "qq_module_deployment_missing"}
    _assert_tree_safe(deployment_root)
    marker = _read_json(
        deployment_root / MARKER_NAME,
        "qq_module_deployment_marker_missing",
    )
    package_json_sha256 = _sha256(source_sidecar / "package.json")
    if set(marker) != MARKER_FIELDS:
        raise DeploymentError("qq_module_deployment_marker_invalid")
    _validate_marker_versions(marker.get("node_version"), marker.get("npm_version"))
    expected_without_versions = _expected_marker(
        descriptor,
        package_json_sha256,
        lock_sha256,
        marker["node_version"],
        marker["npm_version"],
    )
    if marker != expected_without_versions:
        raise DeploymentError("qq_module_deployment_marker_invalid")
    _assert_deployment_layout(deployment_root)
    for relative in SIDECAR_FILES:
        source = source_sidecar.joinpath(*relative.split("/"))
        deployed = deployment_root.joinpath(*relative.split("/"))
        if _sha256(source) != _sha256(deployed):
            raise DeploymentError("qq_module_deployment_content_invalid")
    _lstat_regular(
        deployment_root / "node_modules" / "ws" / "package.json",
        "qq_module_dependencies_missing",
    )
    return {"status": "ready"}


def prepare(project_root: Path) -> dict[str, str]:
    current = inspect(project_root)
    if current["status"] in {"absent", "ready"}:
        return current
    _, descriptor = _descriptor(project_root)
    assert descriptor is not None
    parent = descriptor.dependency_deployment_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        parent_metadata = os.lstat(parent)
    except OSError as exc:
        raise DeploymentError("qq_module_deployment_invalid") from exc
    if _is_link_or_reparse(parent_metadata) or not stat.S_ISDIR(parent_metadata.st_mode):
        raise DeploymentError("qq_module_link_rejected")
    token = uuid.uuid4().hex
    staging = parent / f".{descriptor.version}.staging-{token}"
    staging.mkdir()
    try:
        _copy_allowlist(descriptor.package_root / "sidecar", staging)
        _validate_lock(staging, descriptor.version)
    except Exception:
        _remove_tree_no_follow(staging)
        raise
    return {
        "status": "prepared",
        "locator": f"{MODULE_ID}/.{descriptor.version}.staging-{token}",
    }


def commit(
    project_root: Path,
    locator: str,
    node_version: str,
    npm_version: str,
) -> dict[str, str]:
    _, descriptor = _descriptor(project_root)
    if descriptor is None:
        raise DeploymentError("qq_module_not_installed")
    staging = _safe_staging(descriptor, locator)
    _assert_tree_safe(staging)
    source_sidecar = descriptor.package_root / "sidecar"
    lock_sha256 = _validate_lock(source_sidecar, descriptor.version)
    package_json_sha256 = _sha256(source_sidecar / "package.json")
    _validate_marker_versions(node_version, npm_version)
    if _validate_lock(staging, descriptor.version) != lock_sha256:
        raise DeploymentError("qq_module_deployment_content_invalid")
    for relative in SIDECAR_FILES:
        source = source_sidecar.joinpath(*relative.split("/"))
        deployed = staging.joinpath(*relative.split("/"))
        if _sha256(source) != _sha256(deployed):
            raise DeploymentError("qq_module_deployment_content_invalid")
    _lstat_regular(
        staging / "node_modules" / "ws" / "package.json",
        "qq_module_dependencies_missing",
    )
    (staging / MARKER_NAME).write_text(
        json.dumps(
            _expected_marker(
                descriptor,
                package_json_sha256,
                lock_sha256,
                node_version,
                npm_version,
            ),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _lstat_regular(staging / MARKER_NAME, "qq_module_deployment_marker_invalid")
    _assert_deployment_layout(staging)
    _assert_tree_safe(staging)

    final = descriptor.dependency_deployment_root
    backup = final.parent / f".{descriptor.version}.backup-{uuid.uuid4().hex}"
    moved_old = False
    try:
        if final.exists():
            _assert_tree_safe(final)
            os.replace(final, backup)
            moved_old = True
        os.replace(staging, final)
    except Exception as exc:
        if moved_old and not final.exists() and backup.exists():
            os.replace(backup, final)
        raise DeploymentError("qq_module_deployment_switch_failed") from exc
    if backup.exists():
        try:
            _remove_tree_no_follow(backup)
        except (OSError, DeploymentError):
            pass
    return {"status": "ready"}


def abort(project_root: Path, locator: str) -> dict[str, str]:
    _, descriptor = _descriptor(project_root)
    if descriptor is None:
        return {"status": "absent"}
    staging = _safe_staging(descriptor, locator)
    _remove_tree_no_follow(staging)
    return {"status": "aborted"}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", choices=("inspect", "prepare", "commit", "abort"))
    parser.add_argument("--locator")
    parser.add_argument("--node-version")
    parser.add_argument("--npm-version")
    args = parser.parse_args(list(argv) if argv is not None else None)
    project_root = Path(__file__).absolute().parents[1]
    try:
        if args.action == "inspect":
            result = inspect(project_root)
        elif args.action == "prepare":
            result = prepare(project_root)
        elif args.action == "commit":
            result = commit(
                project_root,
                args.locator or "",
                args.node_version or "",
                args.npm_version or "",
            )
        else:
            result = abort(project_root, args.locator or "")
    except DeploymentError as exc:
        result = {"status": "error", "code": exc.code}
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 3
    except Exception:
        result = {"status": "error", "code": "qq_module_deployment_failed"}
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 3
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
