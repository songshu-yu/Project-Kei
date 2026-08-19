"""Fixed Core adapter for the versioned Project Kei QQ bridge sidecar.

The adapter never accepts a command, cwd, environment mapping or configuration
path from an HTTP request or manifest. Production composition supplies the two
project-owned persistent paths once; ModuleManager supplies the validated
current immutable package and its separate dependency deployment descriptor.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from core.modules.sidecar import (
    DEPENDENCY_DEPLOYMENT_MARKER,
    SidecarDeploymentDescriptor,
    SidecarReadiness,
)


ProcessFactory = Callable[..., Any]
ProcessProbe = Callable[[Path], bool]
ProcessIdentityProbe = Callable[[Path, int], bool]
NodeResolver = Callable[[], Optional[str]]
ADAPTER_NAME = "qq_bridge"
MODULE_ID = "qq_bridge"
BRIDGE_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = BRIDGE_ROOT / ".env"
DEFAULT_DATA_ROOT = BRIDGE_ROOT / "data"

_SAFE_CHILD_ENV_NAMES = (
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TZ",
    "WINDIR",
)
_DEPLOYMENT_MARKER_NAME = DEPENDENCY_DEPLOYMENT_MARKER
_DEPLOYMENT_TOP_LEVEL = {
    _DEPLOYMENT_MARKER_NAME,
    "package.json",
    "package-lock.json",
    "src",
    "node_modules",
}
_DEPLOYMENT_MARKER_FIELDS = {
    "schema_version",
    "module_id",
    "version",
    "installed_tree_sha256",
    "package_json_sha256",
    "lock_sha256",
    "node_version",
    "npm_version",
}
_SIDECAR_SOURCE_NAMES = {
    "bridge_core.mjs",
    "business_menu.mjs",
    "daily_briefing_scheduler.mjs",
    "focus_encouragement_scheduler.mjs",
    "gateway_client.mjs",
    "index.mjs",
    "life_support_scheduler.mjs",
    "state_store.mjs",
    "shutdown_control.mjs",
    "voice_reply.mjs",
}
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOOL_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
_GATEWAY_GENERATION = re.compile(r"^[0-9a-f]{32}$")
_GATEWAY_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,64}$")
_GATEWAY_ERROR_CODES = {
    "closed",
    "gateway_failed",
    "gateway_hello_timeout",
    "gateway_request_failed",
    "gateway_rejected",
    "gateway_response_invalid",
    "gateway_ready_timeout",
    "gateway_url_invalid",
    "gateway_url_missing",
    "gateway_url_rejected",
    "heartbeat_send_failed",
    "heartbeat_timeout",
    "identify_send_failed",
    "invalid_session",
    "server_reconnect",
    "token_rejected",
    "token_request_failed",
    "token_response_invalid",
    "token_missing",
    "websocket_closed",
    "websocket_constructor_failed",
    "websocket_error",
}
_VOICE_RESULT_CODES = {
    "voice_sent",
    "voice_disabled",
    "voice_text_invalid",
    "voice_unavailable",
    "voice_duplicate",
    "voice_cancelled",
    "voice_metadata_invalid",
    "voice_audio_invalid",
    "voice_audio_too_large",
    "voice_upload_failed",
    "voice_file_info_invalid",
    "voice_message_failed",
    "voice_delivery_failed",
}
_GATEWAY_STATES = {
    "connecting",
    "identified_or_ready",
    "reconnect_wait",
    "failed",
    "stopped",
}
_GATEWAY_STATUS_FIELDS = {
    "schema_version",
    "generation",
    "pid",
    "shutdown_control_ready",
    "state",
    "gateway_ready",
    "heartbeat_healthy",
    "last_error_code",
    "last_close_code",
    "reconnect_count",
    "last_ready_at",
    "voice_last_result_code",
    "voice_last_attempt_at",
    "updated_at",
}


def _strict_json_object(text: str) -> dict[str, Any]:
    def pairs_to_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    payload = json.loads(
        text,
        object_pairs_hook=pairs_to_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid JSON")),
    )
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


@dataclass(frozen=True)
class QQBridgeReadiness:
    ready: bool
    state: str
    running: bool
    package_ready: bool
    env_configured: bool
    node_ready: bool
    dependencies_ready: bool
    reason: str
    process_running: bool = False
    can_stop: bool = False
    gateway_ready: bool = False
    gateway_state: str = "stopped"
    gateway_last_error_code: str | None = None
    gateway_last_close_code: int | None = None
    gateway_reconnect_count: int = 0
    gateway_last_ready_at: int | None = None
    voice_last_result_code: str | None = None
    voice_last_attempt_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QQBridgeAdapterError(RuntimeError):
    """Finite adapter failure without paths, commands or upstream text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class QQBridgeSidecarAdapter:
    """Start exactly one installed QQ bridge and stop only the owned process."""

    adapter_name = ADAPTER_NAME
    start_automatically = False
    entry_relative_path = Path("sidecar") / "src" / "index.mjs"

    def __init__(
        self,
        *,
        env_path: str | Path,
        data_root: str | Path,
        process_factory: ProcessFactory = subprocess.Popen,
        process_probe: ProcessProbe | None = None,
        process_identity_probe: ProcessIdentityProbe | None = None,
        node_resolver: NodeResolver | None = None,
        stop_timeout_seconds: float = 10.0,
        gateway_status_max_age_seconds: float = 180.0,
        now_ms: Callable[[], int] | None = None,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        # These two paths are fixed by trusted production composition.  Keep
        # construction lexical: resolving them would stat user-owned secret
        # and runtime locations during Core import.
        self._env_path = Path(os.path.abspath(os.fspath(env_path)))
        self._data_root = Path(os.path.abspath(os.fspath(data_root)))
        self._process_factory = process_factory
        self._process_probe = process_probe
        self._process_identity_probe = process_identity_probe
        self._node_resolver = node_resolver or (lambda: shutil.which("node"))
        self._stop_timeout_seconds = max(0.1, min(float(stop_timeout_seconds), 30.0))
        self._gateway_status_max_age_ms = int(
            max(30.0, min(float(gateway_status_max_age_seconds), 600.0)) * 1000
        )
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        source_environment = dict(base_environment) if base_environment is not None else os.environ
        self._base_environment = {
            name: str(source_environment[name])
            for name in _SAFE_CHILD_ENV_NAMES
            if source_environment.get(name)
        }
        self._lock = threading.RLock()
        self._process: Any = None
        self._package_root: Path | None = None
        self._dependency_root: Path | None = None

    def _gateway_status(
        self,
        expected_pid: int | None,
        dependency_root: Path | None = None,
    ) -> dict[str, Any] | None:
        status_path = self._data_root / "gateway_status.json"
        try:
            if (
                not status_path.is_file()
                or status_path.is_symlink()
                or status_path.stat().st_size > 4096
            ):
                return None
            snapshot = _strict_json_object(status_path.read_text(encoding="utf-8"))
            now_ms = self._now_ms()
            if (
                set(snapshot) != _GATEWAY_STATUS_FIELDS
                or snapshot["schema_version"] != 1
                or not isinstance(snapshot["generation"], str)
                or not _GATEWAY_GENERATION.fullmatch(snapshot["generation"])
                or not isinstance(snapshot["pid"], int)
                or isinstance(snapshot["pid"], bool)
                or (expected_pid is not None and snapshot["pid"] != expected_pid)
                or snapshot["shutdown_control_ready"] is not True
                or snapshot["state"] not in _GATEWAY_STATES
                or not isinstance(snapshot["gateway_ready"], bool)
                or not isinstance(snapshot["heartbeat_healthy"], bool)
                or not isinstance(snapshot["reconnect_count"], int)
                or isinstance(snapshot["reconnect_count"], bool)
                or not 0 <= snapshot["reconnect_count"] <= 1_000_000
                or not isinstance(snapshot["updated_at"], int)
                or isinstance(snapshot["updated_at"], bool)
                or snapshot["updated_at"] > now_ms + 5_000
                or now_ms - snapshot["updated_at"] > self._gateway_status_max_age_ms
            ):
                return None
            if expected_pid is None:
                if dependency_root is None or self._process_identity_probe is None:
                    return None
                try:
                    if not self._process_identity_probe(dependency_root, snapshot["pid"]):
                        return None
                except Exception:
                    return None
            error_code = snapshot["last_error_code"]
            close_code = snapshot["last_close_code"]
            last_ready_at = snapshot["last_ready_at"]
            voice_result_code = snapshot["voice_last_result_code"]
            voice_attempt_at = snapshot["voice_last_attempt_at"]
            if (
                (error_code is not None and (
                    not isinstance(error_code, str)
                    or not _GATEWAY_SAFE_CODE.fullmatch(error_code)
                    or error_code not in _GATEWAY_ERROR_CODES
                ))
                or (close_code is not None and (
                    not isinstance(close_code, int)
                    or isinstance(close_code, bool)
                    or not 1000 <= close_code <= 4999
                ))
                or (last_ready_at is not None and (
                    not isinstance(last_ready_at, int)
                    or isinstance(last_ready_at, bool)
                    or last_ready_at <= 0
                    or last_ready_at > now_ms + 5_000
                ))
                or (voice_result_code is not None and (
                    not isinstance(voice_result_code, str)
                    or voice_result_code not in _VOICE_RESULT_CODES
                ))
                or (voice_attempt_at is not None and (
                    not isinstance(voice_attempt_at, int)
                    or isinstance(voice_attempt_at, bool)
                    or voice_attempt_at <= 0
                    or voice_attempt_at > now_ms + 5_000
                ))
                or ((voice_result_code is None) != (voice_attempt_at is None))
            ):
                return None
            if snapshot["gateway_ready"] and (
                snapshot["state"] != "identified_or_ready"
                or not snapshot["heartbeat_healthy"]
                or last_ready_at is None
            ):
                return None
            return snapshot
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return None

    @property
    def configuration_path(self) -> Path:
        """Trusted persistent path for the PK-140 configuration component."""

        return self._env_path

    @property
    def data_root(self) -> Path:
        """Trusted persistent runtime root fixed by production composition."""

        return self._data_root

    @staticmethod
    def _trusted_package_root(package_root: str | Path) -> Path:
        root = Path(package_root).resolve()
        if not root.is_dir():
            raise QQBridgeAdapterError("package_invalid")
        return root

    def _tracked_running(
        self,
        package_root: Path,
        dependency_root: Path | None = None,
    ) -> bool:
        return (
            self._process is not None
            and self._package_root == package_root
            and (
                dependency_root is None
                or self._dependency_root == dependency_root
            )
            and self._process.poll() is None
        )

    def _running(
        self,
        package_root: Path,
        dependency_root: Path | None = None,
    ) -> bool:
        if self._tracked_running(package_root, dependency_root):
            return True
        if self._process_probe is None:
            return False
        try:
            return bool(self._process_probe(dependency_root or package_root))
        except Exception:
            return False

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_regular_file(path: Path) -> bool:
        return path.is_file() and not path.is_symlink()

    def _deployment_validation_code(
        self,
        package_root: Path,
        dependency_root: Path,
        deployment: SidecarDeploymentDescriptor | None,
    ) -> str:
        try:
            if not dependency_root.exists():
                return "deployment_missing"
            if not dependency_root.is_dir() or dependency_root.is_symlink():
                return "deployment_invalid"
            top_level = {path.name for path in dependency_root.iterdir()}
            if top_level - _DEPLOYMENT_TOP_LEVEL:
                return "deployment_invalid"
            marker_path = dependency_root / _DEPLOYMENT_MARKER_NAME
            if _DEPLOYMENT_MARKER_NAME not in top_level:
                return "deployment_missing"
            if top_level != _DEPLOYMENT_TOP_LEVEL:
                if "node_modules" not in top_level:
                    return "dependencies_missing"
                return "deployment_invalid"
            package_json = dependency_root / "package.json"
            lockfile = dependency_root / "package-lock.json"
            source_root = dependency_root / "src"
            node_modules = dependency_root / "node_modules"
            if not all(
                self._safe_regular_file(path)
                for path in (marker_path, package_json, lockfile)
            ):
                return "deployment_invalid"
            if (
                not source_root.is_dir()
                or source_root.is_symlink()
                or not node_modules.is_dir()
                or node_modules.is_symlink()
            ):
                return "deployment_invalid"
            if {path.name for path in source_root.iterdir()} != _SIDECAR_SOURCE_NAMES:
                return "deployment_invalid"
            if not all(self._safe_regular_file(path) for path in source_root.iterdir()):
                return "deployment_invalid"
            if marker_path.stat().st_size > 4096:
                return "deployment_invalid"
            marker = _strict_json_object(marker_path.read_text(encoding="utf-8"))
            if set(marker) != _DEPLOYMENT_MARKER_FIELDS:
                return "deployment_invalid"
            if (
                marker["schema_version"] != 1
                or marker["module_id"] != MODULE_ID
                or not isinstance(marker["version"], str)
                or not _SEMVER.fullmatch(marker["version"])
                or not all(
                    isinstance(marker[name], str)
                    and _SHA256.fullmatch(marker[name])
                    for name in (
                        "installed_tree_sha256",
                        "package_json_sha256",
                        "lock_sha256",
                    )
                )
                or not isinstance(marker["node_version"], str)
                or not _TOOL_VERSION.fullmatch(marker["node_version"])
                or not isinstance(marker["npm_version"], str)
                or not _TOOL_VERSION.fullmatch(marker["npm_version"])
            ):
                return "deployment_invalid"
            if deployment is None:
                return "deployment_invalid"
            if (
                marker["version"] != deployment.version
                or marker["installed_tree_sha256"]
                != deployment.installed_tree_sha256
            ):
                return "deployment_invalid"
            installed_sidecar = package_root / "sidecar"
            installed_package = installed_sidecar / "package.json"
            installed_lock = installed_sidecar / "package-lock.json"
            if not all(
                self._safe_regular_file(path)
                for path in (installed_package, installed_lock)
            ):
                return "integrity_mismatch"
            if (
                self._file_sha256(package_json)
                != marker["package_json_sha256"]
                or self._file_sha256(installed_package)
                != marker["package_json_sha256"]
                or self._file_sha256(lockfile) != marker["lock_sha256"]
                or self._file_sha256(installed_lock) != marker["lock_sha256"]
            ):
                return "integrity_mismatch"
            installed_sources = installed_sidecar / "src"
            if (
                not installed_sources.is_dir()
                or installed_sources.is_symlink()
                or {path.name for path in installed_sources.iterdir()}
                != _SIDECAR_SOURCE_NAMES
            ):
                return "integrity_mismatch"
            if any(
                not self._safe_regular_file(installed_sources / name)
                or self._file_sha256(source_root / name)
                != self._file_sha256(installed_sources / name)
                for name in _SIDECAR_SOURCE_NAMES
            ):
                return "integrity_mismatch"
            ws_root = node_modules / "ws"
            if (
                not ws_root.is_dir()
                or ws_root.is_symlink()
                or not self._safe_regular_file(ws_root / "package.json")
            ):
                return "dependencies_missing"
            return "ready"
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return "deployment_invalid"

    def inspect(
        self,
        package_root: str | Path,
        dependency_root: str | Path | None = None,
        deployment: SidecarDeploymentDescriptor | None = None,
    ) -> QQBridgeReadiness:
        """Return a secret-free, read-only readiness snapshot."""
        with self._lock:
            root = self._trusted_package_root(package_root)
            resolved_dependency_root = (
                Path(dependency_root).resolve()
                if dependency_root is not None
                else None
            )
            entry = root / self.entry_relative_path
            package_json = root / "sidecar" / "package.json"
            lockfile = root / "sidecar" / "package-lock.json"
            package_ready = entry.is_file() and package_json.is_file() and lockfile.is_file()
            env_configured = self._env_path.is_file()
            node_ready = bool(self._node_resolver())
            dependency_code = (
                self._deployment_validation_code(
                    root,
                    resolved_dependency_root,
                    deployment,
                )
                if resolved_dependency_root is not None
                else "deployment_missing"
            )
            dependencies_ready = dependency_code == "ready"
            process_running = self._running(root, resolved_dependency_root)
            tracked = self._tracked_running(root, resolved_dependency_root)
            tracked_pid = None
            if tracked:
                candidate_pid = getattr(self._process, "pid", None)
                if isinstance(candidate_pid, int) and not isinstance(candidate_pid, bool):
                    tracked_pid = candidate_pid
            gateway = (
                self._gateway_status(tracked_pid, resolved_dependency_root)
                if process_running and tracked
                else self._gateway_status(None, resolved_dependency_root)
                if process_running
                else None
            )
            can_stop = tracked or bool(gateway)
            gateway_ready = bool(gateway and gateway["gateway_ready"])
            gateway_state = str(gateway["state"]) if gateway else (
                "gateway_unavailable" if process_running else "stopped"
            )
            if not package_ready:
                state = "package_invalid"
            elif not env_configured:
                state = "needs_configuration"
            elif not node_ready:
                state = "node_missing"
            elif not dependencies_ready:
                state = dependency_code
            elif process_running:
                state = "running" if gateway_ready else gateway_state
            else:
                state = "ready"
            return QQBridgeReadiness(
                ready=state == "ready",
                state=state,
                running=process_running,
                package_ready=package_ready,
                env_configured=env_configured,
                node_ready=node_ready,
                dependencies_ready=dependencies_ready,
                reason=state,
                process_running=process_running,
                can_stop=can_stop,
                gateway_ready=gateway_ready,
                gateway_state=gateway_state,
                gateway_last_error_code=(
                    gateway["last_error_code"] if gateway else None
                ),
                gateway_last_close_code=(
                    gateway["last_close_code"] if gateway else None
                ),
                gateway_reconnect_count=(
                    gateway["reconnect_count"] if gateway else 0
                ),
                gateway_last_ready_at=(
                    gateway["last_ready_at"] if gateway else None
                ),
                voice_last_result_code=(
                    gateway["voice_last_result_code"] if gateway else None
                ),
                voice_last_attempt_at=(
                    gateway["voice_last_attempt_at"] if gateway else None
                ),
            )

    def readiness(self, manifest: Any, package_root: str) -> SidecarReadiness:
        del manifest, package_root
        return SidecarReadiness.from_code(
            "dependencies_missing",
            ("node_dependencies",),
        )

    @staticmethod
    def _trusted_deployment(
        deployment: SidecarDeploymentDescriptor,
    ) -> tuple[Path, Path]:
        if (
            not isinstance(deployment, SidecarDeploymentDescriptor)
            or deployment.module_id != MODULE_ID
            or not isinstance(deployment.version, str)
            or not _SEMVER.fullmatch(deployment.version)
            or not isinstance(deployment.installed_tree_sha256, str)
            or not _SHA256.fullmatch(deployment.installed_tree_sha256)
        ):
            raise QQBridgeAdapterError("deployment_invalid")
        package_root = QQBridgeSidecarAdapter._trusted_package_root(
            deployment.package_root
        )
        dependency_root = Path(deployment.dependency_deployment_root).resolve()
        if (
            dependency_root == package_root
            or package_root in dependency_root.parents
            or dependency_root in package_root.parents
            or package_root.name != deployment.version
            or package_root.parent.name != MODULE_ID
            or dependency_root.name != deployment.version
            or dependency_root.parent.name != MODULE_ID
        ):
            raise QQBridgeAdapterError("deployment_invalid")
        return package_root, dependency_root

    def deployment_readiness(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> SidecarReadiness:
        del manifest
        package_root, dependency_root = self._trusted_deployment(deployment)
        snapshot = self.inspect(package_root, dependency_root, deployment)
        if snapshot.state == "ready" or (
            snapshot.process_running
            and snapshot.package_ready
            and snapshot.env_configured
            and snapshot.node_ready
            and snapshot.dependencies_ready
        ):
            return SidecarReadiness.from_code("ready")
        if snapshot.state == "needs_configuration":
            return SidecarReadiness.from_code("qq_env_missing", ("qq_env",))
        if snapshot.state == "node_missing":
            return SidecarReadiness.from_code("node_missing", ("node",))
        if snapshot.state in {"dependencies_missing", "deployment_missing"}:
            return SidecarReadiness.from_code(
                snapshot.state,
                ("node_dependencies",),
            )
        if snapshot.state in {"deployment_invalid", "integrity_mismatch"}:
            return SidecarReadiness.from_code(snapshot.state)
        return SidecarReadiness.from_code("entrypoint_missing", ("entrypoint",))

    def _child_environment(self) -> dict[str, str]:
        environment = dict(self._base_environment)
        environment["PROJECT_KEI_QQ_ENV_PATH"] = str(self._env_path)
        environment["PROJECT_KEI_QQ_DATA_ROOT"] = str(self._data_root)
        return environment

    def _start_from_root(
        self,
        package_root: Path,
        runtime_root: Path,
        dependency_root: Path | None,
        deployment: SidecarDeploymentDescriptor | None = None,
    ) -> None:
        readiness = self.inspect(package_root, dependency_root, deployment)
        if (
            readiness.process_running
            and readiness.package_ready
            and readiness.env_configured
            and readiness.node_ready
            and readiness.dependencies_ready
        ):
            self._package_root = package_root
            self._dependency_root = dependency_root
            return
        if readiness.state != "ready":
            raise QQBridgeAdapterError(readiness.state)
        node = self._node_resolver()
        if not node:
            raise QQBridgeAdapterError("node_missing")
        entry = runtime_root / "src" / "index.mjs"
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        self._process = self._process_factory(
            [str(node), str(entry)],
            cwd=str(self._env_path.parent),
            env=self._child_environment(),
            stdin=subprocess.PIPE,
            creationflags=creationflags,
        )
        self._package_root = package_root
        self._dependency_root = dependency_root

    def start(self, manifest: Any, package_root: str) -> None:
        del manifest, package_root
        raise QQBridgeAdapterError("deployment_required")

    def start_deployment(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        del manifest
        with self._lock:
            package_root, dependency_root = self._trusted_deployment(deployment)
            self._start_from_root(
                package_root,
                dependency_root,
                dependency_root,
                deployment,
            )

    def _stop(
        self,
        package_root: Path,
        dependency_root: Path | None,
    ) -> None:
        if not self._tracked_running(package_root, dependency_root):
            if self._running(package_root, dependency_root):
                gateway = self._gateway_status(None, dependency_root)
                if gateway is None:
                    raise QQBridgeAdapterError("shutdown_channel_unavailable")
                self._request_external_shutdown(gateway, package_root, dependency_root)
                return
            self._process = None
            self._package_root = None
            self._dependency_root = None
            return
        process = self._process
        try:
            if process.stdin is None:
                raise QQBridgeAdapterError("shutdown_channel_unavailable")
            process.stdin.write(b"shutdown\n")
            process.stdin.flush()
            process.wait(timeout=self._stop_timeout_seconds)
        except QQBridgeAdapterError:
            raise
        except Exception as exc:
            raise QQBridgeAdapterError("shutdown_failed") from exc
        finally:
            if process.poll() is not None:
                self._process = None
                self._package_root = None
                self._dependency_root = None

    def _request_external_shutdown(
        self,
        gateway: Mapping[str, Any],
        package_root: Path,
        dependency_root: Path | None,
    ) -> None:
        now_ms = self._now_ms()
        request = {
            "schema_version": 1,
            "generation": gateway["generation"],
            "requested_at": now_ms,
            "expires_at": now_ms + 5_000,
        }
        self._data_root.mkdir(parents=True, exist_ok=True)
        request_path = self._data_root / "shutdown_request.json"
        temp_path = self._data_root / f".shutdown_request.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(request, handle, ensure_ascii=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, request_path)
            deadline = time.monotonic() + self._stop_timeout_seconds
            while time.monotonic() < deadline:
                if not self._running(package_root, dependency_root):
                    return
                time.sleep(0.05)
            raise QQBridgeAdapterError("shutdown_failed")
        except QQBridgeAdapterError:
            raise
        except Exception as exc:
            raise QQBridgeAdapterError("shutdown_failed") from exc
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def stop(self, manifest: Any, package_root: str) -> None:
        del manifest, package_root
        raise QQBridgeAdapterError("deployment_required")

    def stop_deployment(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        del manifest
        with self._lock:
            package_root, dependency_root = self._trusted_deployment(deployment)
            self._stop(package_root, dependency_root)

    def is_healthy(self, manifest: Any, package_root: str) -> bool:
        del manifest, package_root
        return False

    def is_deployment_healthy(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> bool:
        del manifest
        with self._lock:
            package_root, dependency_root = self._trusted_deployment(deployment)
            snapshot = self.inspect(package_root, dependency_root, deployment)
            return snapshot.process_running


def register_qq_bridge_sidecar(
    manager: Any,
    *,
    process_probe: ProcessProbe,
    **adapter_options: Any,
) -> QQBridgeSidecarAdapter:
    """Register the reviewed adapter through PK-010's trusted composition."""

    if not callable(process_probe):
        raise ValueError("QQ bridge process probe is required")
    options = {
        "env_path": DEFAULT_ENV_PATH,
        "data_root": DEFAULT_DATA_ROOT,
        "process_probe": process_probe,
    }
    options.update(adapter_options)
    adapter = QQBridgeSidecarAdapter(**options)
    manager.register_sidecar_adapter(ADAPTER_NAME, adapter)
    return adapter


__all__ = [
    "ADAPTER_NAME",
    "MODULE_ID",
    "QQBridgeAdapterError",
    "QQBridgeReadiness",
    "QQBridgeSidecarAdapter",
    "register_qq_bridge_sidecar",
]
