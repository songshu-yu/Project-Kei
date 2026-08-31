"""Offline cumulative verification for the 20 official installable modules."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import _path_setup  # noqa: F401
from fastapi import FastAPI

from core.intel_contracts import CollectorRegistry
from core.modules.assembly import ModuleActivationCoordinator
from core.modules.loader import InProcessModuleLoader
from core.modules.manager import ModuleManager
from core.modules.manifest import validate_manifest
from features.affection_memory.package_builder import build_affection_memory_package
from features.bilibili.package_builder import build_bilibili_package
from features.calendar.package_builder import build_calendar_package
from features.conversation.package_builder import build_conversation_package
from features.daily_briefing.package_builder import build_daily_briefing_package
from features.demon_slayer.package_builder import build_demon_slayer_package
from features.fitness.package_builder import build_fitness_package
from features.focus.package_builder import build_focus_package
from features.github_intel.package_builder import build_github_intel_package
from features.intel_sources.package_builder import build_intel_sources_package
from features.life_forecast.package_builder import build_life_forecast_package
from features.papers.package_builder import build_papers_package
from features.rss_intel.package_builder import build_rss_intel_package
from features.voice.package_builder import build_voice_package
from features.voice.providers.gpt_sovits.package_builder import (
    build_gpt_sovits_provider_package,
)
from features.voice.voice_packs.distribution.package_builder import (
    build_voice_pack_distribution_package,
)
from features.voice_pack_registry.package_builder import build_voice_pack_registry_package
from features.x_monitor.package_builder import build_x_monitor_package
from features.youtube.package_builder import build_youtube_package
from qq_bridge.package_builder import build_qq_bridge_package


SERVER_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = SERVER_ROOT / "core" / "modules" / "official-catalog.json"
BUILDERS = (
    ("affection_memory", build_affection_memory_package, SERVER_ROOT / "features" / "affection_memory"),
    ("bilibili", build_bilibili_package, SERVER_ROOT / "features" / "bilibili"),
    ("calendar", build_calendar_package, SERVER_ROOT / "features" / "calendar"),
    ("conversation", build_conversation_package, SERVER_ROOT / "features" / "conversation"),
    ("daily_briefing", build_daily_briefing_package, SERVER_ROOT / "features" / "daily_briefing"),
    ("demon_slayer", build_demon_slayer_package, SERVER_ROOT / "features" / "demon_slayer"),
    ("fitness", build_fitness_package, SERVER_ROOT / "features" / "fitness"),
    ("focus", build_focus_package, SERVER_ROOT / "features" / "focus"),
    ("github_intel", build_github_intel_package, SERVER_ROOT / "features" / "github_intel"),
    ("intel_sources", build_intel_sources_package, SERVER_ROOT / "features" / "intel_sources"),
    ("life_forecast", build_life_forecast_package, SERVER_ROOT / "features" / "life_forecast"),
    ("papers", build_papers_package, SERVER_ROOT / "features" / "papers"),
    ("rss_intel", build_rss_intel_package, SERVER_ROOT / "features" / "rss_intel"),
    ("voice", build_voice_package, SERVER_ROOT / "features" / "voice"),
    (
        "gpt_sovits_engine_provider",
        build_gpt_sovits_provider_package,
        SERVER_ROOT / "features" / "voice" / "providers" / "gpt_sovits",
    ),
    (
        "voice_pack_distribution",
        build_voice_pack_distribution_package,
        SERVER_ROOT / "features" / "voice" / "voice_packs" / "distribution",
    ),
    (
        "voice_pack_registry",
        build_voice_pack_registry_package,
        SERVER_ROOT / "features" / "voice_pack_registry",
    ),
    ("x_monitor", build_x_monitor_package, SERVER_ROOT / "features" / "x_monitor"),
    ("youtube", build_youtube_package, SERVER_ROOT / "features" / "youtube"),
    ("qq_bridge", build_qq_bridge_package, SERVER_ROOT / "qq_bridge"),
)
PROTECTED_NAMES = {
    ".env",
    "node_modules",
    "vendor",
    "data",
    "demon_slayer.json",
    "focus_timer.json",
    "fitness_checkins.json",
    "calendar_memo.json",
    "llm_profile.json",
    "intel_sources.json",
    "x_profiles.json",
    "x_daily_posts.json",
    "x_daily_replies.json",
}
LIFECYCLE_MODULES = {
    "affection_memory",
    "daily_briefing",
    "demon_slayer",
    "fitness",
    "focus",
    "intel_sources",
    "x_monitor",
    "youtube",
}


class _DescriptorManager:
    def __init__(self, descriptor: dict) -> None:
        self.descriptor = descriptor

    def enabled_activation_descriptors(self) -> list[dict]:
        return [self.descriptor]

    @staticmethod
    def record_load_results(_results) -> None:
        return None


def _lifecycle_app(module_id: str, root: Path) -> FastAPI:
    app = FastAPI()
    collectors = CollectorRegistry()
    app.state.intel_collector_registry = collectors
    app.state.collector_registry = collectors
    app.state.intel_source_config_path = root / "intel_sources.json"
    app.state.intel_source_local_control_guard = lambda _request: True
    app.state.intel_source_snapshot_provider = lambda: {}
    app.state.x_monitor_profile_path = root / "x_profiles.json"
    app.state.x_monitor_posts_path = root / "x_daily_posts.json"
    app.state.x_monitor_nitter_instances = ("https://nitter.invalid",)
    app.state.x_monitor_collector_client = object()
    app.state.affection_memory_relationship_path = root / "affection_state.json"
    app.state.affection_memory_memory_path = root / "memories.json"
    app.state.affection_memory_local_control_guard = lambda _request: True
    app.state.daily_briefing_root_dir = root
    app.state.daily_briefing_source_config_provider = lambda: {}
    app.state.daily_briefing_local_request_guard = lambda _request: True
    app.state.demon_slayer_state_path = root / "demon_slayer.json"
    app.state.fitness_state_path = root / "fitness_checkins.json"
    app.state.fitness_local_control_guard = lambda _request: True
    app.state.focus_state_path = root / "focus_timer.json"
    app.state.focus_local_request_guard = lambda _request: True
    if module_id == "youtube":
        app.state.youtube_collector_provider = lambda: _FakeCollector("youtube")
    return app


class _FakeCollector:
    def __init__(self, source_id: str) -> None:
        self.source_id = source_id

    async def collect(self, _request):
        raise AssertionError("lifecycle registration must not collect")


def _descriptor(package_root: Path) -> dict:
    payload = json.loads((package_root / "manifest.json").read_text(encoding="utf-8"))
    manifest = validate_manifest(payload)
    return {
        "module_id": manifest.id,
        "manifest": manifest.to_dict(),
        "manifest_object": manifest,
        "package_root": str(package_root),
    }


def _state_snapshot(app: FastAPI) -> dict[str, object]:
    return dict(app.state._state)


def _assert_state_restored(app: FastAPI, baseline: dict[str, object]) -> None:
    current = _state_snapshot(app)
    assert set(current) == set(baseline), {
        "extra": set(current) - set(baseline),
        "missing": set(baseline) - set(current),
    }
    assert all(current[name] is value for name, value in baseline.items())


def _assert_import_tree_removed(import_name: str) -> None:
    prefix = import_name + "."
    assert not [
        name for name in sys.modules if name == import_name or name.startswith(prefix)
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_and_digest(path: Path) -> tuple[dict, str]:
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        assert names.count("manifest.json") == 1
        manifest_bytes = archive.read("manifest.json")
        for name in names:
            parts = tuple(part.lower() for part in PurePosixPath(name).parts)
            assert not (set(parts) & PROTECTED_NAMES), (path.name, name)
            assert not PurePosixPath(name).is_absolute()
            assert ".." not in parts
        return json.loads(manifest_bytes.decode("utf-8")), hashlib.sha256(manifest_bytes).hexdigest()


def _topological_order(manifests: dict[str, dict]) -> list[str]:
    pending = {module_id: set(value["dependencies"]) for module_id, value in manifests.items()}
    ordered: list[str] = []
    while pending:
        ready = sorted(module_id for module_id, dependencies in pending.items() if not dependencies)
        assert ready, "official module dependency graph contains a cycle"
        ordered.extend(ready)
        for module_id in ready:
            pending.pop(module_id)
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return ordered


def check_official_release_set_is_deterministic_and_installable() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    releases = {item["module_id"]: item for item in catalog["modules"]}
    expected_ids = {module_id for module_id, _, _ in BUILDERS}
    assert len(BUILDERS) == 20
    assert set(releases) == expected_ids

    with tempfile.TemporaryDirectory(prefix="kei-official-release-set-") as temp:
        root = Path(temp)
        first_root = root / "first"
        second_root = root / "second"
        first_root.mkdir()
        second_root.mkdir()
        manifests: dict[str, dict] = {}
        assets: dict[str, Path] = {}

        for module_id, builder, feature_root in BUILDERS:
            fragment_path = feature_root / "release" / "official-release-fragment.json"
            fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
            assert fragment["module_id"] == module_id
            asset_name = fragment["asset_name"]
            first = builder(first_root / asset_name)
            second = builder(second_root / asset_name)
            assert first.read_bytes() == second.read_bytes(), module_id
            release = releases[module_id]
            manifest, manifest_sha256 = _manifest_and_digest(first)
            assert manifest["id"] == module_id
            assert manifest["version"] == release["version"] == fragment["version"]
            assert first.stat().st_size == release["package_size"]
            assert _sha256(first) == release["package_sha256"]
            assert manifest_sha256 == release["manifest_sha256"]
            manifests[module_id] = manifest
            assets[module_id] = first

        order = _topological_order(manifests)
        manager_root = root / "manager"
        manager = ModuleManager(
            runtime_root=manager_root / "runtime" / "modules",
            registry_path=manager_root / "data" / "module_registry.json",
            data_root=manager_root / "data" / "modules",
        )
        for module_id in order:
            result = manager.install(
                assets[module_id],
                expected_sha256=releases[module_id]["package_sha256"],
            )
            assert result["module_id"] == module_id
        assert set(manager.snapshot()) == expected_ids

        in_process = [
            module_id for module_id in order if manifests[module_id]["type"] == "in_process"
        ]
        with patch.dict(os.environ, {"LLM_API_KEY": "fictional-release-test-key"}):
            for module_id in in_process:
                assert manager.enable(module_id)["enabled"] is True
            for module_id in reversed(in_process):
                assert manager.disable(module_id)["enabled"] is False
        for module_id in reversed(order):
            removed = manager.uninstall(module_id)
            assert removed["data_preserved"] is True
        assert manager.snapshot() == {}
        for module_id in order:
            assert manager.install(
                assets[module_id],
                expected_sha256=releases[module_id]["package_sha256"],
            )["module_id"] == module_id
        assert set(manager.snapshot()) == expected_ids


def check_official_in_process_lifecycle_cleanup() -> None:
    """Load/unload the eight rejected packages with no process-local residue."""
    builders = {
        module_id: builder
        for module_id, builder, _feature_root in BUILDERS
        if module_id in LIFECYCLE_MODULES
    }
    assert set(builders) == LIFECYCLE_MODULES
    with tempfile.TemporaryDirectory(prefix="kei-official-lifecycle-") as temp:
        root = Path(temp)
        for module_id in sorted(builders):
            package_root = builders[module_id](root / f"package-{module_id}")
            descriptor = _descriptor(package_root)
            app = _lifecycle_app(module_id, root / f"state-{module_id}")
            baseline_state = _state_snapshot(app)
            baseline_routes = tuple(app.router.routes)
            baseline_middleware = tuple(app.user_middleware)
            loader = InProcessModuleLoader()
            coordinator = ModuleActivationCoordinator(
                _DescriptorManager(descriptor),
                loader,
            )

            loaded = coordinator.activate(app)
            assert loaded == [{"module_id": module_id, "status": "loaded"}]
            unregister = loader._registrations[module_id]["unregister"]
            import_name = loader._registrations[module_id]["import_name"]
            assert callable(unregister), module_id

            foreign_provider = object()
            if module_id == "affection_memory":
                app.state.conversation_context_provider = foreign_provider
            stopped = coordinator.deactivate(app)
            assert stopped == [{"module_id": module_id, "status": "stopped"}]
            unregister(app)
            unregister(app)
            if module_id == "affection_memory":
                assert app.state.conversation_context_provider is foreign_provider
                delattr(app.state, "conversation_context_provider")

            assert tuple(app.router.routes) == baseline_routes
            assert tuple(app.user_middleware) == baseline_middleware
            assert not baseline_state["intel_collector_registry"].snapshot()
            _assert_state_restored(app, baseline_state)
            _assert_import_tree_removed(import_name)


def check_registration_failure_rolls_back_every_side_effect() -> None:
    """Inject a post-add middleware failure into the formal affection package."""
    with tempfile.TemporaryDirectory(prefix="kei-official-register-failure-") as temp:
        root = Path(temp)
        package_root = build_affection_memory_package(root / "affection-package")
        descriptor = _descriptor(package_root)
        app = _lifecycle_app("affection_memory", root / "state")
        baseline_state = _state_snapshot(app)
        baseline_routes = tuple(app.router.routes)
        baseline_middleware = tuple(app.user_middleware)
        add_middleware = app.add_middleware

        def fail_after_add(*args, **kwargs):
            add_middleware(*args, **kwargs)
            raise RuntimeError("injected post-middleware failure")

        app.add_middleware = fail_after_add  # type: ignore[method-assign]
        result = InProcessModuleLoader().load_one(app, descriptor)
        assert result["status"] == "failed"
        assert tuple(app.router.routes) == baseline_routes
        assert tuple(app.user_middleware) == baseline_middleware
        _assert_state_restored(app, baseline_state)
        manifest = descriptor["manifest_object"]
        _assert_import_tree_removed(
            "_project_kei_module_%s_%s"
            % (manifest.id, manifest.version.replace(".", "_").replace("-", "_"))
        )


class _FailingState:
    def __init__(self, values: dict[str, object], fail_name: str) -> None:
        object.__setattr__(self, "_state", dict(values))
        object.__setattr__(self, "_fail_name", fail_name)
        object.__setattr__(self, "_armed", True)

    def __getattr__(self, name: str) -> object:
        try:
            return self._state[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: object) -> None:
        if name == self._fail_name and self._armed:
            object.__setattr__(self, "_armed", False)
            raise RuntimeError("injected provider publication failure")
        self._state[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self._state[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def check_provider_publication_failure_restores_intel_source_state() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-intel-source-register-failure-") as temp:
        root = Path(temp)
        package_root = build_intel_sources_package(root / "intel-sources-package")
        descriptor = _descriptor(package_root)
        app = _lifecycle_app("intel_sources", root / "state")
        baseline_state = _state_snapshot(app)
        baseline_routes = tuple(app.router.routes)
        app.state = _FailingState(
            baseline_state,
            "intel_source_snapshot_provider",
        )
        result = InProcessModuleLoader().load_one(app, descriptor)
        assert result["status"] == "failed"
        assert tuple(app.router.routes) == baseline_routes
        _assert_state_restored(app, baseline_state)
        manifest = descriptor["manifest_object"]
        _assert_import_tree_removed(
            "_project_kei_module_%s_%s"
            % (manifest.id, manifest.version.replace(".", "_").replace("-", "_"))
        )


def main() -> int:
    check_official_release_set_is_deterministic_and_installable()
    check_official_in_process_lifecycle_cleanup()
    check_registration_failure_rolls_back_every_side_effect()
    check_provider_publication_failure_restores_intel_source_state()
    print("official 20-module release-set tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
