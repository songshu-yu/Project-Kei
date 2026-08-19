"""Isolated checks for the installable affection_memory package."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

os.environ["PROJECT_KEI_ENV_FILE"] = str(
    Path(tempfile.gettempdir())
    / "project-kei-pk160-installable-tests"
    / "missing.env"
)

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from features.affection_memory import repository as repository_module
from features.affection_memory.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_affection_memory_package,
    file_sha256,
)
from features.affection_memory.module import register as register_affection_memory
from features.affection_memory.repository import (
    MemoryPersistenceError,
    MemoryRepository,
    RelationshipRepository,
)
from features.affection_memory.router import create_affection_memory_router
from features.affection_memory.service import MemoryService, RelationshipService
from features.conversation import (
    ConversationContextProvider,
    EmptyConversationContextProvider,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "affection_memory"
RELEASE_ROOT = FEATURE_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
CATALOG_GENERATED_AT = "2026-07-30T00:00:00Z"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43160))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:8000"
    ) as client:
        return await client.request(method, path, **kwargs)


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def write_conversation_contract_package(root: Path) -> Path:
    package = root / "conversation-contract"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "conversation",
        "name": "conversation contract fixture",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": ["/api/v1/conversation-contract-fixture"],
        "legacy_endpoints": [],
        "data_namespace": "conversation",
        "permissions": [],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (package / "backend" / "__init__.py").write_text(
        "class DynamicProvider:\n"
        "    def __init__(self, app):\n"
        "        self.app = app\n"
        "    def get_context(self):\n"
        "        provider = getattr(self.app.state, 'conversation_context_provider', None)\n"
        "        if provider is None or not callable(getattr(provider, 'get_context', None)):\n"
        "            return ''\n"
        "        return provider.get_context()\n"
        "\n"
        "def register(app):\n"
        "    app.state.conversation_contract_provider = DynamicProvider(app)\n",
        encoding="utf-8",
    )
    return package


def restarted_app(
    manager: ModuleManager,
    relationship_path: Path,
    memory_path: Path,
) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.affection_memory_relationship_path = relationship_path
    app.state.affection_memory_memory_path = memory_path
    results = InProcessModuleLoader().load(
        app, manager.enabled_in_process_descriptors()
    )
    manager.record_load_results(results)
    return app, results


def _assert_package_contents(package: Path) -> None:
    forbidden_names = (
        ".env",
        "affection_state",
        "memories.json",
        "profile",
        "cache",
        "vendor",
        "install.ps",
        "install.sh",
        "registry",
        "test",
        "fixture",
    )
    with zipfile.ZipFile(package) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = sorted(info.filename for info in infos)
        assert names == sorted(EXPECTED_PACKAGE_NAMES)
        assert len(names) == len(set(name.casefold() for name in names))
        combined = []
        for info in infos:
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.create_system == 3
            assert info.create_version == 20
            assert info.extract_version == 20
            assert info.internal_attr == 0
            assert info.external_attr == 0o100644 << 16
            assert info.extra == b""
            assert info.comment == b""
            assert "\\" not in info.filename
            assert ".." not in Path(info.filename).parts
            combined.append(archive.read(info).decode("utf-8"))
    package_text = "\n".join(combined)
    assert "\r\n" not in package_text
    assert not re.search(
        r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", package_text
    )
    assert "from features.conversation.context import" not in package_text
    assert "from features.conversation.runtime import" not in package_text
    assert not any(
        token in name.casefold()
        for name in names
        for token in forbidden_names
    )


def check_deterministic_package_and_release_metadata() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "affection_memory"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["dependencies"] == ["conversation"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    with tempfile.TemporaryDirectory(
        prefix="kei-affection-memory-build-"
    ) as temp_dir:
        root = Path(temp_dir)
        first = build_affection_memory_package(root / "first.zip")
        second = build_affection_memory_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)
        with zipfile.ZipFile(first) as archive:
            manifest_raw = archive.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
        assert manifest["dependencies"] == ["conversation"]
        assert entry["module_id"] == "affection_memory"
        assert entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        assert entry["package_sha256"] == file_sha256(first)
        assert entry["package_size"] == first.stat().st_size
        asset_root = root / "assets"
        asset_root.mkdir()
        official = build_affection_memory_package(
            asset_root / OFFICIAL_ASSET_NAME
        )
        output = root / "official-catalog.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(CATALOG_BUILDER),
                "--fragment",
                str(RELEASE_FRAGMENT),
                "--asset-root",
                str(asset_root),
                "--output",
                str(output),
                "--generated-at",
                CATALOG_GENERATED_AT,
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        catalog = json.loads(output.read_text(encoding="utf-8"))
        assert catalog["modules"] == [entry]
        assert file_sha256(official) == file_sha256(first)


def check_dashboard_entrypoint_uses_scoped_request() -> None:
    entrypoint = (
        FEATURE_ROOT / "package_source" / "dashboard" / "index.js"
    )
    source = entrypoint.read_text(encoding="utf-8")
    assert "context.request(" in source
    assert "fetch(" not in source
    assert "缺少受限挂载上下文" in source
    assert "好感度系统" in source
    assert "长期记忆" in source
    assert "module-owned-panels" in source
    assert 'relationshipPanel.dataset.panelId = "module-affection"' in source
    assert 'memoryPanel.dataset.panelId = "module-long-term-memory"' in source
    assert 'default-avatars/affection.png' in source
    assert 'default-avatars/memory.png' in source
    assert 'element("details"' not in source
    subprocess.run(
        ["node", "--check", str(entrypoint)],
        check=True,
        capture_output=True,
        text=True,
    )


def check_empty_provider_without_module() -> None:
    app = FastAPI()
    provider = getattr(
        app.state,
        "affection_memory_context_provider",
        EmptyConversationContextProvider(),
    )
    assert isinstance(provider, ConversationContextProvider)
    assert provider.get_context() == ""
    assert not hasattr(app.state, "affection_memory_module_registered")


def check_production_read_write_guard_split() -> None:
    composition_source = (
        PROJECT_ROOT / "server" / "module_composition.py"
    ).read_text(encoding="utf-8")
    assert (
        "app.state.affection_memory_local_read_guard = self.local_read_guard"
        in composition_source
    )
    assert (
        "app.state.affection_memory_local_control_guard = self.local_write_guard"
        in composition_source
    )

    with tempfile.TemporaryDirectory(
        prefix="kei-affection-memory-guards-"
    ) as temp_dir:
        root = Path(temp_dir)
        app = FastAPI()

        def local_read(request) -> bool:
            return request.client is not None and request.client.host == "127.0.0.1"

        def local_write(request) -> bool:
            return (
                local_read(request)
                and request.headers.get("origin") == "http://127.0.0.1:8000"
            )

        app.include_router(create_affection_memory_router(
            RelationshipService(RelationshipRepository(root / "relationship.json")),
            MemoryService(MemoryRepository(root / "memories.json")),
            local_read_guard=local_read,
            local_control_guard=local_write,
        ))
        relationship = asyncio.run(
            call(app, "GET", "/api/v1/relationship/status")
        )
        memories = asyncio.run(call(app, "GET", "/api/v1/memories"))
        denied_write = asyncio.run(call(
            app,
            "POST",
            "/api/v1/memories",
            json={"content": "temporary guard fixture", "source": "api"},
        ))
        allowed_write = asyncio.run(call(
            app,
            "POST",
            "/api/v1/memories",
            headers={"Origin": "http://127.0.0.1:8000"},
            json={"content": "temporary guard fixture", "source": "api"},
        ))
        assert relationship.status_code == 200
        assert memories.status_code == 200
        assert denied_write.status_code == 403
        assert allowed_write.status_code == 200


def check_lifecycle_provider_and_data_isolation() -> None:
    marker = "fictional-installable-memory-marker"
    with tempfile.TemporaryDirectory(
        prefix="kei-affection-memory-lifecycle-"
    ) as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        conversation = write_conversation_contract_package(root)
        manager.install(
            conversation,
            manager.calculate_package_sha256(conversation),
            expected_module_id="conversation",
        )
        manager.enable("conversation")
        package = build_affection_memory_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)
        installed = manager.install(
            package, digest, expected_module_id="affection_memory"
        )
        assert installed["install_status"] == "installed_disabled"
        manager.enable("affection_memory")

        relationship_path = root / "historical" / "affection_state.json"
        memory_path = root / "historical" / "memories.json"
        app, results = restarted_app(manager, relationship_path, memory_path)
        assert results == [
            {"module_id": "conversation", "status": "loaded"},
            {"module_id": "affection_memory", "status": "loaded"},
        ]
        provider = app.state.affection_memory_context_provider
        assert isinstance(provider, ConversationContextProvider)
        assert app.state.conversation_context_provider is provider
        assert (
            app.state.conversation_contract_provider.get_context()
            == provider.get_context()
        )
        assert set(name for name in dir(provider) if not name.startswith("_")) == {
            "get_context"
        }

        route_paths = [str(getattr(route, "path", "")) for route in app.routes]
        route_keys = [
            (method, str(getattr(route, "path", "")))
            for route in app.routes
            for method in (getattr(route, "methods", None) or ())
        ]
        assert len(route_keys) == len(set(route_keys))
        assert {
            ("GET", "/api/v1/relationship/status"),
            ("POST", "/api/v1/relationship/events"),
            ("POST", "/api/v1/relationship/choices"),
            ("GET", "/api/v1/memories"),
            ("POST", "/api/v1/memories"),
            ("DELETE", "/api/v1/memories/{memory_id}"),
            ("GET", "/affection/status"),
            ("POST", "/affection/event"),
            ("POST", "/affection/choose"),
            ("POST", "/affection/reset"),
            ("GET", "/memories"),
            ("POST", "/memories"),
            ("DELETE", "/memories/{memory_id}"),
            ("POST", "/memories/clear"),
        } <= set(route_keys)

        initial = asyncio.run(
            call(app, "GET", "/api/v1/relationship/status")
        ).json()
        event = asyncio.run(
            call(
                app,
                "POST",
                "/api/v1/relationship/events",
                json={"force_event": "morning_ping"},
            )
        ).json()
        choice_id = event["event"]["choices"][0]["id"]
        resolved = asyncio.run(
            call(
                app,
                "POST",
                "/api/v1/relationship/choices",
                json={"choice_id": choice_id, "with_audio": False},
            )
        ).json()
        duplicate = asyncio.run(
            call(
                app,
                "POST",
                "/affection/choose",
                json={"choice_id": choice_id, "with_audio": False},
            )
        ).json()
        assert resolved["status"] == "resolved"
        assert duplicate["status"] == "idle"
        assert resolved["stats"]["affection"] == (
            initial["affection"] + resolved["effects"].get("affection", 0)
        )

        added = asyncio.run(
            call(
                app,
                "POST",
                "/api/v1/memories",
                json={
                    "content": marker,
                    "tags": ["fixture"],
                    "source": "api",
                    "request_id": "installable-lifecycle",
                },
            )
        )
        assert added.status_code == 200 and added.json()["created"] is True
        asyncio.run(call(app, "POST", "/affection/reset"))
        after_relationship_reset = asyncio.run(
            call(app, "GET", "/api/v1/memories")
        ).json()
        assert after_relationship_reset["count"] == 1
        reset_relationship = asyncio.run(
            call(app, "GET", "/api/v1/relationship/status")
        ).json()
        asyncio.run(call(app, "POST", "/memories/clear"))
        after_memory_clear = asyncio.run(
            call(app, "GET", "/api/v1/relationship/status")
        ).json()
        assert after_memory_clear == reset_relationship

        asyncio.run(
            call(
                app,
                "POST",
                "/memories",
                json={
                    "content": marker,
                    "tags": ["fixture"],
                    "source": "api",
                    "request_id": "installable-reinstall",
                },
            )
        )
        assert marker in provider.get_context()

        # register() is idempotent for its own app and cannot create duplicate
        # routes. A foreign pre-existing route is rejected instead.
        module_suffix = "module_affection_memory_" + OFFICIAL_RELEASE_VERSION.replace(".", "_")
        loaded_module = next(
            module
            for name, module in tuple(__import__("sys").modules.items())
            if name.endswith(module_suffix)
        )
        loaded_module.register(app)
        assert route_paths == [
            str(getattr(route, "path", "")) for route in app.routes
        ]
        foreign_app = FastAPI()
        foreign_app.state.affection_memory_relationship_path = (
            root / "foreign" / "affection.json"
        )
        foreign_app.state.affection_memory_memory_path = (
            root / "foreign" / "memories.json"
        )

        @foreign_app.get("/api/v1/relationship/status")
        async def foreign_status() -> dict:
            return {"foreign": True}

        try:
            loaded_module.register(foreign_app)
        except RuntimeError as exc:
            assert "routes already registered" in str(exc)
        else:
            raise AssertionError("foreign duplicate relationship route was accepted")
        assert not hasattr(
            foreign_app.state, "affection_memory_context_provider"
        )

        manager.disable("affection_memory")
        disabled_app, disabled_results = restarted_app(
            manager, relationship_path, memory_path
        )
        assert disabled_results == [
            {"module_id": "conversation", "status": "loaded"}
        ]
        assert not hasattr(
            disabled_app.state, "affection_memory_context_provider"
        )
        assert not hasattr(disabled_app.state, "conversation_context_provider")
        assert (
            disabled_app.state.conversation_contract_provider.get_context()
            == ""
        )
        assert (
            asyncio.run(
                call(disabled_app, "GET", "/api/v1/relationship/status")
            ).status_code
            == 404
        )

        manager.uninstall("affection_memory")
        assert relationship_path.is_file()
        assert memory_path.is_file()
        uninstalled_app, uninstalled_results = restarted_app(
            manager, relationship_path, memory_path
        )
        assert uninstalled_results == [
            {"module_id": "conversation", "status": "loaded"}
        ]
        assert not hasattr(
            uninstalled_app.state, "affection_memory_context_provider"
        )
        assert not hasattr(
            uninstalled_app.state, "conversation_context_provider"
        )

        manager.install(package, digest, expected_module_id="affection_memory")
        manager.enable("affection_memory")
        reinstalled_app, reinstalled_results = restarted_app(
            manager, relationship_path, memory_path
        )
        assert {
            "module_id": "affection_memory",
            "status": "loaded",
        } in reinstalled_results
        assert (
            marker
            in reinstalled_app.state.affection_memory_context_provider.get_context()
        )

        module_data = manager.data_root / "affection_memory"
        module_data.mkdir(parents=True)
        (module_data / "isolated-module-data.txt").write_text(
            "purge fixture", encoding="utf-8"
        )
        manager.disable("affection_memory")
        purged = manager.purge_data("affection_memory", "affection_memory")
        assert purged["purged"] is True
        assert not module_data.exists()
        assert relationship_path.is_file()
        assert memory_path.is_file()
        manager.uninstall("affection_memory")


def check_atomic_failure_and_error_leak_boundary() -> None:
    marker = "fictional-private-error-marker"
    with tempfile.TemporaryDirectory(
        prefix="kei-affection-memory-atomic-"
    ) as temp_dir:
        root = Path(temp_dir)
        path = root / "memories.json"
        path.write_text(
            json.dumps(
                {
                    "memories": [
                        {
                            "id": "stable",
                            "content": marker,
                            "tags": ["fixture"],
                            "source": "api",
                            "created_at": "2030-01-01T00:00:00",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        old_bytes = path.read_bytes()
        service = MemoryService(
            MemoryRepository(path), id_factory=lambda: "replacement"
        )
        with patch.object(
            repository_module.os,
            "replace",
            side_effect=OSError("fictional atomic failure"),
        ):
            try:
                service.add(
                    "replacement fixture",
                    source="api",
                    request_id="atomic-failure",
                )
            except MemoryPersistenceError as exc:
                assert marker not in str(exc)
                assert str(path) not in str(exc)
            else:
                raise AssertionError("atomic replace failure was accepted")
        assert path.read_bytes() == old_bytes
        assert not list(root.glob(".memories.json.*.tmp"))

        corrupt_path = root / "corrupt-memories.json"
        corrupt_path.write_text(
            '{"memories":[{"content":"' + marker + '"}',
            encoding="utf-8",
        )
        app = FastAPI()
        app.state.affection_memory_relationship_path = (
            root / "relationship.json"
        )
        app.state.affection_memory_memory_path = corrupt_path
        register_affection_memory(app)
        response = asyncio.run(call(app, "GET", "/api/v1/memories"))
        assert response.status_code == 500
        assert marker not in response.text
        assert str(corrupt_path) not in response.text


def main() -> int:
    check_deterministic_package_and_release_metadata()
    check_dashboard_entrypoint_uses_scoped_request()
    check_empty_provider_without_module()
    check_production_read_write_guard_split()
    check_lifecycle_provider_and_data_isolation()
    check_atomic_failure_and_error_leak_boundary()
    print("affection_memory installable tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
