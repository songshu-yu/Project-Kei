"""Production assembly regression for a clean Core and one installed module."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.modules import InProcessModuleLoader, ModuleManager  # noqa: E402
import features.module_manager.service as module_service  # noqa: E402
from features.voice.providers.gpt_sovits import (  # noqa: E402
    ADAPTER_NAME as GPT_SOVITS_ADAPTER_NAME,
)
from module_composition import InstalledModuleHost  # noqa: E402
from qq_bridge.module_adapter import (  # noqa: E402
    ADAPTER_NAME as QQ_BRIDGE_ADAPTER_NAME,
)


BACKEND = """
from fastapi import APIRouter
from starlette.middleware.base import BaseHTTPMiddleware

class SyntheticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["x-synthetic-module"] = "loaded"
        return response

def register(app):
    app.add_middleware(SyntheticMiddleware)
    router = APIRouter()
    @router.get("/api/v1/synthetic-module")
    async def status():
        return {"status": "loaded"}
    app.include_router(router)
    app.state.synthetic_module_registered = True

async def unregister(app):
    app.state.synthetic_module_closed = True
    if hasattr(app.state, "synthetic_module_registered"):
        delattr(app.state, "synthetic_module_registered")
"""


def _package(root: Path) -> Path:
    package = root / "synthetic-module"
    package.mkdir()
    manifest = {
        "schema_version": 1,
        "id": "synthetic_module",
        "name": "Synthetic Module",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": ["/api/v1/synthetic-module"],
        "legacy_endpoints": [],
        "dashboard_entrypoint": None,
        "data_namespace": "synthetic_module",
        "config_schema": None,
        "permissions": [],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (package / "backend.py").write_text(BACKEND, encoding="utf-8")
    return package


def _fresh_api(manager: ModuleManager, temp_root: Path):
    module_service._MANAGER = manager
    module_service._LOADER = InProcessModuleLoader()
    sys.modules.pop("api", None)
    with patch.dict(
        os.environ,
        {"PROJECT_KEI_ENV_FILE": str(temp_root / "absent.env")},
        clear=False,
    ):
        return importlib.import_module("api")


class ConflictingSidecarAdapter:
    def start(self, manifest, package_root):
        del manifest, package_root

    def stop(self, manifest, package_root):
        del manifest, package_root

    def is_healthy(self, manifest, package_root):
        del manifest, package_root
        return True


def _host(manager: ModuleManager, root: Path) -> InstalledModuleHost:
    with patch("module_composition.get_module_manager", return_value=manager):
        return InstalledModuleHost(
            root,
            local_read_guard=lambda request: None,
            local_write_guard=lambda request: None,
        )


def check_repeated_host_construction_is_idempotent_but_conflicts_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-module-host-repeat-") as temp_dir:
        root = Path(temp_dir)
        manager = ModuleManager(
            runtime_root=root / "runtime" / "modules",
            registry_path=root / "data" / "module_registry.json",
            data_root=root / "data" / "modules",
        )
        first = _host(manager, root)
        second = _host(manager, root)
        assert second.gpt_sovits_adapter is first.gpt_sovits_adapter
        assert second.qq_adapter is first.qq_adapter
        assert first.qq_adapter.data_root.resolve() == (root / "qq_bridge" / "data").resolve()

        different_root = root / "different-root"
        try:
            _host(manager, different_root)
        except ValueError as exc:
            assert "different production root" in str(exc)
        else:
            raise AssertionError("production composition reused QQ paths across roots")

        class State:
            pass

        class App:
            state = State()

        app = App()
        first.configure_app_state(app)
        assert app.state.voice_utterance_encoder is first.voice_utterance_encoder
        assert app.state.qq_media_upload_capability_provider() == "unknown"
        assert first.qq_configuration_store is not None
        assert first.qq_adapter.configuration_path.resolve() == (
            root / "qq_bridge" / ".env"
        ).resolve()
        first.qq_adapter.configuration_path.parent.mkdir(parents=True, exist_ok=True)
        first.qq_adapter.configuration_path.write_text(
            "QQBOT_APPID=TEST_APP\n"
            "QQBOT_SECRET=TEST_SECRET\n"
            "QQBOT_REPLY_WITH_VOICE=false\n"
            "QQBOT_MEDIA_UPLOAD_CAPABILITY=available\n",
            encoding="utf-8",
        )
        assert app.state.qq_media_upload_capability_provider() == "available"
        assert asyncio.run(first._voice_health_snapshot(app)) is None
        assert asyncio.run(first._qq_media_capability_snapshot(app)) == "available"

        class FakeVoiceService:
            async def health(self):
                return {"synthesis_profiles": {"qq_c2c_voice_v1": {"available": True}}}

        app.state.voice_service = FakeVoiceService()
        assert asyncio.run(first._voice_health_snapshot(app)) == {
            "synthesis_profiles": {"qq_c2c_voice_v1": {"available": True}}
        }
        app.state.qq_media_upload_capability_provider = lambda: "AVAILABLE"
        assert asyncio.run(first._qq_media_capability_snapshot(app)) == "available"
        app.state.qq_media_upload_capability_provider = lambda: "invalid"
        assert asyncio.run(first._qq_media_capability_snapshot(app)) == "unknown"
        # Python 3.8's asyncio primitives still consult the current loop during
        # construction; asyncio.run() intentionally clears it on return.
        asyncio.set_event_loop(asyncio.new_event_loop())

        try:
            manager.register_sidecar_adapter(
                GPT_SOVITS_ADAPTER_NAME,
                first.gpt_sovits_adapter,
            )
        except ValueError as exc:
            assert "already registered" in str(exc)
        else:
            raise AssertionError("Core registry silently accepted a duplicate adapter")

        conflict_root = root / "conflict"
        conflict_manager = ModuleManager(
            runtime_root=conflict_root / "runtime" / "modules",
            registry_path=conflict_root / "data" / "module_registry.json",
            data_root=conflict_root / "data" / "modules",
        )
        conflicting = ConflictingSidecarAdapter()
        conflict_manager.register_sidecar_adapter(
            GPT_SOVITS_ADAPTER_NAME,
            conflicting,
        )
        try:
            _host(conflict_manager, conflict_root)
        except ValueError as exc:
            assert "different implementation" in str(exc)
        else:
            raise AssertionError("production composition reused a conflicting adapter")
        assert (
            conflict_manager.resolve_sidecar_adapter(GPT_SOVITS_ADAPTER_NAME)
            is conflicting
        )

        qq_conflict_root = root / "qq-conflict"
        qq_conflict_manager = ModuleManager(
            runtime_root=qq_conflict_root / "runtime" / "modules",
            registry_path=qq_conflict_root / "data" / "module_registry.json",
            data_root=qq_conflict_root / "data" / "modules",
        )
        qq_conflict_manager.register_sidecar_adapter(
            GPT_SOVITS_ADAPTER_NAME,
            first.gpt_sovits_adapter,
        )
        qq_conflicting = ConflictingSidecarAdapter()
        qq_conflict_manager.register_sidecar_adapter(
            QQ_BRIDGE_ADAPTER_NAME,
            qq_conflicting,
        )
        try:
            _host(qq_conflict_manager, qq_conflict_root)
        except ValueError as exc:
            assert "different implementation" in str(exc)
        else:
            raise AssertionError("production composition reused a conflicting QQ adapter")
        assert (
            qq_conflict_manager.resolve_sidecar_adapter(QQ_BRIDGE_ADAPTER_NAME)
            is qq_conflicting
        )


def check_clean_core_and_restart_scoped_module_assembly() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-module-host-") as temp_dir:
        root = Path(temp_dir)
        manager = ModuleManager(
            runtime_root=root / "runtime" / "modules",
            registry_path=root / "data" / "module_registry.json",
            data_root=root / "data" / "modules",
        )
        package = _package(root)
        digest = manager.calculate_package_sha256(package)
        manager.install(package, digest, expected_module_id="synthetic_module")
        manager.enable("synthetic_module")

        api = _fresh_api(manager, root)
        with patch.dict(
            os.environ,
            {"PROJECT_KEI_ENV_FILE": str(root / "absent.env")},
            clear=False,
        ):
            api = importlib.reload(api)
        assert (
            api.MODULE_HOST.gpt_sovits_adapter
            is manager.resolve_sidecar_adapter(GPT_SOVITS_ADAPTER_NAME)
        )
        assert (
            api.MODULE_HOST.qq_adapter
            is manager.resolve_sidecar_adapter(QQ_BRIDGE_ADAPTER_NAME)
        )
        before = {route.path for route in api.app.routes}
        assert "/api/v1/synthetic-module" not in before
        with TestClient(api.app):
            during = {route.path for route in api.app.routes}
            assert "/api/v1/synthetic-module" in during
            assert api.app.state.synthetic_module_registered is True
            assert any(
                item.cls.__name__ == "SyntheticMiddleware"
                for item in api.app.user_middleware
            )
        assert api.app.state.synthetic_module_closed is True
        assert "/api/v1/synthetic-module" not in {
            route.path for route in api.app.routes
        }

        manager.disable("synthetic_module")
        manager = ModuleManager(
            runtime_root=root / "runtime" / "modules",
            registry_path=root / "data" / "module_registry.json",
            data_root=root / "data" / "modules",
        )
        api = _fresh_api(manager, root)
        with TestClient(api.app):
            assert "/api/v1/synthetic-module" not in {
                route.path for route in api.app.routes
            }
        sys.modules.pop("api", None)


def main() -> int:
    check_repeated_host_construction_is_idempotent_but_conflicts_fail_closed()
    check_clean_core_and_restart_scoped_module_assembly()
    print("module host assembly tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
