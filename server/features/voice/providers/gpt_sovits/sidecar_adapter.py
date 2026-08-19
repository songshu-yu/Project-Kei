"""Trusted Core adapter for the installable GPT-SoVITS Provider sidecar.

The module manifest can only name this adapter.  It cannot provide a command,
path, URL, environment override, or script.  The adapter reads the fixed
Project Kei descriptor plus the ignored machine-local engine registration and
starts only the fixed ``runtime/python.exe api.py`` entrypoint.
"""

from __future__ import annotations

import http.client
import re
import subprocess
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, List, Protocol

from core.modules.exceptions import SidecarReadinessError
from core.modules.sidecar import SidecarDeploymentDescriptor, SidecarReadiness

from .acquisition import AcquisitionError, LocalEngineRegistry, validate_external_root
from .descriptor import DEFAULT_LOCAL_CONFIG_PATH, EngineDescriptor, load_descriptor


ADAPTER_NAME = "gpt_sovits_provider"
MODULE_ID = "gpt_sovits_engine_provider"
_PYTHON_ENTRY = "runtime/python.exe"
_API_ENTRY = "api.py"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SidecarAdapterError(RuntimeError):
    """Stable adapter failure that does not expose local paths or commands."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProcessHandle(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


ProcessFactory = Callable[[List[str], Path], ProcessHandle]
HealthProbe = Callable[[EngineDescriptor], bool]


def _default_process_factory(arguments: list[str], working_directory: Path) -> ProcessHandle:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        arguments,
        cwd=str(working_directory),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        creationflags=creation_flags,
    )


def _default_health_probe(descriptor: EngineDescriptor) -> bool:
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        descriptor.port,
        timeout=descriptor.health_timeout_seconds,
    )
    try:
        connection.request(descriptor.health_method, descriptor.health_path)
        response = connection.getresponse()
        response.read(1)
        return response.status < 500
    except (OSError, TimeoutError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def _safe_child(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise SidecarAdapterError("engine_entry_invalid", "固定引擎入口无效") from exc
    return candidate


class GPTSoVITSSidecarAdapter:
    """Start and stop only a registered external engine; never acquire it."""

    def __init__(
        self,
        *,
        registry_path: Path = DEFAULT_LOCAL_CONFIG_PATH,
        descriptor: EngineDescriptor | None = None,
        process_factory: ProcessFactory = _default_process_factory,
        health_probe: HealthProbe = _default_health_probe,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._registry = LocalEngineRegistry(Path(registry_path))
        self._descriptor = descriptor or load_descriptor()
        self._process_factory = process_factory
        self._health_probe = health_probe
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._process: ProcessHandle | None = None
        self._attached_existing = False
        self._lock = threading.RLock()

    @staticmethod
    def _declaration(manifest: Any) -> Any:
        sidecar = getattr(manifest, "sidecar", None)
        if (
            getattr(manifest, "id", None) != MODULE_ID
            or sidecar is None
            or getattr(sidecar, "adapter", None) != ADAPTER_NAME
        ):
            raise SidecarAdapterError("sidecar_manifest_invalid", "sidecar manifest 与固定 adapter 不匹配")
        return sidecar

    def _validate_package_descriptor(self, package_root: str) -> None:
        descriptor_path = Path(package_root) / "provider" / "engine.json"
        try:
            packaged = load_descriptor(descriptor_path)
        except Exception as exc:
            raise SidecarAdapterError("package_descriptor_invalid", "模块包的固定引擎描述无效") from exc
        if packaged != self._descriptor:
            raise SidecarAdapterError("package_descriptor_mismatch", "模块包与 Core 固定引擎描述不匹配")

    def _validate_deployment(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        self._declaration(manifest)
        if (
            not isinstance(deployment, SidecarDeploymentDescriptor)
            or deployment.module_id != MODULE_ID
            or deployment.version != getattr(manifest, "version", None)
            or not isinstance(deployment.package_root, Path)
            or not isinstance(deployment.installed_tree_sha256, str)
            or not _SHA256_RE.fullmatch(deployment.installed_tree_sha256)
        ):
            raise SidecarAdapterError("package_descriptor_invalid", "Core sidecar deployment 描述无效")
        self._validate_package_descriptor(str(deployment.package_root))

    def _registered_entries(self) -> tuple[Path, Path, Path]:
        try:
            data = self._registry.load()
            status = self._registry.status(self._descriptor)
        except AcquisitionError as exc:
            raise SidecarAdapterError(exc.code, "本机引擎登记不可用") from exc
        if data is None:
            raise SidecarAdapterError("engine_not_registered", "尚未登记本机 GPT-SoVITS 引擎")
        if not status.get("entrypoints_ready"):
            raise SidecarAdapterError("engine_not_ready", "已登记引擎缺少固定入口")
        root_value = data.get("install_root")
        if not isinstance(root_value, str) or not root_value:
            raise SidecarAdapterError("local_config_invalid", "本机引擎登记无效")
        try:
            root = validate_external_root(Path(root_value))
        except AcquisitionError as exc:
            raise SidecarAdapterError(exc.code, "本机引擎登记无效") from exc
        if _PYTHON_ENTRY not in self._descriptor.required_files or _API_ENTRY not in self._descriptor.required_files:
            raise SidecarAdapterError("descriptor_invalid", "固定引擎入口描述不完整")
        python_entry = _safe_child(root, _PYTHON_ENTRY)
        api_entry = _safe_child(root, _API_ENTRY)
        if not python_entry.is_file() or not api_entry.is_file():
            raise SidecarAdapterError("engine_not_ready", "已登记引擎缺少固定入口")
        return root, python_entry, api_entry

    def _deployment_readiness(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> SidecarReadiness:
        try:
            self._validate_deployment(manifest, deployment)
        except SidecarAdapterError:
            return SidecarReadiness.from_code("package_tampered")

        try:
            data = self._registry.load()
        except AcquisitionError:
            return SidecarReadiness.from_code("deployment_invalid")
        if data is None:
            return SidecarReadiness.from_code(
                "configuration_missing",
                ("engine_registration",),
            )
        if (
            data.get("engine_id") != self._descriptor.engine_id
            or not isinstance(data.get("install_root"), str)
            or not data.get("install_root")
            or data.get("api_style", self._descriptor.default_api_style)
            not in self._descriptor.supported_api_styles
        ):
            return SidecarReadiness.from_code("deployment_invalid")
        try:
            self._registered_entries()
        except SidecarAdapterError as exc:
            if exc.code in {"engine_not_registered"}:
                return SidecarReadiness.from_code(
                    "configuration_missing",
                    ("engine_registration",),
                )
            if exc.code in {"engine_not_ready"}:
                return SidecarReadiness.from_code("entrypoint_missing")
            return SidecarReadiness.from_code("deployment_invalid")
        return SidecarReadiness.from_code("ready")

    def _stop_owned_process(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception as exc:
                raise SidecarAdapterError("engine_stop_failed", "GPT-SoVITS sidecar 停止失败") from exc

    def start(self, manifest: Any, package_root: str) -> None:
        with self._lock:
            declaration = self._declaration(manifest)
            self._validate_package_descriptor(package_root)
            root, python_entry, api_entry = self._registered_entries()

            if self._process is not None and self._process.poll() is None:
                if self._health_probe(self._descriptor):
                    return
                raise SidecarAdapterError("engine_unhealthy", "已启动 GPT-SoVITS sidecar 未通过健康检查")
            self._process = None
            self._attached_existing = False

            if self._health_probe(self._descriptor):
                self._attached_existing = True
                return

            try:
                self._process = self._process_factory(
                    [
                        str(python_entry),
                        str(api_entry),
                        "-a",
                        "127.0.0.1",
                        "-p",
                        str(self._descriptor.port),
                    ],
                    root,
                )
            except Exception as exc:
                self._process = None
                raise SidecarAdapterError("engine_start_failed", "GPT-SoVITS sidecar 启动失败") from exc

            deadline = self._monotonic() + float(declaration.healthcheck_timeout_seconds)
            while True:
                if self._health_probe(self._descriptor):
                    return
                if self._process.poll() is not None:
                    self._stop_owned_process()
                    raise SidecarAdapterError("engine_start_failed", "GPT-SoVITS sidecar 未能启动")
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    self._stop_owned_process()
                    raise SidecarAdapterError("engine_health_timeout", "GPT-SoVITS sidecar 健康检查超时")
                self._sleeper(min(0.1, remaining))

    def stop(self, manifest: Any, package_root: str) -> None:
        with self._lock:
            self._declaration(manifest)
            self._validate_package_descriptor(package_root)
            self._stop_owned_process()
            # A healthy process found before start is external to this adapter.
            # Disabling/uninstalling the module must not terminate or delete it.
            self._attached_existing = False

    def is_healthy(self, manifest: Any, package_root: str) -> bool:
        with self._lock:
            try:
                self._declaration(manifest)
                self._validate_package_descriptor(package_root)
                self._registered_entries()
            except SidecarAdapterError:
                return False
            return bool(self._health_probe(self._descriptor))

    def deployment_readiness(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> SidecarReadiness:
        """Return only Core-normalized readiness for the verified package."""

        with self._lock:
            return self._deployment_readiness(manifest, deployment)

    def start_deployment(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        """Start using only the Core-verified package and fixed local registration."""

        with self._lock:
            readiness = self._deployment_readiness(manifest, deployment)
            if readiness.status != "ready":
                raise SidecarReadinessError(readiness)
            self.start(manifest, str(deployment.package_root))

    def stop_deployment(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> None:
        """Stop only a process owned by this adapter; ignore deployment paths."""

        with self._lock:
            self._declaration(manifest)
            if (
                not isinstance(deployment, SidecarDeploymentDescriptor)
                or deployment.module_id != MODULE_ID
                or deployment.version != getattr(manifest, "version", None)
            ):
                raise SidecarAdapterError("package_descriptor_invalid", "Core sidecar deployment 描述无效")
            self._stop_owned_process()
            self._attached_existing = False

    def is_deployment_healthy(
        self,
        manifest: Any,
        deployment: SidecarDeploymentDescriptor,
    ) -> bool:
        """Check this verified deployment and the fixed loopback health endpoint."""

        with self._lock:
            if self._deployment_readiness(manifest, deployment).status != "ready":
                return False
            return bool(self._health_probe(self._descriptor))


def register_gpt_sovits_sidecar(manager: Any, **adapter_options: Any) -> GPTSoVITSSidecarAdapter:
    """Register the trusted adapter through PK-010's frozen Core entrypoint."""

    adapter = GPTSoVITSSidecarAdapter(**adapter_options)
    manager.register_sidecar_adapter(ADAPTER_NAME, adapter)
    return adapter


__all__ = [
    "ADAPTER_NAME",
    "GPTSoVITSSidecarAdapter",
    "MODULE_ID",
    "SidecarAdapterError",
    "register_gpt_sovits_sidecar",
]
