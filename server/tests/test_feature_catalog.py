"""Contract checks for the project-local module and task catalog."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["PROJECT_KEI_ENV_FILE"] = str(Path(tempfile.gettempdir()) / "project-kei-pk160-tests" / "missing.env")

import _path_setup  # noqa: E402,F401

from core.local_access import LoopbackAccessMiddleware
from core.modules import CORE_MODULE_CONTRACTS, ModuleManager
from features.catalog.models import ModuleCatalogResponse
from features.catalog.service import get_module_catalog
from features.module_manager import service as module_manager_service
from features.voice.voice_packs.security import VoicePackOriginGuardMiddleware
from features.affection_memory.security import AffectionMemoryOriginGuardMiddleware
from features.fitness.security import FitnessOriginGuardMiddleware
from features.qq_control import QQControlOriginGuardMiddleware


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def validate_response(payload: dict) -> ModuleCatalogResponse:
    if hasattr(ModuleCatalogResponse, "model_validate"):
        return ModuleCatalogResponse.model_validate(payload)
    return ModuleCatalogResponse.parse_obj(payload)


def main() -> int:
    malicious_snapshot = {
        module_id: {
            "module_id": module_id,
            "managed": True,
            "source": "local_package",
            "required": False,
            "install_status": "enabled",
            "enabled": True,
            "api_namespaces": ["/api/v1/attacker"],
        }
        for module_id in CORE_MODULE_CONTRACTS
    }
    malicious_snapshot["namespace_shadow"] = {
        "module_id": "namespace_shadow",
        "managed": True,
        "source": "local_package",
        "required": False,
        "install_status": "enabled",
        "enabled": True,
        "api_namespaces": ["/api/v1/modules"],
    }
    payload = get_module_catalog(lifecycle_snapshot=malicious_snapshot)
    response = validate_response(payload)
    modules = response.modules
    keys = [module.key for module in modules]
    task_ids = [module.task_id for module in modules]

    assert response.architecture == "modular-monolith"
    assert response.catalog_version == 2
    assert len(keys) == len(set(keys))
    assert len(task_ids) == len(set(task_ids))
    assert "catalog" in keys and "module_manager" in keys
    assert "x_monitor" in keys and "demon_slayer" in keys
    assert all(key in keys for key in (
        "intel_sources", "bilibili", "youtube", "github_intel", "papers", "rss_intel"
    ))
    assert "namespace_shadow" not in keys
    assert all(module.target_namespace.startswith("/api/v1/") for module in modules)
    assert all((PROJECT_ROOT / module.task_file).is_file() for module in modules if module.task_file)
    for module_id, contract in CORE_MODULE_CONTRACTS.items():
        assert contract.module_id == module_id
        core_module = next(module for module in modules if module.key == module_id)
        assert core_module.required is contract.required
        assert core_module.managed is contract.managed
        assert core_module.source == contract.source
        assert core_module.api_namespaces == list(contract.api_namespaces)
        assert core_module.target_namespace in contract.api_namespaces
        assert core_module.installed_version is None
        assert core_module.install_status == "enabled"

    focus = next(module for module in modules if module.key == "focus")
    assert focus.migration_status == "installable"
    assert focus.managed is True and focus.source == "local_package"
    assert focus.install_status == "available" and focus.enabled is False
    assert focus.requires_restart is True
    assert focus.api_namespaces == ["/api/v1/focus"]
    assert "/api/v1/focus/encouragement" in focus.current_endpoints
    assert "/focus/reset" in focus.legacy_endpoints
    assert focus.data_owner and focus.network_side_effects and focus.failure_mode

    calendar = next(module for module in modules if module.key == "calendar")
    assert calendar.migration_status == "modular"
    assert calendar.api_namespaces == ["/api/v1/calendar"]
    assert len(calendar.current_endpoints) == 10
    assert calendar.data_owner and calendar.data_owner.endswith("calendar_memo.json")
    assert calendar.dashboard_surface == "legacy:/dashboard#calendar"

    daily_briefing = next(module for module in modules if module.key == "daily_briefing")
    assert "/api/v1/briefing/generation-status" in daily_briefing.current_endpoints

    conversation = next(module for module in modules if module.key == "conversation")
    assert conversation.migration_status == "modular"
    assert conversation.api_namespaces == ["/api/v1/conversation", "/api/v1/llm-profile"]
    assert "/chat/text-only" in conversation.legacy_endpoints
    assert conversation.data_owner and "llm_profile.json" in conversation.data_owner
    assert conversation.secret_owner and "never profile" in conversation.secret_owner
    assert conversation.dashboard_surface == "legacy:/dashboard#llm-profile"

    demon = next(module for module in modules if module.key == "demon_slayer")
    assert demon.migration_status == "modular"
    assert demon.api_namespaces == ["/api/v1/demon-slayer"]
    assert "/demon/status" in demon.legacy_endpoints and "/demon/reset" in demon.legacy_endpoints
    assert demon.data_owner and "demon_slayer.json" in demon.data_owner
    assert demon.dashboard_surface == "legacy:/dashboard#demon using versioned API; no business state in localStorage"

    affection_memory = next(module for module in modules if module.key == "affection_memory")
    assert affection_memory.migration_status == "modular"
    assert affection_memory.api_namespaces == ["/api/v1/relationship", "/api/v1/memories"]
    assert "/affection/reset" in affection_memory.legacy_endpoints
    assert "/memories/clear" in affection_memory.legacy_endpoints
    assert affection_memory.data_owner and "server/data/affection_state.json" in affection_memory.data_owner
    assert affection_memory.data_owner and "server/data/memories.json" in affection_memory.data_owner
    assert affection_memory.network_side_effects and "trusted-dashboard-Origin" in affection_memory.network_side_effects
    assert affection_memory.failure_mode and "cross-site reads/writes/preflight" in affection_memory.failure_mode
    assert affection_memory.dashboard_surface and "no personal state in localStorage" in affection_memory.dashboard_surface

    fitness = next(module for module in modules if module.key == "fitness")
    assert fitness.migration_status == "modular"
    assert fitness.api_namespaces == ["/api/v1/fitness"]
    assert "/fitness/reset" in fitness.legacy_endpoints
    assert fitness.data_owner and "server/data/fitness_checkins.json" in fitness.data_owner
    assert fitness.failure_mode and "atomic replacement" in fitness.failure_mode
    assert fitness.dashboard_surface and "no fitness state in localStorage" in fitness.dashboard_surface

    voice = next(module for module in modules if module.key == "voice")
    assert voice.label == "语音公共契约与编排"
    assert voice.migration_status == "modular"
    assert voice.api_namespaces == ["/api/v1/voice", "/api/v1/voice-control"]
    assert "/voice/chat" in voice.legacy_endpoints
    assert "/api/v1/voice-control/status" in voice.legacy_endpoints
    assert "/api/v1/voice-control/asr/start" in voice.legacy_endpoints
    assert "/api/v1/voice-control/gpt-sovits/start" in voice.legacy_endpoints
    assert voice.data_owner and "server/output/voice_replies" in voice.data_owner

    engine = next(module for module in modules if module.key == "gpt_sovits_engine_provider")
    assert engine.task_id == "PK-211" and engine.type == "sidecar"
    assert engine.process == "tts-sidecar" and engine.target_namespace == "/api/v1/voice"
    assert engine.data_owner and "no role assets" in engine.data_owner
    assert engine.network_side_effects and "user-invoked acquisition" in engine.network_side_effects

    voice_packs = next(module for module in modules if module.key == "voice_pack_registry")
    assert voice_packs.task_id == "PK-212" and voice_packs.type == "in_process"
    assert voice_packs.target_namespace == "/api/v1/voice-packs"
    assert voice_packs.data_owner and "ignored local registry" in voice_packs.data_owner
    assert voice_packs.failure_mode and "preserves the previous active pack" in voice_packs.failure_mode

    intel_sources = next(module for module in modules if module.key == "intel_sources")
    assert intel_sources.task_id == "PK-115" and intel_sources.migration_status == "modular"
    assert intel_sources.target_namespace == "/api/v1/intel-sources"
    assert intel_sources.data_owner and "intel_sources.json" in intel_sources.data_owner
    for key, task_id in (
        ("x_monitor", "PK-120"),
        ("bilibili", "PK-130"),
        ("youtube", "PK-131"),
        ("github_intel", "PK-132"),
        ("papers", "PK-133"),
        ("rss_intel", "PK-134"),
    ):
        source_module = next(module for module in modules if module.key == key)
        assert source_module.task_id == task_id
        assert source_module.migration_status == "modular"
        assert source_module.network_side_effects and source_module.failure_mode
    qq_bridge = next(module for module in modules if module.key == "qq_bridge")
    assert qq_bridge.migration_status == "modular"
    assert qq_bridge.process == "sidecar:qq-bridge"
    assert qq_bridge.target_namespace == "/api/v1/qq-control"
    assert "/api/v1/demon-slayer/goals" in qq_bridge.current_endpoints
    assert "/api/v1/focus/encouragement" in qq_bridge.current_endpoints
    assert qq_bridge.data_owner and qq_bridge.network_side_effects and qq_bridge.failure_mode

    with tempfile.TemporaryDirectory(prefix="kei-feature-catalog-") as temp_dir:
        root = Path(temp_dir)
        isolated_manager = ModuleManager(
            runtime_root=root / "runtime" / "modules",
            registry_path=root / "data" / "module_registry.json",
            data_root=root / "data" / "modules",
        )
        with patch.object(module_manager_service, "_MANAGER", isolated_manager):
            import api

    route_paths = {route.path for route in api.app.routes}
    route_keys = []
    for route in api.app.routes:
        route_keys.extend((method, route.path) for method in (getattr(route, "methods", None) or ()))
    assert len(route_keys) == len(set(route_keys)), "duplicate method/path registration detected"
    assert "/api/v1/modules" in route_paths
    assert "/api/v1/modules/{module_id}/install" in route_paths
    assert "/api/v1/modules/official-catalog" in route_paths
    assert "/api/v1/modules/official-catalog/refresh" in route_paths
    assert "/api/v1/modules/{module_id}/install-official" in route_paths
    assert "/api/v1/modules/{module_id}/update-official" in route_paths
    assert "/api/v1/modules/{module_id}/rollback" in route_paths
    assert "/api/v1/modules/{module_id}/rollback-official" in route_paths
    assert "/api/v1/modules/{module_id}/purge-data" in route_paths
    middleware = [item.cls for item in api.app.user_middleware]
    assert middleware[0] is LoopbackAccessMiddleware
    business_paths = {
        "/api/v1/calendar/today",
        "/api/v1/voice-packs",
        "/api/v1/fitness/status",
        "/api/v1/conversation",
        "/chat",
        "/api/v1/qq-control/status",
        "/api/v1/relationship/status",
        "/api/v1/intel-sources",
        "/api/v1/x/posts",
        "/api/v1/bilibili/profiles",
        "/api/v1/briefing/today",
    }
    assert business_paths.isdisjoint(route_paths), (
        "clean Core must not statically assemble optional business routes"
    )

    print("feature catalog tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
