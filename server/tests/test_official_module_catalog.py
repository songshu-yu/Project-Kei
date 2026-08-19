"""Offline PK-010 official GitHub catalog/download contract tests."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

import _path_setup  # noqa: F401
import httpx
from fastapi import FastAPI

from core.modules.manager import ModuleManager
from core.modules.official_catalog import (
    OFFICIAL_CATALOG_URL,
    OfficialCatalogHTTPClient,
    OfficialCatalogStore,
    validate_official_catalog,
)
from features.module_manager import router as module_router
from features.module_manager.official_service import OfficialModuleService


TRUSTED_ORIGIN = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def manifest(module_id: str, version: str) -> dict:
    return {
        "schema_version": 1,
        "id": module_id,
        "name": f"Test {module_id}",
        "version": version,
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": [f"/api/v1/{module_id.replace('_', '-')}"],
        "legacy_endpoints": [],
        "dashboard_entrypoint": "dashboard/index.js",
        "data_namespace": module_id,
        "config_schema": None,
        "permissions": ["local_state"],
        "requires_restart": True,
    }


def package_bytes(payload: dict, malicious: str | None = None) -> tuple[bytes, bytes]:
    import io

    stream = io.BytesIO()
    manifest_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("backend.py", "def register(app):\n    return None\n")
        archive.writestr("dashboard/index.js", "export function mount() {}\n")
        if malicious == "traversal":
            archive.writestr("../escape.txt", "no")
        elif malicious == "symlink":
            info = zipfile.ZipInfo("dashboard/link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "target")
        elif malicious == "reparse":
            info = zipfile.ZipInfo("dashboard/reparse")
            info.create_system = 0
            info.external_attr = 0x400
            archive.writestr(info, "target")
        elif malicious == "duplicate_manifest":
            archive.writestr("MANIFEST.JSON", manifest_bytes)
    return stream.getvalue(), manifest_bytes


def release(payload: dict, archive: bytes, manifest_bytes: bytes, **overrides) -> dict:
    tag = f"module-{payload['id']}-v{payload['version']}"
    asset = f"{payload['id']}-{payload['version']}.zip"
    item = {
        "module_id": payload["id"],
        "name": payload["name"],
        "version": payload["version"],
        "core_compatibility": payload["core_compatibility"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "package_url": (
            "https://github.com/songshu-yu/Project-Kei-Modules/"
            f"releases/download/{tag}/{asset}"
        ),
        "package_size": len(archive),
        "package_sha256": hashlib.sha256(archive).hexdigest(),
        "release_tag": tag,
        "asset_name": asset,
        "dependencies": payload["dependencies"],
        "optional_dependencies": payload["optional_dependencies"],
        "conflicts": payload["conflicts"],
        "permissions": payload["permissions"],
        "data_policy": "preserve_on_uninstall",
        "requires_restart": payload["requires_restart"],
    }
    item.update(overrides)
    return item


def catalog(items: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "publisher": "Project Kei",
        "owner": "songshu-yu",
        "repository": "Project-Kei-Modules",
        "generated_at": "2026-07-30T00:00:00Z",
        "modules": items,
    }


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def make_service(root: Path, payload: dict, handler) -> tuple[ModuleManager, OfficialModuleService]:
    bundled = root / "bundled.json"
    bundled.write_text(json.dumps(catalog([])), encoding="utf-8")
    store = OfficialCatalogStore(bundled, root / "data" / "official_module_catalog.json")
    store.save(validate_official_catalog(payload))
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    manager = make_manager(root)
    return manager, OfficialModuleService(
        manager,
        store,
        OfficialCatalogHTTPClient(client=client),
    )


async def api_client(manager: ModuleManager, service: OfficialModuleService):
    original_manager = module_router.get_module_manager
    original_official = module_router.get_official_module_service
    module_router.get_module_manager = lambda: manager
    module_router.get_official_module_service = lambda: service
    app = FastAPI()
    app.include_router(module_router.router)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 32100)),
        base_url=TRUSTED_ORIGIN,
        headers={"Origin": TRUSTED_ORIGIN},
    )
    return client, original_manager, original_official


def restore_router(original_manager, original_official) -> None:
    module_router.get_module_manager = original_manager
    module_router.get_official_module_service = original_official


async def test_get_refresh_install_update_rollback_and_uninstall() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        v1_manifest = manifest("official_sample", "1.0.0")
        v2_manifest = manifest("official_sample", "2.0.0")
        v1_zip, v1_raw = package_bytes(v1_manifest)
        v2_zip, v2_raw = package_bytes(v2_manifest)
        releases = [
            release(v1_manifest, v1_zip, v1_raw),
            release(v2_manifest, v2_zip, v2_raw),
        ]
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            if str(request.url) == OFFICIAL_CATALOG_URL:
                return httpx.Response(200, json=catalog(releases))
            for item, body in zip(releases, (v1_zip, v2_zip)):
                if str(request.url) == item["package_url"]:
                    return httpx.Response(
                        302,
                        headers={
                            "Location": (
                                "https://release-assets.githubusercontent.com/"
                                f"project-kei/{item['asset_name']}"
                            )
                        },
                    )
                if str(request.url).endswith(item["asset_name"]):
                    return httpx.Response(
                        200,
                        content=body,
                        headers={"Content-Length": str(len(body))},
                    )
            return httpx.Response(404)

        manager, service = make_service(root, catalog(releases), handler)
        client, original_manager, original_official = await api_client(manager, service)
        try:
            before = await client.get("/api/v1/modules/official-catalog")
            assert before.status_code == 200
            assert requests == []
            assert before.json()["network_accessed"] is False
            assert before.json()["modules"][0]["available_actions"] == ["install_official"]

            refreshed = await client.post("/api/v1/modules/official-catalog/refresh")
            assert refreshed.status_code == 200
            assert refreshed.json()["refresh_status"] == "success"
            assert requests == [OFFICIAL_CATALOG_URL]

            install_body = {"version": "1.0.0", "confirmation": "official_sample@1.0.0"}
            first, second = await asyncio.gather(
                client.post("/api/v1/modules/official_sample/install-official", json=install_body),
                client.post("/api/v1/modules/official_sample/install-official", json=install_body),
            )
            assert sorted((first.status_code, second.status_code)) == [200, 409]
            installed = first.json() if first.status_code == 200 else second.json()
            assert installed["package_source"] == "official_github_release"
            assert installed["official_operation"]["received_bytes"] == len(v1_zip)
            assert "enable" in installed["available_actions"]
            assert set(manager.snapshot()) == {"official_sample"}

            enabled = manager.enable("official_sample")
            assert enabled["restart_required"] is True
            updated = await client.post(
                "/api/v1/modules/official_sample/update-official",
                json={"version": "2.0.0", "confirmation": "official_sample@2.0.0"},
            )
            assert updated.status_code == 200
            assert updated.json()["installed_version"] == "2.0.0"
            assert "rollback_official" in updated.json()["available_actions"]

            rolled_back = await client.post(
                "/api/v1/modules/official_sample/rollback-official",
                json={"version": "1.0.0", "confirmation": "official_sample@1.0.0"},
            )
            assert rolled_back.status_code == 200
            assert rolled_back.json()["installed_version"] == "1.0.0"

            removed = await client.delete("/api/v1/modules/official_sample")
            assert removed.status_code == 200
            assert removed.json()["data_preserved"] is True
            assert removed.json()["restart_required"] is True
            assert not (root / "data" / "module_registry.json").read_text(encoding="utf-8").find(
                "official_sample"
            ) >= 0
        finally:
            await client.aclose()
            restore_router(original_manager, original_official)


async def test_fail_closed_downloads_and_cache_fallback() -> None:
    cases = ("redirect", "digest", "truncated", "oversize", "manifest", "traversal", "symlink", "reparse", "duplicate_manifest")
    for case in cases:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = manifest(f"bad_{case}", "1.0.0")
            archive, raw = package_bytes(
                payload,
                malicious=case if case in {"traversal", "symlink", "reparse", "duplicate_manifest"} else None,
            )
            overrides = {}
            if case == "digest":
                overrides["package_sha256"] = "0" * 64
            elif case == "truncated":
                overrides["package_size"] = len(archive) + 1
            elif case == "oversize":
                overrides["package_size"] = len(archive) - 1
            elif case == "manifest":
                overrides["name"] = "Different catalog name"
            item = release(payload, archive, raw, **overrides)

            def handler(request: httpx.Request) -> httpx.Response:
                if case == "redirect":
                    return httpx.Response(302, headers={"Location": "https://evil.example/module.zip"})
                return httpx.Response(200, content=archive)

            manager, service = make_service(root, catalog([item]), handler)
            client, original_manager, original_official = await api_client(manager, service)
            try:
                response = await client.post(
                    f"/api/v1/modules/{payload['id']}/install-official",
                    json={"version": "1.0.0", "confirmation": f"{payload['id']}@1.0.0"},
                )
                assert response.status_code == 422, (case, response.text)
                detail = response.json()["detail"]
                assert isinstance(detail, dict) and detail["code"].startswith("official_")
                assert set(detail) == {
                    "code", "message", "stage", "retryable",
                    "received_bytes", "retry_after",
                }
                assert manager.snapshot() == {}
                assert not (root / "data" / "module_registry.json").exists()
                assert not (root / "runtime" / "modules" / payload["id"]).exists()
                assert not (root / "data" / "modules").exists()
            finally:
                await client.aclose()
                restore_router(original_manager, original_official)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        payload = manifest("cached", "1.0.0")
        archive, raw = package_bytes(payload)
        item = release(payload, archive, raw)

        def offline(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        manager, service = make_service(root, catalog([item]), offline)
        cache = root / "data" / "official_module_catalog.json"
        before = cache.read_bytes()
        client, original_manager, original_official = await api_client(manager, service)
        try:
            failed = await client.post("/api/v1/modules/official-catalog/refresh")
            assert failed.status_code == 502
            assert failed.json()["detail"]["code"] == "official_catalog_refresh_failed"
            assert cache.read_bytes() == before
            cache.write_text("{broken", encoding="utf-8")
            fallback = await client.get("/api/v1/modules/official-catalog")
            assert fallback.status_code == 200
            assert fallback.json()["cache_source"] == "last_good_cache"
            assert fallback.json()["modules"][0]["module_id"] == "cached"
        finally:
            await client.aclose()
            restore_router(original_manager, original_official)


async def test_origin_confirmation_and_catalog_source_guards() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        payload = manifest("guarded", "1.0.0")
        archive, raw = package_bytes(payload)
        item = release(payload, archive, raw)
        manager, service = make_service(
            root,
            catalog([item]),
            lambda request: httpx.Response(200, content=archive),
        )
        client, original_manager, original_official = await api_client(manager, service)
        try:
            denied = await client.post(
                "/api/v1/modules/guarded/install-official",
                json={"version": "1.0.0", "confirmation": "wrong"},
            )
            assert denied.status_code == 409
            assert denied.json()["detail"]["code"] == "official_module_confirmation_required"
            cross_site = await client.post(
                "/api/v1/modules/official-catalog/refresh",
                headers={"Origin": "https://evil.example"},
            )
            assert cross_site.status_code == 403
        finally:
            await client.aclose()
            restore_router(original_manager, original_official)

        untrusted = release(payload, archive, raw, package_url="https://example.com/module.zip")
        try:
            validate_official_catalog(catalog([untrusted]))
            raise AssertionError("arbitrary package URL should be rejected")
        except Exception as exc:
            assert getattr(exc, "code", "") == "official_catalog_source_untrusted"


def test_catalog_builder_determinism() -> None:
    spec = importlib.util.spec_from_file_location(
        "build_official_module_catalog_test",
        PROJECT_ROOT / "scripts" / "build_official_module_catalog.py",
    )
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        payload = manifest("focus", "1.1.0")
        archive, _ = package_bytes(payload)
        asset_name = "focus-1.1.0.zip"
        (root / asset_name).write_bytes(archive)
        fragment = {
            "schema_version": 1,
            "module_id": "focus",
            "name": payload["name"],
            "version": "1.1.0",
            "core_compatibility": payload["core_compatibility"],
            "release_tag": "module-focus-v1.1.0",
            "asset_name": asset_name,
            "dependencies": [],
            "optional_dependencies": [],
            "conflicts": [],
            "permissions": ["local_state"],
            "data_policy": "preserve_on_uninstall",
            "requires_restart": True,
        }
        fragment_path = root / "focus-release.json"
        fragment_path.write_text(json.dumps(fragment), encoding="utf-8")
        first = builder.build_catalog(
            [fragment_path],
            root,
            "2026-07-30T00:00:00Z",
        )
        second = builder.build_catalog(
            [fragment_path],
            root,
            "2026-07-30T00:00:00Z",
        )
        assert first == second
        assert first["modules"][0]["module_id"] == "focus"
        assert first["modules"][0]["package_sha256"] == hashlib.sha256(archive).hexdigest()
        assert "runtime_requirements" not in first["modules"][0]
        legacy_module = validate_official_catalog(first).to_dict()["modules"][0]
        assert "runtime_requirements" not in legacy_module

        runtime_payload = manifest("qq_bridge", "0.1.7")
        runtime_payload["runtime_requirements"] = [{
            "id": "node",
            "supported_major_versions": [20, 22, 24, 26],
            "architecture": "x64",
        }]
        runtime_archive, _ = package_bytes(runtime_payload)
        runtime_asset_name = "qq_bridge-0.1.7.zip"
        (root / runtime_asset_name).write_bytes(runtime_archive)
        runtime_fragment = {
            "schema_version": 1,
            "module_id": "qq_bridge",
            "name": runtime_payload["name"],
            "version": runtime_payload["version"],
            "core_compatibility": runtime_payload["core_compatibility"],
            "release_tag": "module-qq_bridge-v0.1.7",
            "asset_name": runtime_asset_name,
            "dependencies": [],
            "optional_dependencies": [],
            "runtime_requirements": runtime_payload["runtime_requirements"],
            "conflicts": [],
            "permissions": ["local_state"],
            "data_policy": "preserve_on_uninstall",
            "requires_restart": True,
        }
        runtime_fragment_path = root / "qq-bridge-release.json"
        runtime_fragment_path.write_text(json.dumps(runtime_fragment), encoding="utf-8")
        runtime_catalog = builder.build_catalog(
            [runtime_fragment_path],
            root,
            "2026-07-30T00:00:00Z",
        )
        assert (
            runtime_catalog["modules"][0]["runtime_requirements"]
            == runtime_payload["runtime_requirements"]
        )
        validated_runtime_module = validate_official_catalog(runtime_catalog).to_dict()[
            "modules"
        ][0]
        assert (
            validated_runtime_module["runtime_requirements"]
            == runtime_payload["runtime_requirements"]
        )
        try:
            builder.build_catalog(
                [fragment_path, fragment_path],
                root,
                "2026-07-30T00:00:00Z",
            )
            raise AssertionError("duplicate release fragment should fail")
        except ValueError:
            pass


def main() -> int:
    asyncio.run(test_get_refresh_install_update_rollback_and_uninstall())
    asyncio.run(test_fail_closed_downloads_and_cache_fallback())
    asyncio.run(test_origin_confirmation_and_catalog_source_guards())
    test_catalog_builder_determinism()
    print("official module catalog tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
