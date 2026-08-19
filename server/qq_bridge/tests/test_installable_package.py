from __future__ import annotations

import asyncio
import json
import hashlib
import shutil
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

import httpx
from fastapi import FastAPI

from core.modules.manager import ModuleManager
from core.modules.manifest import validate_manifest
from core.modules.sidecar import SidecarDeploymentDescriptor
from qq_bridge.control_facade import QQControlAdapterFacade
from features.qq_control.router import create_qq_control_router
from qq_bridge.module_adapter import (
    QQBridgeAdapterError,
    QQBridgeSidecarAdapter,
    register_qq_bridge_sidecar,
)
from qq_bridge.package_builder import (
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_VERSION,
    SIDECAR_SOURCE_FILES,
    build_qq_bridge_package,
    file_sha256,
)


EXPECTED_PACKAGE_FILES = {
    "README.md",
    "config.schema.json",
    "dashboard/index.js",
    "manifest.json",
    "sidecar/package-lock.json",
    "sidecar/package.json",
    *(f"sidecar/src/{name}" for name in SIDECAR_SOURCE_FILES),
}
FORBIDDEN_PATH_PARTS = {
    ".env",
    "data",
    "logs",
    "node_modules",
    "tests",
    "vendor",
}


class FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flushes = 0

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        self.flushes += 1


class FakeProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.stdin = FakeStdin()
        self.returncode: int | None = None
        self.waits: list[float | None] = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waits.append(timeout)
        self.returncode = 0
        return 0


class FakePopen:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.processes: list[FakeProcess] = []
        self._lock = threading.Lock()

    def __call__(self, command, **kwargs):
        with self._lock:
            process = FakeProcess(4321 + len(self.processes))
            self.calls.append((list(command), dict(kwargs)))
            self.processes.append(process)
            return process


class FailOncePopen(FakePopen):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def __call__(self, command, **kwargs):
        self.attempts += 1
        if self.attempts == 1:
            raise OSError("fictional launch failure")
        return super().__call__(command, **kwargs)


