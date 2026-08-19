"""Offline lifecycle checks for PK-010 local installable modules."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import _path_setup  # noqa: F401
import httpx
from fastapi import FastAPI

from core.modules import (
    CORE_RESERVED_API_NAMESPACES,
    CORE_RESERVED_MODULE_IDS,
    DEPENDENCY_DEPLOYMENT_MARKER,
    InProcessModuleLoader,
    ModuleActivationCoordinator,
    ModuleManager,
    SidecarDeploymentDescriptor,
    SidecarReadiness,
)
from core.modules.exceptions import (
    ManifestValidationError,
    ModuleConflictError,
    ModuleNotFoundError,
    ModuleOperationError,
    PackageValidationError,
    SidecarReadinessError,
)
from core.modules.manifest import ALLOWED_PERMISSIONS, validate_manifest


SERVER_ROOT = Path(__file__).resolve().parents[1]


def make_manifest(
    module_id: str,
    version: str = "1.0.0",
    module_type: str = "in_process",
    dependencies=None,
    optional_dependencies=None,
    namespace=None,
    permissions=None,
    runtime_requirements=None,
) -> dict:
    payload = {
        "schema_version": 1,
        "id": module_id,
        "name": "Test %s" % module_id,
        "version": version,
        "type": module_type,
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "dependencies": list(dependencies or []),
        "optional_dependencies": list(optional_dependencies or []),
        "runtime_requirements": list(runtime_requirements or []),
        "conflicts": [],
        "api_namespaces": [namespace or "/api/v1/%s" % module_id.replace("_", "-")],
        "legacy_endpoints": [],
        "dashboard_entrypoint": "dashboard/index.js",
        "data_namespace": module_id,
        "config_schema": None,
        "permissions": list(permissions or ["local_state"]),
        "requires_restart": module_type == "in_process",
    }
    if module_type == "in_process":
        payload["entrypoint"] = "backend.register"
    else:
        payload["sidecar"] = {"adapter": "test_sidecar", "healthcheck_timeout_seconds": 2}
    return payload


def write_package(root: Path, manifest: dict, backend_source: str = None) -> Path:
    package = root / (manifest["id"] + "-" + manifest["version"])
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    dashboard = package / "dashboard"
    dashboard.mkdir()
    (dashboard / "index.js").write_text("export default {};\n", encoding="utf-8")
    if manifest["type"] == "in_process":
        (package / "backend.py").write_text(
            backend_source or "def register(app):\n    return None\n", encoding="utf-8"
        )
    return package


def write_zip_package(package: Path, archive: Path) -> Path:
    with zipfile.ZipFile(str(archive), "w", compression=zipfile.ZIP_DEFLATED) as target:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                target.write(str(path), path.relative_to(package).as_posix())
    return archive


def new_manager(root: Path, adapters=None, runtime_probe=None) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
        sidecar_adapters=adapters,
        runtime_probe=runtime_probe,
    )


def install(manager: ModuleManager, package: Path, module_id: str = None) -> dict:
    digest = manager.calculate_package_sha256(package)
    return manager.install(package, digest, expected_module_id=module_id or package.name.split("-")[0])


class FakeSidecarAdapter:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.healthy = True

    def start(self, manifest, package_root):
        self.starts += 1

    def stop(self, manifest, package_root):
        self.stops += 1

    def is_healthy(self, manifest, package_root):
        return self.healthy


class ReadinessSidecarAdapter(FakeSidecarAdapter):
    def __init__(self, code="ready", missing=()):
        super().__init__()
        self.code = code
        self.missing = tuple(missing)
        self.readiness_error = None

    def readiness(self, manifest, package_root):
        if self.readiness_error is not None:
            raise self.readiness_error
        return SidecarReadiness.from_code(self.code, self.missing)


class OrderedSidecarAdapter(FakeSidecarAdapter):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def start(self, manifest, package_root):
        super().start(manifest, package_root)
        self.events.append("start:%s" % manifest.id)

    def stop(self, manifest, package_root):
        super().stop(manifest, package_root)
        self.events.append("stop:%s" % manifest.id)


class MalformedReadinessAdapter(FakeSidecarAdapter):
    def readiness(self, manifest, package_root):
        return SidecarReadiness(
            status="needs_configuration",
            code="qq_env_missing",
            message="token=secret-value C:/private/.env",
            missing_requirements=("C:/private/.env",),
        )


class DeploymentAwareSidecarAdapter:
    def __init__(self):
        self.readiness_code = "ready"
        self.readiness_missing = ()
        self.started = []
        self.stopped = []
        self.healthy = True
        self.start_error = None
        self.stop_error = None

    def deployment_readiness(self, manifest, deployment):
        assert isinstance(deployment, SidecarDeploymentDescriptor)
        return SidecarReadiness.from_code(
            self.readiness_code,
            self.readiness_missing,
        )

    def start_deployment(self, manifest, deployment):
        if self.start_error is not None:
            raise self.start_error
        self.started.append(deployment)

    def stop_deployment(self, manifest, deployment):
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped.append(deployment)

    def is_deployment_healthy(self, manifest, deployment):
        return self.healthy


def install_official_directory(
    manager: ModuleManager,
    package: Path,
    module_id: str,
) -> tuple[dict, str, str]:
    digest = manager.calculate_package_sha256(package)
    manifest_sha256 = hashlib.sha256(
        (package / "manifest.json").read_bytes()
    ).hexdigest()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    result = manager.install(
        package,
        digest,
        expected_module_id=module_id,
        version_metadata={
            "source": "official_github_release",
            "publisher": "Project Kei",
            "owner": "songshu-yu",
            "repository": "Project-Kei-Modules",
            "release_tag": "module-%s-v%s" % (module_id, manifest["version"]),
            "asset_name": "%s-%s.zip" % (module_id, manifest["version"]),
            "manifest_sha256": manifest_sha256,
        },
    )
    return result, digest, manifest_sha256


async def request_sidecar_enable(manager: ModuleManager, module_id: str) -> httpx.Response:
    import features.module_manager.router as module_router

    app = FastAPI()
    app.include_router(module_router.router)
    original = module_router.get_module_manager
    module_router.get_module_manager = lambda: manager
    try:
        transport = httpx.ASGITransport(
            app=app,
            client=("127.0.0.1", 12345),
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://project-kei.test",
        ) as client:
            return await client.post(
                "/api/v1/modules/%s/enable" % module_id,
                headers={"Origin": "http://127.0.0.1:8000"},
            )
    finally:
        module_router.get_module_manager = original


def test_browser_local_zip_upload_contract() -> None:
    async def exercise() -> None:
        import features.module_manager.router as module_router

        with tempfile.TemporaryDirectory(prefix="kei-local-upload-test-") as temp:
            root = Path(temp)
            manager = new_manager(root / "manager")
            package = write_package(
                root / "packages",
                make_manifest("local_upload_demo"),
            )
            archive = write_zip_package(package, root / "local_upload_demo-1.0.0.zip")
            payload = archive.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            qq_archive = write_zip_package(
                write_package(root / "qq-package", make_manifest("qq_bridge")),
                root / "qq_bridge-1.0.0.zip",
            )
            qq_payload = qq_archive.read_bytes()
            qq_digest = hashlib.sha256(qq_payload).hexdigest()
            next_archive = write_zip_package(
                write_package(root / "next-package", make_manifest("after_qq")),
                root / "misleading-client-filename.zip",
            )
            next_payload = next_archive.read_bytes()
            next_digest = hashlib.sha256(next_payload).hexdigest()
            stale_archive = write_zip_package(
                write_package(root / "stale-package", make_manifest("after_stale_id")),
                root / "after_stale_id-1.0.0.zip",
            )
            stale_payload = stale_archive.read_bytes()
            stale_digest = hashlib.sha256(stale_payload).hexdigest()
            upload_root = root / "uploads"
            upload_root.mkdir()
            original_manager = module_router.get_module_manager
            original_factory = module_router._UPLOAD_TEMPORARY_DIRECTORY
            original_limit = module_router.LOCAL_MODULE_UPLOAD_MAX_BYTES
            module_router.get_module_manager = lambda: manager
            module_router._UPLOAD_TEMPORARY_DIRECTORY = lambda **kwargs: tempfile.TemporaryDirectory(
                dir=str(upload_root), **kwargs
            )
            try:
                app = FastAPI()
                app.include_router(module_router.router)
                transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
                headers = {
                    "Origin": "http://127.0.0.1:8000",
                    "Content-Type": "application/zip",
                    "X-Project-Kei-Package-SHA256": digest,
                }
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://project-kei.test",
                ) as client:
                    response = await client.post(
                        "/api/v1/modules/local_upload_demo/install-upload",
                        headers=headers,
                        content=payload,
                    )
                    assert response.status_code == 200, response.text
                    body = response.json()
                    assert body["module_id"] == "local_upload_demo"
                    assert body["install_status"] == "installed_disabled"
                    assert body["local_upload"] == {
                        "status": "success",
                        "received_bytes": len(payload),
                        "sha256": digest,
                    }
                    assert "package_path" not in json.dumps(body)
                    assert not any(upload_root.iterdir())

                    qq_response = await client.post(
                        "/api/v1/modules/install-upload",
                        headers={
                            **headers,
                            "X-Project-Kei-Package-SHA256": qq_digest,
                        },
                        content=qq_payload,
                    )
                    assert qq_response.status_code == 200, qq_response.text
                    assert qq_response.json()["module_id"] == "qq_bridge"
                    assert qq_response.json()["installed_version"] == "1.0.0"

                    next_response = await client.post(
                        "/api/v1/modules/install-upload?expected_module_id=",
                        headers={
                            **headers,
                            "X-Project-Kei-Package-SHA256": next_digest,
                        },
                        content=next_payload,
                    )
                    assert next_response.status_code == 200, next_response.text
                    assert next_response.json()["module_id"] == "after_qq"
                    assert next_response.json()["installed_version"] == "1.0.0"
                    assert "misleading-client-filename" not in json.dumps(
                        next_response.json()
                    )
                    assert not any(upload_root.iterdir())

                    before_stale_mismatch = manager.snapshot()
                    stale_expected_id = await client.post(
                        "/api/v1/modules/install-upload?expected_module_id=qq_bridge",
                        headers={
                            **headers,
                            "X-Project-Kei-Package-SHA256": stale_digest,
                        },
                        content=stale_payload,
                    )
                    assert stale_expected_id.status_code == 422
                    assert "does not match requested module" in (
                        stale_expected_id.json()["detail"]
                    )
                    assert manager.snapshot() == before_stale_mismatch
                    assert not (
                        manager.runtime_root / "after_stale_id" / "1.0.0"
                    ).exists()
                    assert not any(upload_root.iterdir())

                    bad_digest = "0" * 64 if digest != "0" * 64 else "1" * 64
                    mismatch = await client.post(
                        "/api/v1/modules/hash_mismatch/install-upload",
                        headers={**headers, "X-Project-Kei-Package-SHA256": bad_digest},
                        content=payload,
                    )
                    assert mismatch.status_code == 422
                    assert mismatch.json()["detail"]["code"] == (
                        "local_module_upload_integrity_mismatch"
                    )
                    assert "hash_mismatch" not in manager.snapshot()
                    assert not any(upload_root.iterdir())

                    wrong_id = await client.post(
                        "/api/v1/modules/not_the_manifest_id/install-upload",
                        headers=headers,
                        content=payload,
                    )
                    assert wrong_id.status_code == 422
                    assert "does not match requested module" in wrong_id.json()["detail"]
                    assert "not_the_manifest_id" not in manager.snapshot()
                    assert not any(upload_root.iterdir())

                    invalid_type = await client.post(
                        "/api/v1/modules/bad_type/install-upload",
                        headers={
                            **headers,
                            "Content-Type": "application/octet-stream",
                        },
                        content=payload,
                    )
                    assert invalid_type.status_code == 415
                    assert invalid_type.json()["detail"]["code"] == (
                        "local_module_upload_content_type_invalid"
                    )

                    module_router.LOCAL_MODULE_UPLOAD_MAX_BYTES = 16
                    oversized_payload = b"x" * 17
                    oversized = await client.post(
                        "/api/v1/modules/too_large/install-upload",
                        headers={
                            **headers,
                            "X-Project-Kei-Package-SHA256": hashlib.sha256(
                                oversized_payload
                            ).hexdigest(),
                        },
                        content=oversized_payload,
                    )
                    assert oversized.status_code == 413
                    assert oversized.json()["detail"]["code"] == (
                        "local_module_upload_too_large"
                    )
                    assert not any(upload_root.iterdir())

                remote_transport = httpx.ASGITransport(
                    app=app,
                    client=("192.0.2.10", 54321),
                )
                async with httpx.AsyncClient(
                    transport=remote_transport,
                    base_url="http://project-kei.test",
                ) as remote:
                    denied = await remote.post(
                        "/api/v1/modules/remote/install-upload",
                        headers=headers,
                        content=payload,
                    )
                    assert denied.status_code == 403
                    assert "remote" not in manager.snapshot()
            finally:
                module_router.get_module_manager = original_manager
                module_router._UPLOAD_TEMPORARY_DIRECTORY = original_factory
                module_router.LOCAL_MODULE_UPLOAD_MAX_BYTES = original_limit

    asyncio.run(exercise())


def test_schema_and_empty_state() -> None:
    schema = json.loads((SERVER_ROOT / "core" / "modules" / "manifest.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == 1
    with tempfile.TemporaryDirectory() as temp:
        manager = new_manager(Path(temp))
        assert manager.snapshot() == {}
        assert not (Path(temp) / "data" / "module_registry.json").exists()


def test_manifest_network_download_permission_closed_set() -> None:
    schema_paths = (
        SERVER_ROOT / "core" / "modules" / "manifest.schema.json",
        SERVER_ROOT / "core" / "modules" / "official-catalog.schema.json",
        SERVER_ROOT
        / "core"
        / "modules"
        / "official-release-fragment.schema.json",
    )
    manifest_schema = json.loads(schema_paths[0].read_text(encoding="utf-8"))
    catalog_schema = json.loads(schema_paths[1].read_text(encoding="utf-8"))
    fragment_schema = json.loads(schema_paths[2].read_text(encoding="utf-8"))
    assert set(manifest_schema["properties"]["permissions"]["items"]["enum"]) == (
        ALLOWED_PERMISSIONS
    )
    assert set(
        catalog_schema["properties"]["modules"]["items"]["properties"]
        ["permissions"]["items"]["enum"]
    ) == ALLOWED_PERMISSIONS
    assert set(
        fragment_schema["properties"]["permissions"]["items"]["enum"]
    ) == ALLOWED_PERMISSIONS

    approved = make_manifest(
        "approved_downloader",
        permissions=["local_state", "network_download"],
    )
    assert validate_manifest(approved).permissions == (
        "local_state",
        "network_download",
    )
    for module_id, permissions in (
        ("unknown_permission", ["local_state", "arbitrary_network"]),
        ("duplicate_permission", ["network_download", "network_download"]),
        ("case_variant_permission", ["local_state", "Network_Download"]),
    ):
        rejected = make_manifest(module_id, permissions=permissions)
        try:
            validate_manifest(rejected)
            raise AssertionError("invalid permission declaration was accepted")
        except ManifestValidationError:
            pass

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        legacy = write_package(
            root / "packages",
            make_manifest("legacy_local_state"),
        )
        approved_package = write_package(root / "packages", approved)
        assert install(manager, legacy, "legacy_local_state")["permissions"] == [
            "local_state"
        ]
        installed = install(
            manager,
            approved_package,
            "approved_downloader",
        )
        assert installed["permissions"] == [
            "local_state",
            "network_download",
        ]
        assert manager.snapshot()["approved_downloader"]["permissions"] == [
            "local_state",
            "network_download",
        ]


def test_runtime_requirements_are_declarative_and_checked_before_enable() -> None:
    declaration = {
        "id": "node",
        "supported_major_versions": [20, 22, 24, 26],
        "architecture": "x64",
    }
    parsed = validate_manifest(
        make_manifest("runtime_consumer", runtime_requirements=[declaration])
    )
    assert [item.to_dict() for item in parsed.runtime_requirements] == [declaration]

    for rejected in (
        {**declaration, "command": "npm install"},
        {**declaration, "path": "C:/private/node.exe"},
        {**declaration, "id": "shell"},
        {**declaration, "supported_major_versions": [26, 24]},
        {**declaration, "supported_major_versions": [24, 24]},
        {**declaration, "architecture": "arm64"},
    ):
        payload = make_manifest(
            "rejected_runtime",
            runtime_requirements=[rejected],
        )
        try:
            validate_manifest(payload)
            raise AssertionError("unsafe runtime requirement was accepted")
        except ManifestValidationError:
            pass

    detected = {"node": None}

    def probe(runtime_id: str):
        return detected[runtime_id]

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root, runtime_probe=probe)
        package = write_package(
            root / "packages",
            make_manifest(
                "runtime_consumer",
                runtime_requirements=[declaration],
            ),
        )
        installed = install(manager, package, "runtime_consumer")
        assert installed["install_status"] == "needs_configuration"
        assert installed["runtime_readiness"] == {
            "ready": False,
            "checks": [{
                "id": "node",
                "status": "missing",
                "detected_version": None,
                "detected_architecture": None,
                "supported_major_versions": [20, 22, 24, 26],
                "required_architecture": "x64",
            }],
        }
        try:
            manager.enable("runtime_consumer")
            raise AssertionError("module enabled without its declared runtime")
        except ModuleConflictError as exc:
            assert str(exc) == "module runtime requirements are not ready: node"

        detected["node"] = ("25.1.0", "x64")
        unsupported = manager.check_configuration("runtime_consumer")
        assert unsupported["runtime_readiness"]["checks"][0]["status"] == (
            "version_unsupported"
        )
        detected["node"] = ("26.5.0", "x64")
        ready = manager.check_configuration("runtime_consumer")
        assert ready["configuration_ready"] is True
        assert ready["runtime_readiness"]["ready"] is True
        assert manager.enable("runtime_consumer")["enabled"] is True


def test_install_reports_required_module_dependency_readiness() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        consumer_package = write_package(
            root / "packages",
            make_manifest("consumer", dependencies=["provider"]),
        )
        installed = install(manager, consumer_package, "consumer")
        assert installed["dependency_readiness"] == {
            "ready": False,
            "checks": [{"module_id": "provider", "status": "missing"}],
        }

        provider_package = write_package(
            root / "packages",
            make_manifest("provider"),
        )
        install(manager, provider_package, "provider")
        assert manager.get("consumer")["dependency_readiness"] == {
            "ready": False,
            "checks": [{"module_id": "provider", "status": "disabled"}],
        }
        manager.enable("provider")
        assert manager.get("consumer")["dependency_readiness"] == {
            "ready": True,
            "checks": [{"module_id": "provider", "status": "ready"}],
        }


def test_install_update_rollback_and_data_preservation() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        package_v1 = write_package(root / "packages", make_manifest("sample", "1.0.0"))
        result = install(manager, package_v1, "sample")
        assert result["install_status"] == "installed_disabled"
        assert result["installed_version"] == "1.0.0"
        try:
            install(manager, package_v1, "sample")
            raise AssertionError("duplicate install should fail")
        except ModuleConflictError:
            pass

        enabled = manager.enable("sample")
        assert enabled["enabled"] is True and enabled["restart_required"] is True
        package_v2 = write_package(root / "packages", make_manifest("sample", "2.0.0"))
        digest_v2 = manager.calculate_package_sha256(package_v2)
        updated = manager.update("sample", package_v2, digest_v2)
        assert updated["installed_version"] == "2.0.0"
        assert updated["previous_version"] == "1.0.0"
        rolled_back = manager.rollback("sample")
        assert rolled_back["installed_version"] == "1.0.0"

        data_path = root / "data" / "modules" / "sample"
        data_path.mkdir(parents=True)
        (data_path / "state.json").write_text("{}", encoding="utf-8")
        removed = manager.uninstall("sample")
        assert removed["data_preserved"] is True
        assert data_path.is_dir()
        assert "sample" not in manager.snapshot()


def test_invalid_packages_do_not_reach_runtime() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        incompatible = make_manifest("incompatible")
        incompatible["core_compatibility"] = ">=9.0.0"
        package = write_package(root / "packages", incompatible)
        digest = manager.calculate_package_sha256(package)
        try:
            manager.install(package, digest, "incompatible")
            raise AssertionError("incompatible manifest should fail")
        except ManifestValidationError:
            pass
        assert not (root / "runtime" / "modules" / "incompatible").exists()

        archive = root / "traversal.zip"
        with zipfile.ZipFile(str(archive), "w") as handle:
            handle.writestr("../escape.txt", "no")
            handle.writestr("manifest.json", "{}")
        try:
            manager.install(archive, manager.calculate_package_sha256(archive), "escape")
            raise AssertionError("path traversal should fail")
        except PackageValidationError:
            pass
        assert not (root / "runtime" / "modules" / "escape").exists()
        assert not (root / "escape.txt").exists()


def test_core_ids_and_namespaces_are_reserved_without_state() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        registry_path = root / "data" / "module_registry.json"
        runtime_root = root / "runtime" / "modules"

        for module_id in sorted(CORE_RESERVED_MODULE_IDS):
            package = write_package(root / "packages", make_manifest(module_id))
            try:
                install(manager, package, module_id)
                raise AssertionError("reserved Core module id was installed: %s" % module_id)
            except ModuleConflictError:
                pass
            assert not registry_path.exists()
            assert not (runtime_root / module_id).exists()
            assert not (root / "data" / "modules").exists()
            assert manager.snapshot() == {}

        reserved_namespaces = sorted(CORE_RESERVED_API_NAMESPACES)
        namespace_cases = reserved_namespaces + [reserved_namespaces[0] + "/shadow"]
        for index, namespace in enumerate(namespace_cases):
            module_id = "namespace_shadow_%s" % index
            package = write_package(
                root / "packages",
                make_manifest(module_id, namespace=namespace),
            )
            try:
                install(manager, package, module_id)
                raise AssertionError("reserved Core namespace was installed: %s" % namespace)
            except ModuleConflictError:
                pass
            assert not registry_path.exists()
            assert not (runtime_root / module_id).exists()
            assert not (root / "data" / "modules").exists()
            assert manager.snapshot() == {}

        normal = write_package(root / "packages", make_manifest("normal_optional"))
        installed = install(manager, normal, "normal_optional")
        assert installed["install_status"] == "installed_disabled"
        enabled = manager.enable("normal_optional")
        assert enabled["enabled"] is True
        assert set(manager.snapshot()) == {"normal_optional"}


def test_dependency_cycles_and_failed_update_keep_old_version() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        alpha = write_package(root / "packages", make_manifest("alpha", dependencies=["beta"]))
        install(manager, alpha, "alpha")
        try:
            manager.enable("alpha")
            raise AssertionError("missing dependency should block enable")
        except ModuleConflictError:
            pass
        beta = write_package(root / "packages", make_manifest("beta", dependencies=["alpha"]))
        try:
            install(manager, beta, "beta")
            raise AssertionError("dependency cycle should fail")
        except ModuleConflictError:
            pass

        stable = write_package(root / "packages", make_manifest("stable", "1.0.0"))
        install(manager, stable, "stable")
        broken_manifest = make_manifest("stable", "2.0.0")
        broken = write_package(root / "packages", broken_manifest)
        (broken / "backend.py").unlink()
        digest = manager.calculate_package_sha256(broken)
        try:
            manager.update("stable", broken, digest)
            raise AssertionError("broken update should fail")
        except PackageValidationError:
            pass
        current = manager.get("stable")
        assert current["installed_version"] == "1.0.0"
        assert not (root / "runtime" / "modules" / "stable" / "2.0.0").exists()


def test_in_process_loader_and_sidecar_stop_protocol() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        adapter = FakeSidecarAdapter()
        manager = new_manager(root, {"test_sidecar": adapter})
        backend = (
            "def register(app):\n"
            "    @app.get('/api/v1/loadable/ping')\n"
            "    async def ping():\n"
            "        return {'ok': True}\n"
        )
        loadable = write_package(root / "packages", make_manifest("loadable"), backend)
        install(manager, loadable, "loadable")
        manager.enable("loadable")
        app = FastAPI()
        loader = InProcessModuleLoader()
        results = loader.load(app, manager.enabled_in_process_descriptors())
        manager.record_load_results(results)
        assert results == [{"module_id": "loadable", "status": "loaded"}]
        assert "/api/v1/loadable/ping" in {route.path for route in app.routes}
        assert manager.get("loadable")["restart_required"] is False
        assert manager.asset_path("loadable", "dashboard/index.js").is_file()
        try:
            manager.asset_path("loadable", "backend.py")
            raise AssertionError("backend source must not be served as a dashboard asset")
        except ModuleNotFoundError:
            pass

        data_path = root / "data" / "modules" / "loadable"
        data_path.mkdir(parents=True)
        (data_path / "state.json").write_text("{}", encoding="utf-8")
        try:
            manager.purge_data("loadable", "wrong-id")
            raise AssertionError("purge must require exact confirmation")
        except ModuleConflictError:
            pass
        assert data_path.exists()
        assert manager.purge_data("loadable", "loadable")["purged"] is True
        assert not data_path.exists()

        sidecar = write_package(root / "packages", make_manifest("worker", module_type="sidecar"))
        installed = install(manager, sidecar, "worker")
        assert installed["sidecar_readiness"]["code"] == "legacy_healthcheck"
        manager.enable("worker")
        assert adapter.starts == 1
        manager.disable("worker")
        assert adapter.stops == 1


def test_sidecar_readiness_state_machine_and_redaction() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        adapter = ReadinessSidecarAdapter(
            "qq_env_missing",
            ("qq_app_id", "qq_access_token"),
        )
        manager = new_manager(root, {"test_sidecar": adapter})
        package = write_package(
            root / "packages",
            make_manifest("qq_optional", module_type="sidecar"),
        )

        installed = install(manager, package, "qq_optional")
        assert installed["install_status"] == "needs_configuration"
        assert installed["configuration_ready"] is False
        assert installed["sidecar_readiness"] == {
            "status": "needs_configuration",
            "code": "qq_env_missing",
            "message": "QQ configuration requirements are missing",
            "missing_requirements": ["qq_app_id", "qq_access_token"],
        }

        checked = manager.check_configuration("qq_optional")
        assert checked["install_status"] == "needs_configuration"
        assert checked["missing_requirements"] == ["qq_app_id", "qq_access_token"]
        response = asyncio.run(request_sidecar_enable(manager, "qq_optional"))
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "sidecar_needs_configuration",
            "message": "sidecar requirements are not ready",
            "sidecar_readiness": installed["sidecar_readiness"],
        }
        try:
            manager.enable("qq_optional")
            raise AssertionError("sidecar readiness must block enable")
        except SidecarReadinessError as exc:
            assert exc.detail()["code"] == "sidecar_needs_configuration"
            assert exc.readiness.code == "qq_env_missing"
        blocked = manager.get("qq_optional")
        assert blocked["enabled"] is False
        assert blocked["install_status"] == "needs_configuration"
        assert adapter.starts == 0
        assert set(manager.registry.load()["modules"]) == {"qq_optional"}
        assert (
            root / "runtime" / "modules" / "qq_optional" / "1.0.0"
        ).is_dir()

        adapter.code = "ready"
        adapter.missing = ()
        assert manager.check_configuration("qq_optional")["install_status"] == "installed_disabled"
        assert manager.enable("qq_optional")["install_status"] == "enabled"
        assert adapter.starts == 1

        adapter.code = "dependencies_missing"
        adapter.missing = ("node_modules",)
        restarted_manager = new_manager(root, {"test_sidecar": adapter})
        startup = restarted_manager.start_enabled_sidecars()
        assert startup[0]["status"] == "needs_configuration"
        assert startup[0]["sidecar_readiness"]["status"] == "needs_configuration"
        assert startup[0]["code"] == "dependencies_missing"
        after_start = restarted_manager.get("qq_optional")
        assert after_start["enabled"] is True
        assert after_start["install_status"] == "needs_configuration"
        assert adapter.starts == 1
        adapter.code = "ready"
        adapter.missing = ()
        assert restarted_manager.start_enabled_sidecars() == [
            {"module_id": "qq_optional", "status": "started"}
        ]
        recovered = restarted_manager.get("qq_optional")
        assert recovered["configuration_ready"] is True
        assert recovered["sidecar_readiness"]["code"] == "ready"
        assert recovered["install_status"] == "enabled"
        assert adapter.starts == 2

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        adapter = ReadinessSidecarAdapter()
        adapter.readiness_error = RuntimeError(
            "token=secret-value C:/private/qq/.env upstream response"
        )
        manager = new_manager(root, {"test_sidecar": adapter})
        package = write_package(
            root / "packages",
            make_manifest("exceptional_sidecar", module_type="sidecar"),
        )
        result = install(manager, package, "exceptional_sidecar")
        wire = json.dumps(result, ensure_ascii=False)
        assert result["install_status"] == "needs_configuration"
        assert result["sidecar_readiness"]["code"] == "adapter_unavailable"
        assert "secret-value" not in wire
        assert ".env" not in wire
        assert "C:/" not in wire

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        adapter = MalformedReadinessAdapter()
        manager = new_manager(root, {"test_sidecar": adapter})
        package = write_package(
            root / "packages",
            make_manifest("malformed_sidecar", module_type="sidecar"),
        )
        result = install(manager, package, "malformed_sidecar")
        wire = json.dumps(result, ensure_ascii=False)
        assert result["sidecar_readiness"]["code"] == "adapter_unavailable"
        assert "secret-value" not in wire
        assert ".env" not in wire
        assert "C:/" not in wire


def test_sidecar_adapter_registration_seam() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        package = write_package(
            root / "packages",
            make_manifest("registered_sidecar", module_type="sidecar"),
        )
        installed = install(manager, package, "registered_sidecar")
        assert installed["sidecar_readiness"]["code"] == "adapter_unavailable"

        adapter = ReadinessSidecarAdapter("ready")
        manager.register_sidecar_adapter("test_sidecar", adapter)
        assert manager.check_configuration("registered_sidecar")["configuration_ready"] is True
        assert manager.enable("registered_sidecar")["enabled"] is True
        restarted_without_adapter = new_manager(root)
        startup = restarted_without_adapter.start_enabled_sidecars()
        assert startup[0]["status"] == "unavailable"
        assert startup[0]["code"] == "adapter_unavailable"
        assert (
            restarted_without_adapter.get("registered_sidecar")["install_status"]
            == "needs_configuration"
        )
        try:
            manager.register_sidecar_adapter("test_sidecar", adapter)
            raise AssertionError("reviewed adapters cannot be silently replaced")
        except ValueError:
            pass
        try:
            manager.register_sidecar_adapter("incomplete_adapter", object())
            raise AssertionError("incomplete adapter protocol was registered")
        except ValueError:
            pass


def test_sidecar_dependency_deployment_descriptor_and_rollback() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        adapter = DeploymentAwareSidecarAdapter()
        manager = new_manager(root, {"test_sidecar": adapter})
        package_v1 = write_package(
            root / "packages",
            make_manifest("node_sidecar", "1.0.0", module_type="sidecar"),
        )
        installed, digest_v1, manifest_sha_v1 = install_official_directory(
            manager,
            package_v1,
            "node_sidecar",
        )
        descriptor_v1 = manager.resolve_sidecar_deployment("node_sidecar")
        assert descriptor_v1.version == "1.0.0"
        assert descriptor_v1.package_root == (
            root / "runtime" / "modules" / "node_sidecar" / "1.0.0"
        )
        assert descriptor_v1.dependency_deployment_root == (
            root / "runtime" / "module-dependencies" / "node_sidecar" / "1.0.0"
        )
        assert descriptor_v1.installed_tree_sha256 == installed["package_sha256"]

        dependency_file = (
            descriptor_v1.dependency_deployment_root
            / "node_modules"
            / "example"
            / "index.js"
        )
        dependency_file.parent.mkdir(parents=True)
        dependency_file.write_text("module.exports = {};\n", encoding="utf-8")
        assert DEPENDENCY_DEPLOYMENT_MARKER == ".project-kei-deployment.json"
        (
            descriptor_v1.dependency_deployment_root
            / DEPENDENCY_DEPLOYMENT_MARKER
        ).write_text(
            '{"layout_version": 1}\n',
            encoding="utf-8",
        )
        assert (
            manager.calculate_package_sha256(descriptor_v1.package_root)
            == descriptor_v1.installed_tree_sha256
        )
        from features.catalog.models import ModuleInfo

        public_model = ModuleInfo(
            key="node_sidecar",
            label="Node sidecar",
            task_id="PK-test",
            task_file="tasks/test.md",
            process="sidecar",
            current_endpoints=[],
            target_namespace="/api/v1/node-sidecar",
            migration_status="modular",
            **manager.get("node_sidecar"),
        )
        public_wire = public_model.model_dump_json()
        assert '"sidecar_readiness"' in public_wire
        assert str(descriptor_v1.package_root) not in public_wire
        assert str(descriptor_v1.dependency_deployment_root) not in public_wire
        assert "module-dependencies" not in public_wire

        manager.enable("node_sidecar")
        assert adapter.started[-1] == descriptor_v1
        package_v2 = write_package(
            root / "packages",
            make_manifest("node_sidecar", "2.0.0", module_type="sidecar"),
        )
        digest_v2 = manager.calculate_package_sha256(package_v2)
        manifest_sha_v2 = hashlib.sha256(
            (package_v2 / "manifest.json").read_bytes()
        ).hexdigest()
        manager.update(
            "node_sidecar",
            package_v2,
            digest_v2,
            version_metadata={
                "source": "official_github_release",
                "publisher": "Project Kei",
                "owner": "songshu-yu",
                "repository": "Project-Kei-Modules",
                "release_tag": "module-node_sidecar-v2.0.0",
                "asset_name": "node_sidecar-2.0.0.zip",
                "manifest_sha256": manifest_sha_v2,
            },
        )
        descriptor_v2 = manager.resolve_sidecar_deployment("node_sidecar")
        assert descriptor_v2.version == "2.0.0"
        assert adapter.started[-1] == descriptor_v2
        assert adapter.stopped[-1] == descriptor_v1
        try:
            manager.resolve_sidecar_deployment("node_sidecar", "1.0.0")
            raise AssertionError("non-current dependency deployment was resolved")
        except ModuleConflictError:
            pass

        (descriptor_v2.dependency_deployment_root / "node_modules").mkdir(
            parents=True
        )
        (descriptor_v2.dependency_deployment_root / "node_modules" / "v2.txt").write_text(
            "generated dependency",
            encoding="utf-8",
        )
        rolled_back = manager.rollback(
            "node_sidecar",
            expected_version="1.0.0",
            expected_package_sha256=digest_v1,
            expected_manifest_sha256=manifest_sha_v1,
            require_official=True,
        )
        assert rolled_back["installed_version"] == "1.0.0"
        assert manager.resolve_sidecar_deployment("node_sidecar") == descriptor_v1
        assert adapter.started[-1] == descriptor_v1
        assert (
            manager.calculate_package_sha256(descriptor_v1.package_root)
            == descriptor_v1.installed_tree_sha256
        )


def test_sidecar_dependency_descriptor_rejects_unsafe_state() -> None:
    import core.modules.manager as manager_module

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        try:
            ModuleManager(
                runtime_root=root / "runtime" / "modules",
                registry_path=root / "data" / "registry.json",
                data_root=root / "data" / "modules",
                dependency_deployment_root=root / "runtime" / "modules" / "deps",
            )
            raise AssertionError("overlapping dependency root was accepted")
        except ValueError:
            pass

        adapter = DeploymentAwareSidecarAdapter()
        manager = new_manager(root, {"test_sidecar": adapter})
        try:
            manager.resolve_sidecar_deployment("missing_sidecar")
            raise AssertionError("uninstalled sidecar deployment was resolved")
        except ModuleNotFoundError:
            pass
        for invalid in ("../escape", "Uppercase", "node/sidecar"):
            try:
                manager.resolve_sidecar_deployment(invalid)
                raise AssertionError("unsafe module id was accepted")
            except (ModuleNotFoundError, ModuleOperationError):
                pass

        package = write_package(
            root / "packages",
            make_manifest("safe_sidecar", module_type="sidecar"),
        )
        install(manager, package, "safe_sidecar")
        try:
            manager.resolve_sidecar_deployment("safe_sidecar", "../1.0.0")
            raise AssertionError("unsafe version was accepted")
        except ModuleOperationError:
            pass

        registry = manager.registry.load()
        registry["modules"]["safe_sidecar"]["versions"]["1.0.0"]["path"] = (
            "../../outside"
        )
        manager.registry.save(registry)
        try:
            manager.resolve_sidecar_deployment("safe_sidecar")
            raise AssertionError("forged package path was accepted")
        except ModuleOperationError:
            pass
        registry["modules"]["safe_sidecar"]["versions"]["1.0.0"]["path"] = (
            "safe_sidecar/1.0.0"
        )
        manager.registry.save(registry)

        descriptor = manager.resolve_sidecar_deployment("safe_sidecar")
        descriptor.dependency_deployment_root.mkdir(parents=True)
        original_link_check = manager_module._is_link_or_reparse

        def fake_link_check(path):
            if Path(path) == descriptor.dependency_deployment_root:
                return True
            return original_link_check(path)

        manager_module._is_link_or_reparse = fake_link_check
        try:
            try:
                manager.resolve_sidecar_deployment("safe_sidecar")
                raise AssertionError("dependency reparse point was accepted")
            except ModuleOperationError:
                pass
        finally:
            manager_module._is_link_or_reparse = original_link_check

        adapter.start_error = RuntimeError(
            "C:/private/module-dependencies token=secret-value"
        )
        try:
            manager.enable("safe_sidecar")
            raise AssertionError("sidecar start exception was accepted")
        except ModuleOperationError as exc:
            assert str(exc) == "sidecar start failed"
        public_wire = json.dumps(manager.get("safe_sidecar"), ensure_ascii=False)
        assert "C:/private" not in public_wire
        assert "secret-value" not in public_wire


def test_sidecar_readiness_stable_mapping() -> None:
    expected = {
        "dependencies_missing": "needs_configuration",
        "configuration_missing": "needs_configuration",
        "deployment_missing": "needs_configuration",
        "deployment_invalid": "unavailable",
        "integrity_mismatch": "unavailable",
        "package_tampered": "unavailable",
        "runtime_missing": "unavailable",
        "platform_unsupported": "unavailable",
    }
    for code, status in expected.items():
        readiness = SidecarReadiness.from_code(code, ("requirement",))
        assert readiness.status == status
        assert readiness.code == code
        assert "requirement" in readiness.to_dict()["missing_requirements"]
    unknown = SidecarReadiness.from_code(
        "C:/private/.env token=secret-value",
        ("secret",),
    )
    assert unknown == SidecarReadiness.from_code("adapter_unavailable")
    unavailable_detail = SidecarReadinessError(
        SidecarReadiness.from_code("runtime_missing", ("runtime",))
    ).detail()
    assert unavailable_detail["code"] == "sidecar_unavailable"
    assert unavailable_detail["sidecar_readiness"]["status"] == "unavailable"
    wire = json.dumps(unknown.to_dict())
    assert "private" not in wire
    assert "secret-value" not in wire


def test_dependency_graph_preflight_and_deterministic_order() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        manifests = [
            make_manifest("conversation"),
            make_manifest("calendar"),
            make_manifest("affection_memory", dependencies=["conversation"]),
            make_manifest(
                "voice",
                dependencies=["conversation"],
                optional_dependencies=["calendar"],
            ),
            make_manifest("alpha"),
            make_manifest("zeta"),
        ]
        for manifest in manifests:
            package = write_package(root / "packages", manifest)
            install(manager, package, manifest["id"])
        for module_id in (
            "conversation",
            "calendar",
            "affection_memory",
            "voice",
            "alpha",
            "zeta",
        ):
            manager.enable(module_id)
        ordered = [
            item["module_id"] for item in manager.enabled_activation_descriptors()
        ]
        assert ordered == [
            "alpha",
            "calendar",
            "conversation",
            "zeta",
            "affection_memory",
            "voice",
        ]
        try:
            manager.uninstall("conversation")
            raise AssertionError("enabled strong dependency was uninstalled")
        except ModuleConflictError:
            pass

        registry = manager.registry.load()
        registry["modules"]["affection_memory"]["manifest"]["dependencies"] = [
            "missing_provider"
        ]
        manager.registry.save(registry)
        try:
            manager.enabled_activation_descriptors()
            raise AssertionError("missing strong dependency passed preflight")
        except ModuleConflictError as exc:
            assert str(exc) == (
                "module dependency missing: affection_memory->missing_provider"
            )

        registry["modules"]["affection_memory"]["manifest"]["dependencies"] = [
            "conversation"
        ]
        registry["modules"]["voice"]["manifest"]["version"] = "9.0.0"
        manager.registry.save(registry)
        try:
            manager.enabled_activation_descriptors()
            raise AssertionError("dependency version mismatch passed preflight")
        except ModuleConflictError as exc:
            assert str(exc) == "module version mismatch: voice"


def test_dependency_cycle_and_atomic_registration_rollback() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        base = write_package(
            root / "packages",
            make_manifest("base"),
            (
                "def register(app):\n"
                "    app.state.events.append('register:base')\n"
                "def unregister(app):\n"
                "    app.state.events.append('unregister:base')\n"
            ),
        )
        failing = write_package(
            root / "packages",
            make_manifest("failing", dependencies=["base"]),
            (
                "def register(app):\n"
                "    app.state.events.append('register:failing')\n"
                "    raise RuntimeError('C:/private token=secret-value')\n"
                "def unregister(app):\n"
                "    app.state.events.append('unregister:failing')\n"
            ),
        )
        install(manager, base, "base")
        install(manager, failing, "failing")
        manager.enable("base")
        manager.enable("failing")
        app = FastAPI()
        app.state.events = []
        coordinator = ModuleActivationCoordinator(
            manager,
            InProcessModuleLoader(),
        )
        results = coordinator.activate(app)
        assert results == [
            {"module_id": "base", "status": "rolled_back"},
            {
                "module_id": "failing",
                "status": "failed",
                "error": "module registration failed",
            },
        ]
        assert app.state.events == [
            "register:base",
            "register:failing",
            "unregister:failing",
            "unregister:base",
        ]
        assert "secret-value" not in json.dumps(results)
        assert not any(
            route.path.startswith("/api/v1/base")
            or route.path.startswith("/api/v1/failing")
            for route in app.routes
        )

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        manager = new_manager(root)
        for module_id in ("cycle_a", "cycle_b"):
            package = write_package(root / "packages", make_manifest(module_id))
            install(manager, package, module_id)
            manager.enable(module_id)
        registry = manager.registry.load()
        registry["modules"]["cycle_a"]["manifest"]["dependencies"] = ["cycle_b"]
        registry["modules"]["cycle_b"]["manifest"]["dependencies"] = ["cycle_a"]
        manager.registry.save(registry)
        try:
            ModuleActivationCoordinator(
                manager,
                InProcessModuleLoader(),
            ).activate(FastAPI())
            raise AssertionError("dependency cycle reached registration")
        except ModuleConflictError as exc:
            assert str(exc) == "module dependency cycle: cycle_a,cycle_b"
        registry = manager.registry.load()
        registry["modules"]["cycle_a"]["manifest"]["dependencies"] = ["cycle_a"]
        registry["modules"]["cycle_b"]["manifest"]["dependencies"] = []
        manager.registry.save(registry)
        try:
            manager.enabled_activation_descriptors()
            raise AssertionError("dependency self-cycle passed preflight")
        except ModuleConflictError as exc:
            assert str(exc) == "module dependency self-cycle: cycle_a"


def test_sidecars_use_topology_and_reverse_shutdown_order() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        events = []
        adapter = OrderedSidecarAdapter(events)
        manager = new_manager(root, {"test_sidecar": adapter})
        base = write_package(
            root / "packages",
            make_manifest("sidecar_base", module_type="sidecar"),
        )
        consumer = write_package(
            root / "packages",
            make_manifest(
                "sidecar_consumer",
                module_type="sidecar",
                dependencies=["sidecar_base"],
            ),
        )
        install(manager, base, "sidecar_base")
        install(manager, consumer, "sidecar_consumer")
        manager.enable("sidecar_base")
        manager.enable("sidecar_consumer")
        events.clear()
        coordinator = ModuleActivationCoordinator(
            manager,
            InProcessModuleLoader(),
        )
        assert coordinator.activate(FastAPI()) == [
            {"module_id": "sidecar_base", "status": "started"},
            {"module_id": "sidecar_consumer", "status": "started"},
        ]
        assert coordinator.deactivate(FastAPI()) == [
            {"module_id": "sidecar_consumer", "status": "stopped"},
            {"module_id": "sidecar_base", "status": "stopped"},
        ]
        assert events == [
            "start:sidecar_base",
            "start:sidecar_consumer",
            "stop:sidecar_consumer",
            "stop:sidecar_base",
        ]


def main() -> int:
    test_schema_and_empty_state()
    test_browser_local_zip_upload_contract()
    test_manifest_network_download_permission_closed_set()
    test_runtime_requirements_are_declarative_and_checked_before_enable()
    test_install_reports_required_module_dependency_readiness()
    test_install_update_rollback_and_data_preservation()
    test_invalid_packages_do_not_reach_runtime()
    test_core_ids_and_namespaces_are_reserved_without_state()
    test_dependency_cycles_and_failed_update_keep_old_version()
    test_in_process_loader_and_sidecar_stop_protocol()
    test_sidecar_readiness_state_machine_and_redaction()
    test_sidecar_adapter_registration_seam()
    test_sidecar_dependency_deployment_descriptor_and_rollback()
    test_sidecar_dependency_descriptor_rejects_unsafe_state()
    test_sidecar_readiness_stable_mapping()
    test_dependency_graph_preflight_and_deterministic_order()
    test_dependency_cycle_and_atomic_registration_rollback()
    test_sidecars_use_topology_and_reverse_shutdown_order()
    print("installable module lifecycle tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