class FakeScheduleService:
    def __init__(self) -> None:
        self.daily = {"enabled": False}
        self.life = {"enabled": False}

    def get_daily_schedule(self):
        return self.daily

    def update_daily_schedule(self, update):
        self.daily = {"enabled": bool(update)}
        return self.daily

    def get_life_support_schedule(self):
        return self.life

    def update_life_support_schedule(self, update):
        self.life = {"enabled": bool(update)}
        return self.life


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def create_deployment(
    package_root: Path,
    dependency_root: Path,
    *,
    installed_tree_sha256: str = "a" * 64,
) -> SidecarDeploymentDescriptor:
    sidecar = package_root / "sidecar"
    dependency_root.mkdir(parents=True)
    shutil.copy2(sidecar / "package.json", dependency_root / "package.json")
    shutil.copy2(sidecar / "package-lock.json", dependency_root / "package-lock.json")
    shutil.copytree(sidecar / "src", dependency_root / "src")
    ws = dependency_root / "node_modules" / "ws"
    ws.mkdir(parents=True)
    (ws / "package.json").write_text(
        '{"name":"ws","version":"8.21.0"}\n',
        encoding="utf-8",
    )
    marker = {
        "schema_version": 1,
        "module_id": "qq_bridge",
        "version": OFFICIAL_RELEASE_VERSION,
        "installed_tree_sha256": installed_tree_sha256,
        "package_json_sha256": sha256(dependency_root / "package.json"),
        "lock_sha256": sha256(dependency_root / "package-lock.json"),
        "node_version": "22.0.0",
        "npm_version": "10.0.0",
    }
    (dependency_root / ".project-kei-deployment.json").write_text(
        json.dumps(marker, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return SidecarDeploymentDescriptor(
        module_id="qq_bridge",
        version=OFFICIAL_RELEASE_VERSION,
        package_root=package_root,
        dependency_deployment_root=dependency_root,
        installed_tree_sha256=installed_tree_sha256,
    )


class QQBridgeInstallablePackageTests(unittest.TestCase):
    def test_needs_configuration_sidecar_can_serve_only_its_dashboard_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_zip = build_qq_bridge_package(root / OFFICIAL_ASSET_NAME)
            manager = ModuleManager(
                runtime_root=root / "runtime" / "modules",
                registry_path=root / "registry" / "module_registry.json",
                data_root=root / "module-data",
                dependency_deployment_root=root / "runtime" / "module-dependencies",
            )
            digest = manager.calculate_package_sha256(package_zip)
            installed = manager.install(
                package_zip,
                digest,
                expected_module_id="qq_bridge",
            )
            self.assertEqual(installed["install_status"], "needs_configuration")
            self.assertFalse(installed["enabled"])
            dashboard = manager.asset_path("qq_bridge", "dashboard/index.js")
            self.assertEqual(dashboard.name, "index.js")
            self.assertIn("QQ 功能启动", dashboard.read_text(encoding="utf-8"))

    def test_deterministic_package_has_exact_safe_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first = Path(first_temp) / OFFICIAL_ASSET_NAME
            second = Path(second_temp) / OFFICIAL_ASSET_NAME
            build_qq_bridge_package(first)
            build_qq_bridge_package(second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(file_sha256(first), file_sha256(second))
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, EXPECTED_PACKAGE_FILES)
                lowered = {part.lower() for name in names for part in Path(name).parts}
                self.assertTrue(FORBIDDEN_PATH_PARTS.isdisjoint(lowered))
                manifest_bytes = archive.read("manifest.json")
                manifest = validate_manifest(json.loads(manifest_bytes.decode("utf-8")))
                self.assertEqual(manifest.id, "qq_bridge")
                self.assertEqual(manifest.type, "sidecar")
                self.assertEqual(manifest.sidecar.adapter, "qq_bridge")
                self.assertEqual(manifest.api_namespaces, ("/api/v1/qq-control",))
                self.assertEqual(
                    [item.to_dict() for item in manifest.runtime_requirements],
                    [{
                        "id": "node",
                        "supported_major_versions": [20, 22, 24, 26],
                        "architecture": "x64",
                    }],
                )
                self.assertFalse(manifest.requires_restart)
                package = json.loads(archive.read("sidecar/package.json"))
                lock = json.loads(archive.read("sidecar/package-lock.json"))
                self.assertEqual(package["version"], OFFICIAL_RELEASE_VERSION)
                self.assertEqual(lock["version"], OFFICIAL_RELEASE_VERSION)
                self.assertEqual(
                    lock["packages"][""]["version"],
                    OFFICIAL_RELEASE_VERSION,
                )
                self.assertEqual(
                    package["engines"]["node"],
                    "20.x || 22.x || 24.x || 26.x",
                )
                joined = b"\n".join(archive.read(name) for name in sorted(names))
                for marker in (
                    b"QQBOT_SECRET=",
                    b"FAKE_SECRET_TOKEN",
                    b"FAKE_ACCESS_TOKEN",
                    b"openid_fake_user_1234567890",
                ):
                    self.assertNotIn(marker, joined)

    def test_builder_rejects_output_inside_source_and_existing_destination(self) -> None:
        bridge_root = Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError):
            build_qq_bridge_package(bridge_root / "unsafe-package.zip")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "existing.zip"
            output.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                build_qq_bridge_package(output)
            self.assertEqual(output.read_bytes(), b"preserve")
            with self.assertRaises(ValueError):
                build_qq_bridge_package(
                    Path(temp) / "wrong-version.zip",
                    version="0.2.0",
                )

    def test_readiness_is_secret_free_and_never_creates_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(
                package_root,
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION,
            )
            env_path = root / "persistent" / ".env"
            data_root = root / "persistent" / "data"
            popen = FakePopen()
            adapter = QQBridgeSidecarAdapter(
                env_path=env_path,
                data_root=data_root,
                process_factory=popen,
                node_resolver=lambda: None,
                base_environment={"PATH": "FAKE_PATH", "QQBOT_SECRET": "FAKE_SECRET"},
            )

            missing_config = adapter.deployment_readiness(
                None,
                deployment,
            ).to_dict()
            self.assertEqual(missing_config["status"], "needs_configuration")
            self.assertEqual(missing_config["code"], "qq_env_missing")
            self.assertFalse(env_path.exists())
            self.assertFalse(data_root.exists())
            self.assertNotIn("FAKE_SECRET", json.dumps(missing_config))

            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FAKE_SECRET\n", encoding="utf-8")
            missing_node = adapter.deployment_readiness(None, deployment).to_dict()
            self.assertEqual(missing_node["code"], "node_missing")
            self.assertNotIn("FAKE_SECRET", json.dumps(missing_node))
            self.assertEqual(popen.calls, [])

    def test_concurrent_start_is_single_and_stop_uses_fixed_shutdown_channel(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            dependency_root = (
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(package_root, dependency_root)
            env_path = root / "persistent" / ".env"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FAKE_SECRET\n", encoding="utf-8")
            data_root = root / "persistent" / "data"
            popen = FakePopen()
            adapter = QQBridgeSidecarAdapter(
                env_path=env_path,
                data_root=data_root,
                process_factory=popen,
                node_resolver=lambda: "C:/fake/node.exe",
                base_environment={
                    "PATH": "C:/fake",
                    "SYSTEMROOT": "C:/Windows",
                    "QQBOT_SECRET": "MUST_NOT_INHERIT",
                    "AUTHORIZATION": "MUST_NOT_INHERIT",
                },
            )

            threads = [
                threading.Thread(
                    target=adapter.start_deployment,
                    args=(None, deployment),
                )
                for _ in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(len(popen.calls), 1)
            command, kwargs = popen.calls[0]
            self.assertEqual(command[0], "C:/fake/node.exe")
            self.assertEqual(Path(command[1]), dependency_root / "src" / "index.mjs")
            self.assertEqual(Path(kwargs["cwd"]), env_path.parent)
            self.assertNotIn("QQBOT_SECRET", kwargs["env"])
            self.assertNotIn("AUTHORIZATION", kwargs["env"])
            self.assertEqual(Path(kwargs["env"]["PROJECT_KEI_QQ_ENV_PATH"]), env_path)
            self.assertEqual(Path(kwargs["env"]["PROJECT_KEI_QQ_DATA_ROOT"]), data_root)

            process = popen.processes[0]
            adapter.stop_deployment(None, deployment)
            self.assertEqual(process.stdin.writes, [b"shutdown\n"])
            self.assertEqual(process.stdin.flushes, 1)
            self.assertEqual(process.returncode, 0)
            self.assertFalse(adapter.is_deployment_healthy(None, deployment))
            adapter.stop_deployment(None, deployment)
            adapter.start_deployment(None, deployment)
            self.assertEqual(len(popen.calls), 2)
            adapter.stop_deployment(None, deployment)

    def test_external_duplicate_is_not_started_or_terminated_without_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            dependency_root = (
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(package_root, dependency_root)
            env_path = root / ".env"
            env_path.write_text("QQBOT_SECRET=FAKE_SECRET\n", encoding="utf-8")
            popen = FakePopen()
            adapter = QQBridgeSidecarAdapter(
                env_path=env_path,
                data_root=root / "data",
                process_factory=popen,
                process_probe=lambda _: True,
                node_resolver=lambda: "C:/fake/node.exe",
            )
            adapter.start_deployment(None, deployment)
            self.assertEqual(popen.calls, [])
            with self.assertRaisesRegex(
                QQBridgeAdapterError,
                "shutdown_channel_unavailable",
            ):
                adapter.stop_deployment(None, deployment)

    def test_external_process_can_stop_only_through_matching_generation_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            dependency_root = (
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(package_root, dependency_root)
            env_path = root / "persistent" / ".env"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FICTIONAL_SECRET\n", encoding="utf-8")
            data_root = root / "persistent" / "data"
            data_root.mkdir(parents=True)
            now_ms = 1_800_000_000_000
            process_id = 7777
            generation = "e" * 32
            (data_root / "gateway_status.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "generation": generation,
                    "pid": process_id,
                    "shutdown_control_ready": True,
                    "state": "identified_or_ready",
                    "gateway_ready": True,
                    "heartbeat_healthy": True,
                    "last_error_code": None,
                    "last_close_code": None,
                    "reconnect_count": 0,
                    "last_ready_at": now_ms,
                    "voice_last_result_code": None,
                    "voice_last_attempt_at": None,
                    "updated_at": now_ms,
                }),
                encoding="utf-8",
            )
            running = True

            def process_probe(_: Path) -> bool:
                nonlocal running
                request_path = data_root / "shutdown_request.json"
                if request_path.is_file():
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    self.assertEqual(set(request), {
                        "schema_version", "generation", "requested_at", "expires_at",
                    })
                    self.assertEqual(request["generation"], generation)
                    running = False
                return running

            adapter = QQBridgeSidecarAdapter(
                env_path=env_path,
                data_root=data_root,
                process_probe=process_probe,
                process_identity_probe=lambda candidate_root, candidate_pid: (
                    candidate_root == dependency_root.resolve() and candidate_pid == process_id
                ),
                node_resolver=lambda: "C:/fake/node.exe",
                now_ms=lambda: now_ms,
                stop_timeout_seconds=0.5,
            )
            before = adapter.inspect(package_root, dependency_root, deployment)
            self.assertTrue(before.process_running)
            self.assertTrue(before.can_stop)
            adapter.stop_deployment(None, deployment)
            self.assertFalse(running)
            self.assertFalse(adapter.inspect(package_root, dependency_root, deployment).process_running)

    def test_external_shutdown_fails_closed_for_wrong_process_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            dependency_root = (
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(package_root, dependency_root)
            data_root = root / "data"
            data_root.mkdir()
            now_ms = 1_800_000_000_000
            (data_root / "gateway_status.json").write_text(json.dumps({
                "schema_version": 1,
                "generation": "f" * 32,
                "pid": 8888,
                "shutdown_control_ready": True,
                "state": "identified_or_ready",
                "gateway_ready": True,
                "heartbeat_healthy": True,
                "last_error_code": None,
                "last_close_code": None,
                "reconnect_count": 0,
                "last_ready_at": now_ms,
                "voice_last_result_code": None,
                "voice_last_attempt_at": None,
                "updated_at": now_ms,
            }), encoding="utf-8")
            adapter = QQBridgeSidecarAdapter(
                env_path=root / ".env",
                data_root=data_root,
                process_probe=lambda _: True,
                process_identity_probe=lambda _root, _pid: False,
                node_resolver=lambda: "C:/fake/node.exe",
                now_ms=lambda: now_ms,
            )
            snapshot = adapter.inspect(package_root, dependency_root, deployment)
            self.assertTrue(snapshot.process_running)
            self.assertFalse(snapshot.can_stop)
            with self.assertRaisesRegex(QQBridgeAdapterError, "shutdown_channel_unavailable"):
                adapter.stop_deployment(None, deployment)
            self.assertFalse((data_root / "shutdown_request.json").exists())

    def test_gateway_snapshot_distinguishes_process_from_connected_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            dependency_root = (
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(package_root, dependency_root)
            env_path = root / "persistent" / ".env"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FICTIONAL_SECRET\n", encoding="utf-8")
            data_root = root / "persistent" / "data"
            popen = FakePopen()
            now_ms = 1_800_000_000_000
            adapter = QQBridgeSidecarAdapter(
                env_path=env_path,
                data_root=data_root,
                process_factory=popen,
                node_resolver=lambda: "C:/fake/node.exe",
                now_ms=lambda: now_ms,
            )
            adapter.start_deployment(None, deployment)
            process_only = adapter.inspect(package_root, dependency_root, deployment)
            self.assertTrue(process_only.process_running)
            self.assertFalse(process_only.gateway_ready)
            self.assertEqual(process_only.state, "gateway_unavailable")

            data_root.mkdir(parents=True)
            state_path = data_root / "gateway_status.json"
            snapshot = {
                "schema_version": 1,
                "generation": "a" * 32,
                "pid": popen.processes[0].pid,
                "shutdown_control_ready": True,
                "state": "identified_or_ready",
                "gateway_ready": True,
                "heartbeat_healthy": True,
                "last_error_code": None,
                "last_close_code": None,
                "reconnect_count": 2,
                "last_ready_at": now_ms - 1_000,
                "voice_last_result_code": None,
                "voice_last_attempt_at": None,
                "updated_at": now_ms,
            }
            state_path.write_text(json.dumps(snapshot), encoding="utf-8")
            connected = adapter.inspect(package_root, dependency_root, deployment)
            self.assertEqual(connected.state, "running")
            self.assertTrue(connected.process_running)
            self.assertTrue(connected.gateway_ready)
            self.assertEqual(connected.gateway_reconnect_count, 2)
            self.assertIsNone(connected.voice_last_result_code)

            snapshot.update({
                "state": "reconnect_wait",
                "gateway_ready": False,
                "heartbeat_healthy": False,
                "last_error_code": "heartbeat_timeout",
                "last_close_code": 4000,
            })
            state_path.write_text(json.dumps(snapshot), encoding="utf-8")
            reconnecting = adapter.inspect(package_root, dependency_root, deployment)
            self.assertEqual(reconnecting.state, "reconnect_wait")
            self.assertTrue(reconnecting.process_running)
            self.assertFalse(reconnecting.gateway_ready)

            old_bytes = b"{broken-status"
            state_path.write_bytes(old_bytes)
            corrupt = adapter.inspect(package_root, dependency_root, deployment)
            self.assertEqual(corrupt.state, "gateway_unavailable")
            self.assertEqual(state_path.read_bytes(), old_bytes)

            snapshot["pid"] = popen.processes[0].pid + 1
            state_path.write_text(json.dumps(snapshot), encoding="utf-8")
            self.assertEqual(
                adapter.inspect(package_root, dependency_root, deployment).state,
                "gateway_unavailable",
            )
            snapshot["pid"] = popen.processes[0].pid
            snapshot["updated_at"] = now_ms - 181_000
            snapshot["authorization"] = "FICTIONAL_AUTHORIZATION"
            state_path.write_text(json.dumps(snapshot), encoding="utf-8")
            stale = adapter.inspect(package_root, dependency_root, deployment)
            self.assertEqual(stale.state, "gateway_unavailable")
            self.assertNotIn("FICTIONAL_AUTHORIZATION", json.dumps(stale.to_dict()))

    def test_deployment_marker_and_tree_tampering_fail_closed(self) -> None:
        cases = {
            "marker_missing": "deployment_missing",
            "marker_unknown_field": "deployment_invalid",
            "marker_duplicate_field": "deployment_invalid",
            "marker_wrong_schema": "deployment_invalid",
            "marker_old_version": "deployment_invalid",
            "marker_digest_mismatch": "deployment_invalid",
            "marker_uppercase_digest": "deployment_invalid",
            "marker_empty_node_version": "deployment_invalid",
            "marker_path_node_version": "deployment_invalid",
            "package_tampered": "integrity_mismatch",
            "lock_tampered": "integrity_mismatch",
            "source_tampered": "integrity_mismatch",
            "unknown_top_level": "deployment_invalid",
            "node_modules_missing": "dependencies_missing",
        }
        for case, expected_code in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                package_root = build_qq_bridge_package(
                    root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
                )
                dependency_root = (
                    root
                    / "runtime"
                    / "module-dependencies"
                    / "qq_bridge"
                    / OFFICIAL_RELEASE_VERSION
                )
                deployment = create_deployment(package_root, dependency_root)
                marker_path = dependency_root / ".project-kei-deployment.json"
                if case == "marker_missing":
                    marker_path.unlink()
                elif case == "marker_unknown_field":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["path"] = "C:/forbidden"
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "marker_duplicate_field":
                    marker_text = marker_path.read_text(encoding="utf-8").strip()
                    marker_path.write_text(
                        marker_text[:-1] + ',"module_id":"qq_bridge"}',
                        encoding="utf-8",
                    )
                elif case == "marker_old_version":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["version"] = "0.0.9"
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "marker_wrong_schema":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["schema_version"] = 2
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "marker_digest_mismatch":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["installed_tree_sha256"] = "b" * 64
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "marker_uppercase_digest":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["lock_sha256"] = marker["lock_sha256"].upper()
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "marker_empty_node_version":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["node_version"] = ""
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "marker_path_node_version":
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["node_version"] = "C:/forbidden/node.exe"
                    marker_path.write_text(json.dumps(marker), encoding="utf-8")
                elif case == "package_tampered":
                    (dependency_root / "package.json").write_text(
                        '{"name":"tampered"}\n',
                        encoding="utf-8",
                    )
                elif case == "lock_tampered":
                    (dependency_root / "package-lock.json").write_text(
                        '{"lockfileVersion":3}\n',
                        encoding="utf-8",
                    )
                elif case == "source_tampered":
                    (dependency_root / "src" / "index.mjs").write_text(
                        'throw new Error("tampered");\n',
                        encoding="utf-8",
                    )
                elif case == "unknown_top_level":
                    (dependency_root / "unexpected.txt").write_text(
                        "unexpected\n",
                        encoding="utf-8",
                    )
                elif case == "node_modules_missing":
                    shutil.rmtree(dependency_root / "node_modules")

                env_path = root / "persistent" / ".env"
                env_path.parent.mkdir(parents=True)
                env_path.write_text("QQBOT_SECRET=FAKE_SECRET\n", encoding="utf-8")
                popen = FakePopen()
                adapter = QQBridgeSidecarAdapter(
                    env_path=env_path,
                    data_root=root / "persistent" / "data",
                    process_factory=popen,
                    process_probe=lambda _: True,
                    node_resolver=lambda: "C:/fake/node.exe",
                )
                readiness = adapter.deployment_readiness(None, deployment)
                self.assertEqual(readiness.code, expected_code)
                self.assertEqual(
                    readiness.status,
                    (
                        "needs_configuration"
                        if expected_code in {"deployment_missing", "dependencies_missing"}
                        else "unavailable"
                    ),
                )
                with self.assertRaisesRegex(
                    QQBridgeAdapterError,
                    expected_code,
                ):
                    adapter.start_deployment(None, deployment)
                self.assertEqual(popen.calls, [])

    def test_invalid_deployment_never_falls_back_to_package_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = build_qq_bridge_package(
                root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            local_ws = package_root / "sidecar" / "node_modules" / "ws"
            local_ws.mkdir(parents=True)
            (local_ws / "package.json").write_text(
                '{"name":"ws","version":"8.21.0"}\n',
                encoding="utf-8",
            )
            dependency_root = (
                root / "runtime" / "module-dependencies" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            )
            deployment = create_deployment(package_root, dependency_root)
            (dependency_root / ".project-kei-deployment.json").unlink()
            env_path = root / "persistent" / ".env"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FAKE_SECRET\n", encoding="utf-8")
            popen = FakePopen()
            adapter = QQBridgeSidecarAdapter(
                env_path=env_path,
                data_root=root / "persistent" / "data",
                process_factory=popen,
                node_resolver=lambda: "C:/fake/node.exe",
            )
            self.assertEqual(
                adapter.deployment_readiness(None, deployment).code,
                "deployment_missing",
            )
            with self.assertRaises(QQBridgeAdapterError):
                adapter.start_deployment(None, deployment)
            with self.assertRaisesRegex(QQBridgeAdapterError, "deployment_required"):
                adapter.start(None, str(package_root))
            self.assertFalse(adapter.is_healthy(None, str(package_root)))
            invalid_descriptor = SidecarDeploymentDescriptor(
                module_id="qq_bridge",
                version=OFFICIAL_RELEASE_VERSION,
                package_root=package_root,
                dependency_deployment_root=root / "runtime" / "wrong" / OFFICIAL_RELEASE_VERSION,
                installed_tree_sha256="a" * 64,
            )
            with self.assertRaisesRegex(QQBridgeAdapterError, "deployment_invalid"):
                adapter.start_deployment(None, invalid_descriptor)
            self.assertEqual(popen.calls, [])

    def test_qq_control_facade_uses_the_registered_adapter_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_zip = build_qq_bridge_package(root / OFFICIAL_ASSET_NAME)
            env_path = root / "persistent" / ".env"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FAKE_SECRET\n", encoding="utf-8")
            popen = FakePopen()
            manager = ModuleManager(
                runtime_root=root / "runtime" / "modules",
                registry_path=root / "registry" / "module_registry.json",
                data_root=root / "module-data",
                dependency_deployment_root=root / "runtime" / "module-dependencies",
            )
            adapter = register_qq_bridge_sidecar(
                manager,
                process_probe=lambda _: False,
                env_path=env_path,
                data_root=root / "persistent" / "data",
                process_factory=popen,
                node_resolver=lambda: "C:/fake/node.exe",
            )
            digest = manager.calculate_package_sha256(package_zip)
            manager.install(package_zip, digest, expected_module_id="qq_bridge")
            deployment = manager.resolve_sidecar_deployment("qq_bridge")
            create_deployment(
                deployment.package_root,
                deployment.dependency_deployment_root,
                installed_tree_sha256=deployment.installed_tree_sha256,
            )
            schedules = FakeScheduleService()
            facade = QQControlAdapterFacade(manager, adapter, schedules)

            self.assertEqual(facade.status()["state"], "ready")
            self.assertEqual(popen.calls, [])

            async def exercise_router():
                app = FastAPI()
                app.include_router(
                    create_qq_control_router(
                        facade,
                        read_guard=lambda _: True,
                        write_guard=lambda _: True,
                    )
                )
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://test",
                ) as client:
                    versioned = await client.get("/api/v1/qq-control/status")
                    legacy = await client.get("/dashboard/qq-bridge/status")
                    started = await client.post("/api/v1/qq-control/start")
                    duplicate = await client.post("/dashboard/qq-bridge/start")
                return versioned, legacy, started, duplicate

            versioned, legacy, started, duplicate = asyncio.run(exercise_router())
            self.assertEqual(versioned.status_code, 200)
            self.assertEqual(legacy.status_code, 200)
            self.assertEqual(versioned.json()["state"], "ready")
            self.assertEqual(legacy.json()["state"], "ready")
            self.assertTrue(started.json()["started"])
            self.assertFalse(duplicate.json()["started"])
            self.assertEqual(len(popen.calls), 1)
            post_start = facade.status()
            self.assertEqual(post_start["state"], "gateway_unavailable")
            self.assertTrue(post_start["process_running"])
            self.assertFalse(post_start["gateway_ready"])
            status_root = root / "persistent" / "data"
            status_root.mkdir(parents=True)
            now_ms = int(time.time() * 1000)
            (status_root / "gateway_status.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "generation": "b" * 32,
                    "pid": popen.processes[0].pid,
                    "shutdown_control_ready": True,
                    "state": "identified_or_ready",
                    "gateway_ready": True,
                    "heartbeat_healthy": True,
                    "last_error_code": None,
                    "last_close_code": None,
                    "reconnect_count": 0,
                    "last_ready_at": now_ms,
                    "voice_last_result_code": "voice_upload_failed",
                    "voice_last_attempt_at": now_ms,
                    "updated_at": now_ms,
                }),
                encoding="utf-8",
            )
            connected = facade.status()
            self.assertEqual(connected["state"], "running")
            self.assertTrue(connected["process_running"])
            self.assertTrue(connected["gateway_ready"])
            self.assertIsNone(connected["gateway_last_error_code"])
            self.assertIsNone(connected["gateway_message"])
            self.assertEqual(connected["voice_last_result_code"], "voice_upload_failed")
            self.assertEqual(
                connected["voice_message"],
                "QQ rejected or could not receive the voice upload.",
            )
            self.assertEqual(connected["voice_last_attempt_at"], now_ms)
            (status_root / "gateway_status.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "generation": "b" * 32,
                    "pid": popen.processes[0].pid,
                    "shutdown_control_ready": True,
                    "state": "reconnect_wait",
                    "gateway_ready": False,
                    "heartbeat_healthy": False,
                    "last_error_code": "token_request_failed",
                    "last_close_code": None,
                    "reconnect_count": 1,
                    "last_ready_at": None,
                    "voice_last_result_code": "voice_upload_failed",
                    "voice_last_attempt_at": now_ms,
                    "updated_at": now_ms,
                }),
                encoding="utf-8",
            )
            reconnecting = facade.status()
            self.assertTrue(reconnecting["process_running"])
            self.assertFalse(reconnecting["gateway_ready"])
            self.assertEqual(reconnecting["gateway_last_error_code"], "token_request_failed")
            self.assertEqual(
                reconnecting["gateway_message"],
                "QQ access token request failed; retry is bounded.",
            )
            self.assertNotIn("http", reconnecting["gateway_message"].lower())
            self.assertNotIn("token=", reconnecting["gateway_message"].lower())
            self.assertNotIn("pid", connected)
            self.assertNotIn("generation", connected)
            self.assertFalse(facade.start()["started"])
            self.assertEqual(len(popen.calls), 1)
            self.assertIs(facade.get_daily_schedule(), schedules.daily)
            self.assertIs(facade.get_life_support_schedule(), schedules.life)

            async def stop_through_router():
                app = FastAPI()
                app.include_router(create_qq_control_router(
                    facade,
                    read_guard=lambda _: True,
                    write_guard=lambda _: True,
                ))
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    arbitrary = await client.post(
                        "/api/v1/qq-control/stop",
                        json={"pid": 4321},
                    )
                    stopped = await client.post("/api/v1/qq-control/stop")
                    duplicate = await client.post("/dashboard/qq-bridge/stop")
                return arbitrary, stopped, duplicate

            arbitrary, stopped, duplicate = asyncio.run(stop_through_router())
            self.assertEqual(arbitrary.status_code, 422)
            self.assertTrue(stopped.json()["stopped"])
            self.assertEqual(duplicate.status_code, 409)

    def test_module_lifecycle_preserves_external_configuration_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_zip = build_qq_bridge_package(root / OFFICIAL_ASSET_NAME)
            persistent = root / "persistent"
            env_path = persistent / ".env"
            data_root = persistent / "data"
            data_root.mkdir(parents=True)
            env_bytes = b"QQBOT_SECRET=FAKE_SECRET\n"
            state_bytes = b'{"schema_version":1,"entries":{}}\n'
            env_path.write_bytes(env_bytes)
            state_path = data_root / "fake-runtime.json"
            state_path.write_bytes(state_bytes)
            popen = FakePopen()
            manager = ModuleManager(
                runtime_root=root / "runtime" / "modules",
                registry_path=root / "registry" / "module_registry.json",
                data_root=root / "module-data",
                dependency_deployment_root=root / "runtime" / "module-dependencies",
            )
            register_qq_bridge_sidecar(
                manager,
                process_probe=lambda _: False,
                env_path=env_path,
                data_root=data_root,
                process_factory=popen,
                node_resolver=lambda: "C:/fake/node.exe",
            )
            digest = manager.calculate_package_sha256(package_zip)
            installed = manager.install(package_zip, digest, expected_module_id="qq_bridge")
            self.assertEqual(installed["install_status"], "needs_configuration")
            self.assertEqual(
                installed["sidecar_readiness"]["code"],
                "deployment_missing",
            )

            runtime_package = root / "runtime" / "modules" / "qq_bridge" / OFFICIAL_RELEASE_VERSION
            deployment = manager.resolve_sidecar_deployment("qq_bridge")
            installed_snapshot = tree_snapshot(runtime_package)
            create_deployment(
                runtime_package,
                deployment.dependency_deployment_root,
                installed_tree_sha256=deployment.installed_tree_sha256,
            )
            self.assertEqual(
                tree_snapshot(runtime_package),
                installed_snapshot,
            )
            enabled = manager.enable("qq_bridge")
            self.assertTrue(enabled["enabled"])
            self.assertEqual(len(popen.calls), 0)
            self.assertEqual(manager.start_enabled_sidecars(), [])
            self.assertEqual(len(popen.calls), 0)
            facade = QQControlAdapterFacade(
                manager,
                manager.resolve_sidecar_adapter("qq_bridge"),
                FakeScheduleService(),
            )
            self.assertEqual(facade.status()["state"], "ready")
            self.assertTrue(facade.start()["started"])
            self.assertEqual(len(popen.calls), 1)
            command, kwargs = popen.calls[0]
            self.assertEqual(
                Path(command[1]),
                deployment.dependency_deployment_root / "src" / "index.mjs",
            )
            self.assertEqual(Path(kwargs["cwd"]), env_path.parent)
            manager.disable("qq_bridge")
            result = manager.uninstall("qq_bridge")
            self.assertTrue(result["data_preserved"])
            self.assertEqual(env_path.read_bytes(), env_bytes)
            self.assertEqual(state_path.read_bytes(), state_bytes)
            self.assertFalse((root / "runtime" / "modules" / "qq_bridge").exists())
            shutil.rmtree(deployment.dependency_deployment_root)

            reinstalled = manager.install(package_zip, digest, expected_module_id="qq_bridge")
            self.assertEqual(reinstalled["install_status"], "needs_configuration")
            self.assertEqual(
                reinstalled["sidecar_readiness"]["code"],
                "deployment_missing",
            )
            self.assertEqual(env_path.read_bytes(), env_bytes)
            self.assertEqual(state_path.read_bytes(), state_bytes)

    def test_explicit_start_failure_is_retryable_and_shutdown_waits_for_next_click(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_zip = build_qq_bridge_package(root / OFFICIAL_ASSET_NAME)
            env_path = root / "persistent" / ".env"
            env_path.parent.mkdir(parents=True)
            env_path.write_text("QQBOT_SECRET=FICTIONAL\n", encoding="utf-8")
            popen = FailOncePopen()
            manager = ModuleManager(
                runtime_root=root / "runtime" / "modules",
                registry_path=root / "registry" / "module_registry.json",
                data_root=root / "module-data",
                dependency_deployment_root=root / "runtime" / "module-dependencies",
            )
            adapter = register_qq_bridge_sidecar(
                manager,
                process_probe=lambda _: False,
                env_path=env_path,
                data_root=root / "persistent" / "data",
                process_factory=popen,
                node_resolver=lambda: "C:/fake/node.exe",
            )
            digest = manager.calculate_package_sha256(package_zip)
            manager.install(package_zip, digest, expected_module_id="qq_bridge")
            deployment = manager.resolve_sidecar_deployment("qq_bridge")
            create_deployment(
                deployment.package_root,
                deployment.dependency_deployment_root,
                installed_tree_sha256=deployment.installed_tree_sha256,
            )
            facade = QQControlAdapterFacade(manager, adapter, FakeScheduleService())

            self.assertEqual(facade.status()["state"], "ready")
            self.assertEqual(popen.attempts, 0)
            failed = facade.start()
            self.assertEqual(failed["state"], "start_failed")
            self.assertFalse(failed["started"])
            self.assertEqual(popen.attempts, 1)
            self.assertTrue(manager.get("qq_bridge")["enabled"])

            retry_results: list[dict] = []
            retry_threads = [
                threading.Thread(target=lambda: retry_results.append(facade.start()))
                for _ in range(8)
            ]
            for thread in retry_threads:
                thread.start()
            for thread in retry_threads:
                thread.join()
            self.assertEqual(sum(result["started"] for result in retry_results), 1)
            self.assertEqual(popen.attempts, 2)
            self.assertEqual(len(popen.calls), 1)
            self.assertFalse(facade.start()["started"])
            self.assertEqual(popen.attempts, 2)

            manager.disable("qq_bridge")
            self.assertEqual(facade.status()["state"], "ready")
            self.assertEqual(popen.attempts, 2)
            restarted = facade.start()
            self.assertTrue(restarted["started"])
            self.assertEqual(popen.attempts, 3)
            self.assertEqual(len(popen.calls), 2)
            self.assertTrue(facade.status()["can_stop"])
            stopped = facade.stop()
            self.assertTrue(stopped["stopped"])
            self.assertFalse(stopped["running"])
            self.assertFalse(facade.stop()["stopped"])

    def test_dashboard_uses_only_fixed_qq_control_facade(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "package_source"
            / "dashboard"
            / "index.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"/api/v1/qq-control/status"', source)
        self.assertIn('"/api/v1/qq-control/start"', source)
        self.assertIn('"/api/v1/qq-control/stop"', source)
        self.assertEqual(source.count('"/api/v1/qq-control/start"'), 1)
        self.assertIn('startButton.addEventListener("click"', source)
        self.assertIn('startButton.disabled = true', source)
        self.assertIn('stopButton.addEventListener("click"', source)
        self.assertIn("status?.can_stop !== true", source)
        self.assertIn("globalThis.confirm", source)
        self.assertIn('"/api/v1/qq-control/schedules/daily-briefing"', source)
        self.assertIn('"/api/v1/qq-control/schedules/life-support"', source)
        for label in ("QQ 功能启动", "每日情报定时推送", "生命维持系统"):
            self.assertIn(label, source)
        self.assertIn("module-owned-panels", source)
        for panel_id in ("module-qq_bridge", "module-qq-daily-push", "module-qq-life-support"):
            self.assertIn(panel_id, source)
        for avatar in ("qq-launch.png", "briefing-schedule.png", "life-support.png"):
            self.assertIn(avatar, source)
        self.assertIn("https://q.qq.com/", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("/api/v1/modules/", source)
        self.assertNotIn('method: "DELETE"', source)
        self.assertNotIn("npm ", source)

        panels = (
            Path(__file__).resolve().parents[2]
            / "static"
            / "dashboard"
            / "panels.js"
        ).read_text(encoding="utf-8")
        self.assertIn("function enhanceQQLaunchVisual", panels)
        self.assertIn("button.setAttribute('aria-label', '启动 QQ Bridge')", panels)
        self.assertIn("if (!button.disabled) start.click()", panels)
        self.assertIn("button.disabled = start.disabled", panels)

        start_script = (
            Path(__file__).resolve().parents[3] / "scripts" / "start.ps1"
        ).read_text(encoding="utf-8")
        self.assertNotIn('if ($Only -eq "qq")', start_script)
        self.assertNotIn('& $Node.FilePath "src\\index.mjs"', start_script)
        self.assertNotIn('Arguments @("--only", "qq"', start_script)
        self.assertIn("waits for an explicit dashboard avatar", start_script)

    def test_needs_configuration_keeps_fixed_local_control_facade_available(self) -> None:
        from module_composition import qq_control_route_available

        self.assertTrue(qq_control_route_available({
            "type": "sidecar",
            "install_status": "needs_configuration",
            "enabled": False,
        }))
        self.assertTrue(qq_control_route_available({
            "type": "sidecar",
            "install_status": "enabled",
            "enabled": True,
        }))
        self.assertFalse(qq_control_route_available({
            "type": "in_process",
            "install_status": "needs_configuration",
            "enabled": False,
        }))
        self.assertFalse(qq_control_route_available(None))

    def test_life_support_reminder_uses_dynamic_text_provider_and_degrades(self) -> None:
        class Result:
            text = "[emotion:calm] 老师，记得喝水。"
            generated = True
            model = "fake-model"

        class Generator:
            def __init__(self):
                self.calls = []

            async def generate_text(self, system, user, **options):
                self.calls.append((system, user, options))
                return Result()

        generator = Generator()
        facade = QQControlAdapterFacade(
            object(),
            object(),
            object(),
            text_generator_provider=lambda: generator,
        )
        app = FastAPI()
        app.include_router(
            create_qq_control_router(
                facade,
                read_guard=lambda _request: True,
                write_guard=lambda _request: True,
            )
        )

        async def exercise():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/life-support/reminder",
                    json={"kind": "hydrate"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {
                    "text": "老师，记得喝水。",
                    "generated": True,
                    "model": "fake-model",
                })
                invalid = await client.post(
                    "/life-support/reminder",
                    json={"kind": "reset"},
                )
                self.assertEqual(invalid.status_code, 422)

                degraded = QQControlAdapterFacade(
                    object(),
                    object(),
                    object(),
                    text_generator_provider=lambda: None,
                )
                degraded_app = FastAPI()
                degraded_app.include_router(
                    create_qq_control_router(
                        degraded,
                        read_guard=lambda _request: True,
                        write_guard=lambda _request: True,
                    )
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=degraded_app),
                    base_url="http://test",
                ) as degraded_client:
                    fallback = await degraded_client.post(
                        "/life-support/reminder",
                        json={"kind": "rest"},
                    )
                    self.assertEqual(fallback.status_code, 200)
                    self.assertFalse(fallback.json()["generated"])
                    self.assertIsNone(fallback.json()["model"])

        asyncio.run(exercise())
        self.assertEqual(len(generator.calls), 1)


if __name__ == "__main__":
    unittest.main()
